# 글로벌 통상 브리프

한국 통상 담당자를 위한 한국어 일일 통상·정책 뉴스 브리프입니다. HTML/CSS/바닐라 JavaScript만 사용하며 빌드, 서버, 외부 폰트와 CDN이 필요 없습니다.

## 파일 구성

- `index.html`: 보고서 화면, 개인화 선택, 국가 정보 준비 화면
- `assets/style.css`: 반응형 화면 및 인쇄 스타일
- `assets/app.js`: 데이터 로딩, 부서·국가 정렬, 텍스트 복사
- `data/sample-report.json`: 실제 뉴스·통계를 포함하지 않은 작은 형식 예제
- `data/report.json`: 별도 자동화가 생성하는 실제 보고서 (이 프로젝트에서 생성하지 않음)
- `data/report.js`: Python 도구가 실제 JSON으로 생성하는 파일 직접 열기용 대체 데이터
- `tools/build_report_js.py`: 표준 라이브러리만 사용하는 데이터 검증·변환 도구 (`data/report.js`만 생성)
- `tools/publish_daily.py`: 일일 게시 명령. 검증 → `data/archive/<날짜>.json/.js` 저장 → `data/archive/index.json/.js` 재생성 → `data/report.js` 재생성
- `data/archive/`: 날짜별 보고서 보관함. `index.json`은 최신순 `{date, topIssueHeadline, keywords}` 목록
- `tools/DAILY_UPDATE.md`: 매일 08:00 KST 예약 실행 절차
- `tools/run_codex_research.sh`: ChatGPT(Codex CLI, 웹검색)로 오늘자 `data/report.json`을 작성하는 조사 러너 (게시 안 함, 종료 코드 0일 때만 `publish_daily.py` 진행)
- `tools/verify_report.py`: 러너 후처리. 게시일 기간·출처 URL(curl) 재확인, 실패 항목 제거, 검증된 Top Issues 5개 미만이면 중단
- `tools/research_prompt.md`: 사용자 조사 프롬프트 원문 (수정 금지)
- `tools/fetch_customs.ps1`: 국내 Windows PC용 관세청 수집 스크립트(파이썬 불필요) → `data/customs-kr.json`
- `tools/merge_customs.py`: `customs-kr.json`을 `data/country-stats.json/js`에 병합

## 로컬에서 열기

`index.html`을 더블클릭하거나 이 디렉터리에서 `python3 -m http.server`를 실행한 뒤 `http://localhost:8000`에 접속합니다. 직접 열기에서는 브라우저의 파일 접근 제한 때문에 `data/report.js`가 필요합니다. 실제 데이터를 준비한 뒤 다음 명령으로 생성합니다.

```sh
python3 tools/build_report_js.py
```

먼저 `data/report.json?v=현재시각`을 fetch하고 실패·형식 오류 시 `window.REPORT_DATA`로 대체합니다. `index.html`의 `data/report.js` 스크립트가 해당 전역 값을 제공합니다. 두 데이터가 모두 없으면 친절한 한국어 오류 카드를 표시합니다. 샘플은 자동으로 표시하지 않습니다. JSON과 JS를 같은 업데이트에 함께 배포해야 최신 데이터가 일치합니다.

## report.json 전체 형식

아래는 구조 예제이며 실제 뉴스가 아닙니다. URL은 선택 사항이므로 생략했습니다.

```json
{
  "date": "2026-10-31",
  "generatedAt": "2026-10-31T08:00:00+09:00",
  "coverage": "샘플 수집 범위",
  "topIssues": [
    {"text": "샘플 주요 이슈 문장", "source": "샘플 출처"},
    {"text": "샘플 주요 이슈 문장", "source": "샘플 출처"},
    {"text": "샘플 주요 이슈 문장", "source": "샘플 출처"},
    {"text": "샘플 주요 이슈 문장", "source": "샘플 출처"},
    {"text": "샘플 주요 이슈 문장", "source": "샘플 출처"}
  ],
  "departments": [
    {"id": "cis", "name": "통상협력총괄과", "issues": [
      {"countries": ["러시아"], "category": "정책·규제", "title": "샘플 이슈 제목",
       "bullets": [{"text": "샘플 핵심 내용", "source": "샘플 출처"}]}
    ]}
  ],
  "reports": [
    {"org": "샘플 기관", "title": "샘플 보고서 제목", "date": "2026-10-29",
     "department": "cis", "countries": ["러시아"]}
  ],
  "notes": ["형식 설명용 샘플입니다."]
}
```

| 필드 | 형식·규칙 |
| --- | --- |
| `date` | KST 보고 날짜, `YYYY-MM-DD` |
| `generatedAt` | 시간대 오프셋이 있는 ISO 8601 생성 시각. 화면은 KST로 변환 |
| `coverage` | 수집 구간 자유 텍스트. 예: 전일 08:00 ~ 당일 08:00 KST (최근 24시간) |
| `topIssues` | 정확히 5개. 각 항목은 한 문장 `text`, 출처 `source`, 선택적 `url` |
| `departments` | 부서 객체 배열. `id`, `name`, `issues` 필요. 중복 ID 금지 |
| `departments[].issues` | 이슈 배열. 비어 있어도 부서 제목과 “금일 반영 이슈 없음” 표시. 누락 부서도 기본 제목 표시 |
| `issues[].countries` | 국가명 문자열 배열 |
| `issues[].category` | 아래 6개 카테고리 중 하나 |
| `issues[].title` | 이슈 제목 문자열 |
| `issues[].bullets` | 하나 이상의 핵심 내용. 각 항목은 `text`, `source` 필수, `url` 선택 |
| `reports` | 보고서 배열. 빈 배열이면 보고서 영역 숨김 |
| `reports[].org`, `title` | 기관명과 보고서 제목 |
| `reports[].date` | 발간일 `YYYY-MM-DD` |
| `reports[].department`, `countries` | 알려진 부서 ID와 국가명 배열 |
| `reports[].url` | 선택적 PDF 링크 |
| `notes` | 선택적 투명성 안내 문자열 배열. 화면 하단에 작게 표시 |

URL은 생략하거나 빈 문자열로 둘 수 있습니다. 제공 시 `http` 또는 `https` 주소여야 하며 출처는 새 탭 링크(`rel="noopener noreferrer"`)로 표시합니다. URL이 없으면 일반 출처 텍스트로 표시합니다. 보고서는 **최근 3~4일 이내 발간되었고 PDF가 확인된 경우에만** 수집 자동화에서 포함하세요. 발간 시점과 실제 PDF 여부는 생성 도구가 네트워크로 확인하지 않으므로 수집 단계의 책임입니다.

카테고리: `국제·외교`, `정책·규제`, `경제동향`, `산업동향`, `대외교역`, `중동정세`.

### 부서 기본 순서와 국가 선택지

| ID | 부서명 | 국가·그룹 |
| --- | --- | --- |
| `cis` | 통상협력총괄과 | 러시아, 우크라이나, 카자흐스탄, 투르크메니스탄, 우즈베키스탄, 아제르바이잔, 아르메니아, 몽골, 키르기스스탄, 타지키스탄, 조지아, 몰도바, 벨라루스 |
| `neasia` | 동북아통상과 | 중국, 일본, 홍콩, 대만 |
| `india` | 인도통상협력과 | 인도, 서남아 |
| `asean` | 아주통상과 | 필리핀, 싱가포르, 인도네시아, 말레이시아, 베트남, 라오스, 기타 아세안 |
| `mea` | 중동아프리카통상과 | UAE, 쿠웨이트, 이집트, 사우디, 이란, 이스라엘, 기타 중동·아프리카 |

`assets/app.js`의 `ALIASES`가 파키스탄·방글라데시 등을 서남아, 태국·캄보디아·미얀마·브루나이 등을 기타 아세안, 카타르·오만·이라크·예멘·콩고민주공화국·리비아·튀르키예 등을 기타 중동·아프리카에 연결합니다. 이슈의 국가 중 하나라도 선택 국가 또는 그룹 별칭에 맞으면 해당 이슈를 위로 이동합니다. 새 국가가 추가되면 별칭 목록도 갱신하세요.

### 개인화와 복사

선택은 `localStorage`의 `tradeBrief.prefs`에 `{ "department": "cis", "country": "러시아" }` 형태로 저장합니다. 저장소가 차단되어도 현재 화면 선택은 작동합니다.

- 기본: 부서 기본 순서, 이슈는 JSON 순서.
- 부서만 선택: 선택 부서를 먼저 배치하고 나머지는 기본 순서.
- 국가도 선택: 선택 부서의 일치 이슈를 “★ 국가 관련 이슈”로 이동한 뒤 해당 부서의 나머지 이슈, 다른 부서를 표시. 이슈를 복제하거나 숨기지 않습니다.
- 선택 부서는 강조 테두리로 표시하며 Global Top Issues는 항상 먼저 나옵니다.
- 텍스트 복사는 현재 순서를 따릅니다. 클립보드 접근이 제한되면 기존 복사 방식을 시도하고 실패 시 직접 선택할 텍스트를 제공합니다.
- 인쇄 시 조작 UI를 제외한 일일 보고서를 출력합니다.

테스트용 순수 함수는 `window.TradeBrief.orderSections(data, prefs)`입니다. `{kind: 'country' | 'dept', deptId, issues: [...]}` 배열을 반환하며 입력을 변경하지 않습니다.

## 지난 보고서 보기

상단의 ◀ 이전 / 날짜 선택 / 다음 ▶ 으로 보관된 날짜를 고릅니다. 주소에 `#2026-10-31`처럼 날짜가 붙어 공유할 수 있습니다. 과거 날짜를 보면 "과거 보고서(YYYY.MM.DD)" 안내와 "최신 보고서로" 버튼이 표시되며, 소관과·국가 개인화와 텍스트 복사도 그대로 작동합니다. 키워드 검색은 보관된 모든 날짜의 Global Top Issues와 이슈 제목에서 찾습니다. 파일 직접 열기(file://)에서는 `data/archive/index.js`와 날짜별 `.js`를 대신 읽습니다. 과거 보고서는 자동화가 실제로 게시한 날짜만 존재합니다.

## 일일 업데이트 흐름

자세한 예약 실행 절차는 `tools/DAILY_UPDATE.md`를 따릅니다. 게시 명령은 `python3 tools/publish_daily.py`입니다 (보고 날짜가 오늘 KST가 아니면 실패, `--allow-any-date`로 무시).


1. 매일 **08:00 KST** 자동화가 최근 24시간 뉴스를 수집하고 출처를 확인하여 `data/report.json`을 재생성합니다.
2. `python3 tools/publish_daily.py`를 실행합니다. 5개 주요 이슈, 부서 ID, 카테고리, bullet의 text/source 및 기본 형식을 검증합니다. 오류면 명확한 메시지와 비정상 종료 코드를 반환하고 기존 JS를 유지합니다.
3. 검증에 성공한 JSON, JS, 보관함 파일을 함께 커밋·푸시하여 GitHub Pages 또는 Cloudflare Pages 같은 무료 정적 호스팅에 배포합니다. 별도의 빌드 단계는 필요 없습니다.

GitHub Actions 예약 실행을 사용한다면 cron `0 23 * * *` UTC가 다음 날 **08:00 KST**입니다. 예약 작업은 지연될 수 있으며 실제 수집·커밋·배포 자동화는 이 저장소에 구현되어 있지 않습니다.

## 국가 정보 계획

현재는 GDP, 1인당 GDP, 인플레이션, 금리, 한국과의 교역현황 항목과 `—`만 표시합니다. 수치나 가상 통계는 제공하지 않습니다. 향후 World Bank/IMF 공개 API를 통한 경제 지표, K-stat/관세청을 통한 한국과의 교역현황 연계를 검토합니다. K-stat/관세청 연계에는 계정이 필요하며 아직 구현하지 않았습니다.

## 국가 정보 탭 (통계)

`국가 정보` 탭은 `data/country-stats.json`(파일 직접 열기 시 `data/country-stats.js`)을 읽어 담당국 54개국의 지표 5개를 표시합니다. 값마다 기준연도·기준일과 출처 링크를 붙이고, 출처에 값이 없으면 추정하지 않고 `—`와 `데이터 없음(출처 링크)`로 표시합니다. 바로가기 링크: `index.html?tab=country&country=SA` (ISO 2자리 코드).

| 지표 | 출처 | 비고 |
| --- | --- | --- |
| GDP, 1인당 GDP, 인플레이션 | World Bank API (`NY.GDP.MKTP.CD`, `NY.GDP.PCAP.CD`, `FP.CPI.TOTL.ZG`), CC BY 4.0 | 연간, 최신 유효 연도. 대만은 미수록 |
| 정책금리 | BIS `WS_CBPOL` 일별 정책금리 | BIS 미수록국은 각국 중앙은행 링크 |
| 한국과의 교역 | 1순위 관세청 국가별 수출입실적(GW), 대체 UN Comtrade 무료 미리보기 API(한국 보고 기준) | Comtrade는 공개 시차가 커서 최근 월이 수개월 전일 수 있음. 대만은 Comtrade `Other Asia, nes`(490) 값 |

### 갱신

```sh
python3 tools/fetch_country_stats.py                 # 전체 (약 30~60초)
python3 tools/fetch_country_stats.py --skip-customs  # 관세청 제외
python3 tools/fetch_country_stats.py --only-customs  # 관세청 값만 갱신, 나머지는 기존 파일 유지
```

- 표준 라이브러리만 사용합니다. 출처 호출이 실패한 항목은 직전 파일의 값(원래 기준시점 포함)을 유지합니다.
- 관세청 인증키는 환경변수 `DATA_GO_KR_SERVICE_KEY`로만 전달합니다. 스크립트는 키를 출력·로그·파일에 남기지 않습니다. 키를 파일이나 저장소에 커밋하지 마세요.
- 지표는 월·연 단위로 바뀌므로 매일 1회 실행이면 충분합니다.

### 관세청 API 접속 제한 → 국내 PC에서 수집 후 박스에서 병합

`apis.data.go.kr`은 해외 네트워크에서 TLS 연결이 끊겨 수집되지 않습니다(박스 egress가 미국 IP). 관세청 값은 국내 Windows PC에서 **파이썬 없이** PowerShell 스크립트로 수집합니다.

**1) PC에서 실행 (Windows PowerShell 5.1 이상, 추가 설치 없음)**

1. `tools\fetch_customs.ps1` 파일을 PC의 아무 폴더(예: `바탕화면\trade-brief`)에 둡니다.
2. 시작 메뉴에서 **PowerShell**을 열고 그 폴더로 이동합니다. 예: `cd $HOME\Desktop\trade-brief`
3. 다음을 실행합니다.

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\fetch_customs.ps1
   ```

4. `인증키:` 프롬프트에 공공데이터포털 **일반 인증키**(Encoding/Decoding 어느 쪽이든 가능)를 붙여넣고 Enter. 입력값은 화면에 표시되지 않습니다. 아무것도 입력하지 않고 Enter 를 누르면 환경변수 `DATA_GO_KR_SERVICE_KEY`를 사용합니다.
5. 첫 호출 직후 `인증키 확인: 정상` 또는 실패 사유(미등록 키, 승인 미반영, 호출 한도 초과, 네트워크 차단 등)가 한국어로 표시됩니다. 인증키 오류면 바로 중단하고 파일을 만들지 않습니다. 발급 직후 키는 반영까지 1~2시간 걸릴 수 있습니다.
6. 54개국 × 2회(전년 1~12월, 올해 1월~이번 달) 호출 후 `data\customs-kr.json`(스크립트가 저장소의 `tools` 폴더에 있으면 `..\data\customs-kr.json`)이 생깁니다. 약 1~2분. 이 파일 하나만 박스로 전달합니다. 인증키는 파일·로그·화면에 남지 않습니다.

`customs-kr.json` 형식(`schema: customs-kr/1`, UTF-8 BOM 없음, 단위 USD): 국가별 `monthly`(최근 월), `last12`(최근 연속 12개월 합계, `YYYY-MM~YYYY-MM`), `annual`(전년 1~12월 합계, 12개월이 모두 있을 때만), `months`(조회된 월별 값), 그리고 `generatedAt`, `latestPeriod`, `errors`(국가별 실패 사유).

**2) 박스에서 병합**

```sh
python3 tools/merge_customs.py --customs-file data/customs-kr.json            # country-stats.json/js 갱신
python3 tools/merge_customs.py --customs-file data/customs-kr.json --dry-run  # 검증만
python3 tools/fetch_country_stats.py --customs-file data/customs-kr.json      # 전체 수집 + 같은 병합
```

- 국가별 `trade.customs`에 관세청 값과 출처(`관세청 수출입무역통계`), 기준월(`monthly.period`, `last12.period`, `annual.period`), PC 수집 시각(`fetchedAt`)을 기록합니다. 화면은 관세청 값을 UN Comtrade보다 먼저 표시하고, Comtrade 값은 지우지 않고 빈 칸 대체용으로만 씁니다.
- 파일에 없거나 수집에 실패한 국가는 기존 값을 유지합니다. 인증키로 보이는 필드나 형식 오류가 있으면 병합을 거부합니다.
- 이후 박스에서 키 없이 `fetch_country_stats.py`를 돌려도 PC 파일로 반영한 관세청 상태와 값은 유지됩니다. 관세청 값은 PC에서 다시 수집해야 갱신됩니다(월 1회 정도면 충분).

파이썬이 있는 국내 PC라면 기존 방식(`set DATA_GO_KR_SERVICE_KEY=...` 후 `python tools\fetch_country_stats.py --only-customs`)도 그대로 쓸 수 있습니다.
