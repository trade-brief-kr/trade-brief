# 일일 업데이트 절차 (매일 08:00 KST 예약 실행용)

작업 디렉터리: `/workspace/trade-brief` (원격 `main`, GitHub Pages가 `main /`에서 배포). `gh`는 `trade-brief-kr`로 로그인되어 있음.

## 원칙 (반드시 지킬 것)
- 조사는 Codex(ChatGPT)가 한다(2단계). 아래 원칙은 러너가 Codex 프롬프트와 후처리로 적용한다.
- **절대 지어내지 않는다.** 웹 검색으로 실제 기사 페이지를 열어 날짜와 매체를 확인한 내용만 쓴다.
- 출처(매체)나 게시 날짜를 확인할 수 없는 항목은 **삭제**한다. 기억이나 추측으로 채우지 않는다.
- 기간: 일반 기사는 **최근 24시간**, 러시아 Kommersant·RBC의 한국 통상 관련 기사는 **48시간**, 경제단체·연구기관 보고서는 **최근 3~4일 내 발간된 PDF**만 쓴다.
- 검증된 Global Top Issues가 **5개 미만**이거나 게시 명령이 실패하면 **게시하지 않는다.** 커밋·푸시도 하지 않고 문제를 보고한다.
- `tools/research_prompt.md`(사용자 원문 프롬프트)는 수정하지 않는다. 과거 날짜의 `data/archive/*.json`도 수정하지 않는다.

## 단계
1. 준비
   ```sh
   cd /workspace/trade-brief && git checkout main && git pull --ff-only
   TZ=Asia/Seoul date +%F   # 오늘 날짜(KST) = 보고 날짜
   ```
2. 조사·`data/report.json` 작성 = **ChatGPT(Codex)** 로 수행한다. 에이전트는 직접 웹 조사·기사 작성·report.json 편집을 하지 않는다 (사용자 지시).
   ```sh
   bash tools/run_codex_research.sh; echo "rc=$?"
   ```
   - 러너가 `tools/research_prompt.md` 원문 + README 스키마 + 위 원칙을 Codex(웹검색)에 넘기고, 결과를 `tools/verify_report.py`로 후처리(게시일·스키마 검증; URL curl 재확인은 기본 OFF·Codex 검증 신뢰, 검증된 Top Issues 5개 미만이면 중단)한 뒤 통과본만 `data/report.json`에 쓴다. 최대 약 40분.
   - 종료 코드: `0` 성공 · `2` 환경 오류 · `10` Codex 실패 · `11` 타임아웃 · `12` 결과 없음/JSON 오류 · `13` 검증 실패(날짜, 스키마, Top Issues 5개 미만) · `14` 사전검증 실패.
   - **0이 아니면 여기서 멈춘다.** `data/report.json`은 변경되지 않은 상태다. 대신 조사해서 채우지 말고, 커밋·푸시 없이 실패 단계·종료 코드·사유(로그 `/tmp/trade-brief-runs/codex-run-*/`의 `codex.log`, `verify-log.json`)를 보고한다. `10`·`11`이면 1회까지 재실행 가능.
3. (참고) 드라이런: `bash tools/run_codex_research.sh --out /workspace/trade-brief-dryrun/report.json` (data/ 변경 없음)
4. 보고 시 (선택) `--check-links`를 켠 경우에만 `verify-log.json`의 `unverifiable`을 함께 적는다. 기본 경로는 curl 재확인 없음.
5. 검증·게시 (한 번에 처리, 같은 날 재실행 시 그 날짜를 덮어씀)
   ```sh
   python3 tools/publish_daily.py
   ```
   종료 코드가 0이 아니면 여기서 멈춘다. 이 경우 게시 파일은 변경되지 않는다. `git checkout -- data/report.json`으로 되돌리고 오류 메시지를 보고한다.
6. 커밋·푸시
   ```sh
   git add -A && git commit -m "Daily report $(TZ=Asia/Seoul date +%F)" && git push origin main
   ```
7. 라이브 확인 (Pages 반영까지 1~2분 대기, 최대 5분 재시도)
   ```sh
   curl -fsS "https://trade-brief-kr.github.io/trade-brief/data/report.json?v=$(date +%s)" | python3 -c "import json,sys;print(json.load(sys.stdin)['date'])"
   curl -fsS "https://trade-brief-kr.github.io/trade-brief/data/archive/index.json?v=$(date +%s)" | python3 -c "import json,sys;print(json.load(sys.stdin)[0]['date'])"
   ```
   두 값이 모두 오늘 날짜면 완료. 아니면 `gh run list -R trade-brief-kr/trade-brief -L 3`으로 Pages 배포 상태를 확인하고 보고한다.

## 보고 형식
성공: 날짜, Top Issues 5개 제목 요약, 소관과별 이슈 수, 링크 https://trade-brief-kr.github.io/trade-brief/
실패: 실패 단계, 오류 메시지, 게시하지 않았다는 사실.
