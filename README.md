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
- `tools/research_prompt.md`: 사용자 조사 프롬프트 원문 (수정 금지)

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
