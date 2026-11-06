#!/usr/bin/env bash
# 일일 조사 러너: ChatGPT(Codex CLI, 웹검색)로 오늘자 report.json을 작성하고 검증한다.
# 에이전트는 직접 웹 조사하지 않고 이 스크립트만 실행한다. 게시는 하지 않는다.
#
# 사용법: bash tools/run_codex_research.sh [--out PATH] [--timeout SEC] [--check-links] [--strict-links] [--keep-work] [--prompt-only]
#   --out PATH      검증 통과본을 쓸 위치 (기본 data/report.json). 드라이런은 저장소 밖 경로 지정.
#   --timeout SEC   Codex 최대 실행 시간 (기본 2400초 = 40분, 환경변수 CODEX_TIMEOUT)
#   --check-links   (선택) 후처리에서 URL curl 재확인. 기본은 OFF — Codex 검증을 신뢰.
#   --strict-links  --check-links와 함께: 유료·봇 차단(401/403/429 등) 링크도 제거
#   --keep-work     Codex 임시 작업 폴더를 지우지 않음
#   --prompt-only   Codex를 실행하지 않고 프롬프트만 <로그폴더>/prompt.md 로 생성 후 종료(0). --out 은 저장소 밖 경로 권장.
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
CHECK_LINKS=""
KEEP=0
PROMPT_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --check-links) CHECK_LINKS="--check-links"; shift ;;
    --strict-links) STRICT="--strict-links"; shift ;;
    --keep-work) KEEP=1; shift ;;
    --prompt-only) PROMPT_ONLY=1; shift ;;
    -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
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
4. topIssues는 정확히 5개. 게시일·스키마 검증에서 날짜가 틀린 항목은 제거되어 5개 미만이면 게시가 취소되므로,
   확실한 항목으로 고른다. Top Issues 문장은 일일보도동향 bullet에서 같은 문장으로 반복하지 않는다.
   링크 HTTP 재검증은 후처리에서 하지 않는다. 출처·URL 검증은 Codex(본인)가 한다.
5. departments는 정확히 이 순서와 키: cis(통상협력총괄과), neasia(동북아통상과), india(인도통상협력과), asean(아주통상과),
   mea(중동아프리카통상과). 이슈가 없는 과는 "issues": [].
6. category는 국제·외교, 정책·규제, 경제동향, 산업동향, 대외교역, 중동정세 중 하나.
7. reports는 3~4일 내 발간되고 기관 공식 원문(가능하면 PDF 직링크)이 확인된 것만. 없으면 [].
8. 한국어, 명사형 종결(예: "비용부담은 여전"). 진행상황·안내 문구 금지.
9. 확인 못 한 부분은 notes 배열에 짧게 적는다(선택).
10. source/url은 원 발행 매체 도메인을 우선한다 (reuters.com, bloomberg.com, ft.com, wsj.com, apnews.com,
    nikkei.com, cnbc.com, aljazeera.com, kommersant.ru, rbc.ru 등). 재게재·요약 사이트
    (MarketScreener, StreetInsider, Investing.com, Yahoo Finance, swissinfo 등) URL은 쓰지 않는다.
    재게재 페이지에서 원문을 확인했으면 원문 URL과 원 매체명만 넣고, "(… 재게재)" 표기를 쓰지 않는다.
    원문 URL을 웹검색으로 찾지 못했을 때만 재게재 URL을 유지하고 notes에 "원문 URL 미확인: (매체·제목)"을 한 줄 남긴다.
    검증은 Codex가 한다. 후처리 curl 재검증에 의존하지 말 것.

## 조사 범위 (누락 없이: 아래를 모두 개별 검색한 뒤 작성)
- 공통 필수: 미국·이란 협상/중동 정세, 유가(브렌트·WTI) 변동 요인, 글로벌 에너지 공급(OPEC+, LNG), 핵심광물·공급망, 주요국(미·중·EU·일) 정책 변화, 통상 규제·관세·제재.
- 소관과·국가별로 최소 1회 이상씩 검색: 러시아·우크라이나·카자흐스탄·우즈베키스탄 등 CIS·몽골 / 중국·일본·대만·홍콩 /
  인도·파키스탄·방글라데시 등 서남아 / 베트남·인도네시아·필리핀·말레이시아·싱가포르·태국 등 아세안 /
  사우디·UAE·이란·이스라엘·이집트·카타르·튀르키예·아프리카.
- 각 국가와 한국의 정상회담·장관급 회담·대통령 발언 등 한국 관련 고위급 교류 기사 검색 (연합뉴스 영문, Korea Herald, Korea JoongAng Daily 등 한국 영문 매체 사용 가능).
- Kommersant·RBC에서 한국(Корея, Южная Корея) 관련 48시간 내 기사 검색.
- 대상 경제단체 보고서 사이트(KITA, 수은 해외경제연구소, 현대경제연구원, 대한상의 SGI, KOTRA, KIEP)의 최근 3~4일 발간 보고서 확인.
- 목표 분량: Top Issues 5개 + 일일보도동향 이슈 12~25개(각 이슈 bullet 2~3개). 각 소관과마다 확인된 이슈가 있으면 최소 1개 이상.

## 소관과별 최소 분량 (필수 조건; 위 절대 원칙 1~3 안에서 충족)
### 통상협력총괄과(cis): 러시아·우크라이나 외 국가 이슈 최소 1건 필수
- 러시아·우크라이나 이슈와 별도로, 다음 국가 중 최소 1개국 이슈를 반드시 1건 이상 넣는다:
  카자흐스탄, 우즈베키스탄, 투르크메니스탄, 키르기스스탄, 타지키스탄(중앙아시아) / 아제르바이잔, 아르메니아, 조지아(코카서스) / 몽골.
- 관점: 에너지(석유·가스·우라늄·전력), 핵심광물 개발, 인프라·철도·물류(중간회랑 TITR, 카스피해 항만, 중앙아-중국 철도 등),
  플랜트·프로젝트 수주·발표, 투자협정, 한국과의 협력. 사용자 원문 프롬프트의 '보강형' 규칙대로 글로벌 헤드라인급이 아니어도
  공급망·통상 환경 변화와 관련된 중간 수준 이슈를 포함한다. 프로젝트 관련 이슈(플랜트 수주 계획 발표 등)는 고영향 이슈로 볼 수 있다.
- 검색 방법: 위 9개국을 국가별로 각각 검색한다(Reuters, Bloomberg, AP, Nikkei Asia 외 Kazinform, Trend.az, Daryo, The Astana Times,
  Gazeta.uz, AKIpress, Montsame, Interfax 등 현지·지역 매체 사용 가능, 출처·게시 시각 확인 필수).
- 24시간 내 해당 국가 기사가 정말 없을 때만, 최근 기사 중 그 나라의 공급망·에너지·물류 구조적 변화, 정책 방향성 또는 경제흐름을 보여주는
  보강형 항목 1건을 넣는다. 이때도 publishedAt은 실제 게시 시각을 쓰며, 기간 밖 기사는 검증에서 제거되므로 가능한 한 24시간 내 보도를 우선한다.
  이 경우 notes에 "통상협력총괄과 중앙아·코카서스·몽골 검색 범위: (검색한 국가·매체)" 형식으로 확인한 검색 범위를 한 줄 기록한다.
  '해당 없음' 같은 문구는 쓰지 않는다.
- 본문(title·text)에 "고영향 이슈 제한적", "이슈 부재" 등의 문구를 쓰지 않는다.

### 아주통상과(asean): 이슈 최소 3건, 가능하면 서로 다른 3개국 이상
- 다음 국가를 국가별로 각각 검색한다: 필리핀, 싱가포르, 인도네시아, 말레이시아, 베트남, 태국 (추가로 캄보디아, 라오스, 미얀마, 브루나이, 아세안 전체).
- 관점: 통상·관세·FTA, 수출입 동향, 공급망·핵심광물(인도네시아 니켈 등)·반도체, 에너지·전력, 인프라·프로젝트, 주요 정책·금리, 한국과의 교류.
- asean 이슈는 최소 3건, 가능하면 서로 다른 아세안 국가 3개국 이상을 다룬다(한 나라 이슈만으로 채우지 않는다).
  각 이슈의 countries에 해당 국가명을 넣는다. 24시간 내 확인된 기사가 정말 부족할 때만 3건 미만을 허용하며, 지어내거나 기간 밖 기사로 채우지 않는다.
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
- cis에 러시아·우크라이나 외 중앙아·코카서스·몽골 이슈 1건 이상, asean 이슈 3건 이상(가능하면 3개국 이상)인지 확인. 부족하면 해당 국가를 다시 검색.
- 현재 작업 폴더에 report.json 저장 (UTF-8). 다른 파일 생성·수정 금지.
TAIL
} > "$PROMPT"
if [ "$PROMPT_ONLY" = 1 ]; then echo "프롬프트만 생성(Codex 미실행): $PROMPT"; exit 0; fi

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

# --- 후처리 검증 (게시일·스키마; 링크 curl은 기본 OFF — Codex 검증 신뢰. --check-links 시에만) ---
python3 "$ROOT/tools/verify_report.py" --input "$LOGDIR/raw-report.json" --output "$LOGDIR/verified-report.json" \
  --log "$LOGDIR/verify-log.json" $CHECK_LINKS $STRICT
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
