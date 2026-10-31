#!/usr/bin/env bash
# 일일 조사 러너: ChatGPT(Codex CLI, 웹검색)로 오늘자 report.json을 작성하고 검증한다.
# 에이전트는 직접 웹 조사하지 않고 이 스크립트만 실행한다. 게시는 하지 않는다.
#
# 사용법: bash tools/run_codex_research.sh [--out PATH] [--timeout SEC] [--strict-links] [--keep-work]
#   --out PATH      검증 통과본을 쓸 위치 (기본 data/report.json). 드라이런은 저장소 밖 경로 지정.
#   --timeout SEC   Codex 최대 실행 시간 (기본 2400초 = 40분, 환경변수 CODEX_TIMEOUT)
#   --strict-links  유료·봇 차단(401/403/429 등)으로 접속 확인 불가한 링크도 제거
#   --keep-work     Codex 임시 작업 폴더를 지우지 않음
#
# 종료 코드 (0일 때만 다음 단계 `python3 tools/publish_daily.py` 진행)
#   0  성공: 검증 통과본이 --out 에 기록됨 (publish_daily --check 통과)
#   2  사용법·환경 오류 (codex 없음, 프롬프트 파일 없음, 동시 실행 중)
#   10 Codex 실행 실패 (비정상 종료)
#   11 Codex 타임아웃
#   12 Codex 결과 없음 또는 JSON 파싱 불가
#   13 검증 실패 (날짜가 오늘 아님, 스키마 오류, 검증된 Top Issues 5개 미만 등)
#   14 publish_daily.py와 동일 규칙의 사전검증 실패
# 출력 형식은 기존 data/report.json과 동일(publishedAt 등 보조 필드는 제거).
# 실패 시 --out 파일은 변경되지 않는다. 로그: <out 폴더>/codex-run-<날짜>/ (기본은 /tmp/trade-brief-runs/)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/data/report.json"
TIMEOUT="${CODEX_TIMEOUT:-2400}"
EFFORT="${CODEX_EFFORT:-high}"   # Codex 추론 강도 (기본 설정은 none → 조사량이 매우 적음)
STRICT=""
KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --strict-links) STRICT="--strict-links"; shift ;;
    --keep-work) KEEP=1; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
  esac
done

command -v codex >/dev/null || { echo "codex CLI 없음" >&2; exit 2; }
[ -f "$ROOT/tools/research_prompt.md" ] || { echo "tools/research_prompt.md 없음" >&2; exit 2; }
mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

exec 9>/tmp/trade-brief-research.lock
flock -n 9 || { echo "다른 조사 러너가 실행 중" >&2; exit 2; }

TODAY="$(TZ=Asia/Seoul date +%F)"
YESTERDAY="$(TZ=Asia/Seoul date -d '-1 day' +%F)"
NOW_ISO="$(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M:%S+09:00)"
NOW_HM="$(TZ=Asia/Seoul date +%H:%M)"
if [ "$OUT" = "$ROOT/data/report.json" ]; then LOGBASE="/tmp/trade-brief-runs"; else LOGBASE="$(dirname "$OUT")"; fi
LOGDIR="$LOGBASE/codex-run-$TODAY-$(TZ=Asia/Seoul date +%H%M%S)"
mkdir -p "$LOGDIR"
WORK="$(mktemp -d /tmp/codex-research.XXXXXX)"
cleanup() { [ "$KEEP" = 1 ] || rm -rf "$WORK"; }
trap cleanup EXIT

# --- 자체완결 프롬프트 구성 ---------------------------------------------------
PROMPT="$LOGDIR/prompt.md"
{
cat <<HDR
당신은 한국 산업통상 담당자용 "글로벌 통상 브리프"의 조사·작성자다. 웹 검색으로 실제 기사를 찾아 확인하고,
결과를 현재 작업 폴더의 report.json 파일 하나로만 저장한다. 다른 파일은 만들거나 수정하지 않는다.
화면 출력(최종 메시지)은 "DONE" 한 단어로 충분하다.

## 실행 정보
- 오늘(KST): $TODAY, 현재 시각: $NOW_ISO
- 수집 구간: $YESTERDAY $NOW_HM ~ $TODAY $NOW_HM KST (최근 24시간). Kommersant·RBC의 한국 관련 러시아 기사는 48시간, 경제단체 보고서는 최근 3~4일 내 발간분.

## 절대 원칙
1. 절대 지어내지 않는다. 웹 검색 결과에서 실제 기사 URL·매체·게시 시각을 확인한 내용만 쓴다. 기억이나 추측으로 채우지 않는다.
2. 출처(매체) 또는 게시 날짜·시각을 확인할 수 없는 항목은 삭제한다. 기간 밖 기사도 삭제한다.
3. 모든 bullet(topIssues 포함)에는 반드시 "source"(매체명), "url"(그 기사의 실제 주소, 홈페이지·검색결과 주소 금지),
   "publishedAt"(기사 게시 시각, 시간대 포함 ISO 8601, 예 "2026-10-31T21:40:00+09:00" 또는 "...Z")을 넣는다.
   publishedAt을 확인할 수 없으면 그 bullet을 넣지 않는다. 텍스트는 기사 워딩을 객관적으로 옮기고 해석을 붙이지 않는다.
4. topIssues는 정확히 5개. 검증 단계에서 링크가 죽었거나 날짜가 틀린 항목은 자동 제거되어 5개 미만이면 게시가 취소되므로,
   확실한 항목으로 고른다. Top Issues 문장은 일일보도동향 bullet에서 같은 문장으로 반복하지 않는다.
5. departments는 정확히 이 순서와 키: cis(통상협력총괄과), neasia(동북아통상과), india(인도통상협력과), asean(아주통상과),
   mea(중동아프리카통상과). 이슈가 없는 과는 "issues": [].
6. category는 국제·외교, 정책·규제, 경제동향, 산업동향, 대외교역, 중동정세 중 하나.
7. reports는 3~4일 내 발간되고 기관 공식 원문(가능하면 PDF 직링크)이 확인된 것만. 없으면 [].
8. 한국어, 명사형 종결(예: "비용부담은 여전"). 진행상황·안내 문구 금지.
9. 확인 못 한 부분은 notes 배열에 짧게 적는다(선택).
10. source는 url 페이지의 실제 발행 매체명으로 쓴다. 재배포·요약 사이트(MarketScreener, Yahoo 등)의 기사를 원 매체명
    (예: Reuters)으로 표기하려면 그 페이지에 원 매체가 명시돼 있어야 하며, 이 경우 "Reuters(MarketScreener 재게재)"처럼 쓴다.

## 조사 범위 (누락 없이: 아래를 모두 개별 검색한 뒤 작성)
- 공통 필수: 미국·이란 협상/중동 정세, 유가(브렌트·WTI) 변동 요인, 글로벌 에너지 공급(OPEC+, LNG), 핵심광물·공급망, 주요국(미·중·EU·일) 정책 변화, 통상 규제·관세·제재.
- 소관과·국가별로 최소 1회 이상씩 검색: 러시아·우크라이나·카자흐스탄·우즈베키스탄 등 CIS·몽골 / 중국·일본·대만·홍콩 /
  인도·파키스탄·방글라데시 등 서남아 / 베트남·인도네시아·필리핀·말레이시아·싱가포르·태국 등 아세안 /
  사우디·UAE·이란·이스라엘·이집트·카타르·튀르키예·아프리카.
- 각 국가와 한국의 정상회담·장관급 회담·대통령 발언 등 한국 관련 고위급 교류 기사 검색 (연합뉴스 영문, Korea Herald, Korea JoongAng Daily 등 한국 영문 매체 사용 가능).
- Kommersant·RBC에서 한국(Корея, Южная Корея) 관련 48시간 내 기사 검색.
- 대상 경제단체 보고서 사이트(KITA, 수은 해외경제연구소, 현대경제연구원, 대한상의 SGI, KOTRA, KIEP)의 최근 3~4일 발간 보고서 확인.
- 목표 분량: Top Issues 5개 + 일일보도동향 이슈 12~25개(각 이슈 bullet 2~3개). 각 소관과마다 확인된 이슈가 있으면 최소 1개 이상,
  통상협력총괄과(CIS)는 고영향 이슈가 없으면 에너지·핵심광물·인프라·물류·프로젝트 관련 보강형 이슈 최소 1개.
- 한 매체에 집중하지 말고, 단순 사실은 Reuters·AP, 정책 해석·시장 영향은 Bloomberg·FT·WSJ·Nikkei·CNBC 보도로 교차 확인.
  유료 기사는 검색 결과에 노출된 제목·요약·게시 시각까지만 사용한다.

## report.json 스키마 (아래 README 발췌를 따르되, 각 bullet에 publishedAt 추가)
필수 최상위 값: "date": "$TODAY", "generatedAt": "작성 완료 시각(+09:00)", "coverage": "$YESTERDAY $NOW_HM ~ $TODAY $NOW_HM KST 보도 기준 (최근 24시간, 러시아 한국 관련 이슈 48시간)".
bullet 예: {"text": "...", "source": "Reuters", "url": "https://www.reuters.com/...", "publishedAt": "2026-10-31T09:12:00Z"}

HDR
awk '/^## report.json 전체 형식/{f=1} /^### 개인화와 복사/{f=0} f' "$ROOT/README.md"
echo
echo "## 사용자 원문 조사 프롬프트 (내용 기준은 이것을 그대로 따른다; '출력'은 report.json 작성으로 대체)"
echo
cat "$ROOT/tools/research_prompt.md"
cat <<TAIL

## 마지막 점검 (저장 전에 반드시)
- 모든 bullet의 publishedAt이 수집 구간 안인지, url이 그 기사 페이지인지 재확인. 아니면 삭제.
- topIssues 5개, departments 5개(순서·키), JSON 문법 유효.
- 현재 작업 폴더에 report.json 저장 (UTF-8). 다른 파일 생성·수정 금지.
TAIL
} > "$PROMPT"

# --- Codex 실행 (임시 폴더에서만 쓰기 가능: 저장소·archive·research_prompt 수정 불가) ---
echo "[$(TZ=Asia/Seoul date +%T) KST] Codex 조사 시작 (최대 ${TIMEOUT}s) work=$WORK log=$LOGDIR"
START=$(date +%s)
# 인증키 등 비밀 환경변수는 Codex에 넘기지 않는다.
for v in $(compgen -e | grep -E '^(DATA_GO_KR|GH_|GITHUB_)|KEY|TOKEN|SECRET|PASSWORD' || true); do unset "$v"; done
timeout --kill-after=60 "$TIMEOUT" codex --search exec -c model_reasoning_effort="\"$EFFORT\"" --skip-git-repo-check --ephemeral \
  -s workspace-write -C "$WORK" -o "$LOGDIR/codex-last-message.txt" - < "$PROMPT" \
  > "$LOGDIR/codex.log" 2>&1
RC=$?
ELAPSED=$(( $(date +%s) - START ))
echo "[$(TZ=Asia/Seoul date +%T) KST] Codex 종료 rc=$RC, ${ELAPSED}s"
echo "$ELAPSED" > "$LOGDIR/elapsed_seconds"
if [ $RC -eq 124 ] || [ $RC -eq 137 ]; then echo "Codex 타임아웃(${TIMEOUT}s)" >&2; exit 11; fi
if [ $RC -ne 0 ]; then echo "Codex 실패 rc=$RC (로그: $LOGDIR/codex.log)" >&2; tail -5 "$LOGDIR/codex.log" >&2; exit 10; fi
if [ ! -s "$WORK/report.json" ]; then echo "Codex가 report.json을 만들지 않음" >&2; exit 12; fi
cp "$WORK/report.json" "$LOGDIR/raw-report.json"

# --- 후처리 검증 (curl 링크·게시일 재확인, 실패 항목 제거, Top 5 미만이면 중단) ---
python3 "$ROOT/tools/verify_report.py" --input "$LOGDIR/raw-report.json" --output "$LOGDIR/verified-report.json" \
  --log "$LOGDIR/verify-log.json" $STRICT
VRC=$?
if [ $VRC -ne 0 ]; then exit $VRC; fi
# publish_daily.py와 같은 검증(build_report_js.validate + 오늘 날짜)을 게시 없이 재확인
python3 - "$LOGDIR/verified-report.json" "$TODAY" "$ROOT/tools" <<'PY' || exit 14
import json, sys
sys.path.insert(0, sys.argv[3])
from build_report_js import validate
r = json.load(open(sys.argv[1], encoding='utf-8'))
validate(r)
assert r['date'] == sys.argv[2], f"date {r['date']} != {sys.argv[2]}"
print(f"사전검증 통과(게시 안 함): {r['date']}")
PY

cp "$LOGDIR/verified-report.json" "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
echo "완료: $OUT (로그 $LOGDIR). 다음 단계: python3 tools/publish_daily.py"
exit 0
