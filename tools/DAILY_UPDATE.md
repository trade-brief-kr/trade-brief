# 일일 업데이트 절차 (매일 08:00 KST 예약 실행용)

작업 디렉터리: `/workspace/trade-brief` (원격 `main`, GitHub Pages가 `main /`에서 배포). `gh`는 `trade-brief-kr`로 로그인되어 있음.

## 원칙 (반드시 지킬 것)
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
2. `tools/research_prompt.md`를 끝까지 읽고 그 기준을 그대로 따른다 (매체 우선순위, 필수 이슈, 소관과·국가 분류, 카테고리 6종, 명사형 종결, 기사 워딩 인용).
3. 웹 검색으로 조사한다. 항목마다 기사 URL·매체·게시 시각을 확인하고, 기간 밖이거나 확인이 안 되면 버린다. 같은 사안은 하나의 이슈로 통합한다.
4. `data/report.json`을 새로 쓴다 (형식은 `README.md`의 "report.json 전체 형식").
   - `date`: 오늘 KST `YYYY-MM-DD`
   - `generatedAt`: 실제 작성 시각, 예 `2026-11-01T08:05:00+09:00`
   - `coverage`: 예 `2026-10-31 08:00 ~ 2026-11-01 08:00 KST 보도 기준 (최근 24시간, 러시아 한국 관련 이슈 48시간)`
   - `topIssues` 정확히 5개, 모든 bullet에 `source`, 가능하면 `url`
   - `departments`: `cis`, `neasia`, `india`, `asean`, `mea` 순서. 이슈가 없는 과는 `issues: []`
   - `reports`: 조건(3~4일 내 PDF)을 만족하는 것만, 없으면 `[]`
   - `notes`: 확인 못 한 부분 등 투명성 안내 (선택)
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
