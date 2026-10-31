#!/usr/bin/env python3
"""국가 정보 탭용 통계 수집기.

출처
  - World Bank Open Data API (CC BY 4.0): GDP, 1인당 GDP, 인플레이션
  - BIS Central bank policy rates (WS_CBPOL): 정책금리
  - 관세청 국가별 수출입실적(GW) (공공데이터포털): 한국과의 교역, 월별
    인증키는 환경변수 DATA_GO_KR_SERVICE_KEY 에서만 읽고 출력·저장하지 않는다.
  - UN Comtrade 무료 미리보기 API: 관세청 접속이 안 될 때의 한국 보고 기준 교역 대체값

생성 파일: data/country-stats.json, data/country-stats.js (file:// 직접 열기용)

사용법
  python3 tools/fetch_country_stats.py              # 전체 수집
  python3 tools/fetch_country_stats.py --skip-customs
  python3 tools/fetch_country_stats.py --only-customs  # 기존 파일에 관세청 값만 갱신
  python3 tools/fetch_country_stats.py --customs-file data/customs-kr.json
      # 관세청 API 대신 국내 PC(tools/fetch_customs.ps1)에서 만든 파일을 병합
      # (tools/merge_customs.py 와 같은 로직. 관세청 값이 UN Comtrade 보다 우선)

수집에 실패한 항목은 직전 파일의 값(원래 기준시점 포함)을 유지하고,
직전 값도 없으면 null 로 둔다. 추정치나 가공된 숫자는 넣지 않는다.
"""
import argparse
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_customs import load_customs_file, merge as merge_customs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / 'data' / 'country-stats.json'
OUT_JS = ROOT / 'data' / 'country-stats.js'
KST = timezone(timedelta(hours=9))
USER_AGENT = 'trade-brief-stats/1.0 (+internal briefing; python-urllib)'

DEPARTMENTS = [
    {'id': 'cis', 'name': '통상협력총괄과'},
    {'id': 'neasia', 'name': '동북아통상과'},
    {'id': 'india', 'name': '인도통상협력과'},
    {'id': 'asean', 'name': '아주통상과'},
    {'id': 'mea', 'name': '중동아프리카통상과'},
]

# (ISO2, ISO3, 한국어명, 소관과, 하위 그룹, 중앙은행명, 중앙은행 URL)
COUNTRIES = [
    ('RU', 'RUS', '러시아', 'cis', '', '러시아 중앙은행', 'https://www.cbr.ru/eng/'),
    ('UA', 'UKR', '우크라이나', 'cis', '', '우크라이나 국립은행', 'https://bank.gov.ua/en/'),
    ('KZ', 'KAZ', '카자흐스탄', 'cis', '', '카자흐스탄 국립은행', 'https://nationalbank.kz/en'),
    ('TM', 'TKM', '투르크메니스탄', 'cis', '', '투르크메니스탄 중앙은행', 'https://www.cbt.tm/'),
    ('UZ', 'UZB', '우즈베키스탄', 'cis', '', '우즈베키스탄 중앙은행', 'https://cbu.uz/en/'),
    ('AZ', 'AZE', '아제르바이잔', 'cis', '', '아제르바이잔 중앙은행', 'https://www.cbar.az/'),
    ('AM', 'ARM', '아르메니아', 'cis', '', '아르메니아 중앙은행', 'https://www.cba.am/en'),
    ('MN', 'MNG', '몽골', 'cis', '', '몽골 중앙은행', 'https://www.mongolbank.mn/en'),
    ('KG', 'KGZ', '키르기스스탄', 'cis', '', '키르기스스탄 국립은행', 'https://www.nbkr.kg/'),
    ('TJ', 'TJK', '타지키스탄', 'cis', '', '타지키스탄 국립은행', 'https://nbt.tj/en/'),
    ('GE', 'GEO', '조지아', 'cis', '', '조지아 국립은행', 'https://nbg.gov.ge/en'),
    ('MD', 'MDA', '몰도바', 'cis', '', '몰도바 국립은행', 'https://www.bnm.md/en'),
    ('BY', 'BLR', '벨라루스', 'cis', '', '벨라루스 국립은행', 'https://www.nbrb.by/engl'),
    ('CN', 'CHN', '중국', 'neasia', '', '중국인민은행', 'http://www.pbc.gov.cn/en/'),
    ('JP', 'JPN', '일본', 'neasia', '', '일본은행', 'https://www.boj.or.jp/en/'),
    ('HK', 'HKG', '홍콩', 'neasia', '', '홍콩금융관리국', 'https://www.hkma.gov.hk/eng/'),
    ('TW', 'TWN', '대만', 'neasia', '', '대만 중앙은행', 'https://www.cbc.gov.tw/en/'),
    ('IN', 'IND', '인도', 'india', '', '인도 중앙은행(RBI)', 'https://www.rbi.org.in/'),
    ('PK', 'PAK', '파키스탄', 'india', '서남아', '파키스탄 중앙은행', 'https://www.sbp.org.pk/'),
    ('BD', 'BGD', '방글라데시', 'india', '서남아', '방글라데시 중앙은행', 'https://www.bb.org.bd/en/'),
    ('LK', 'LKA', '스리랑카', 'india', '서남아', '스리랑카 중앙은행', 'https://www.cbsl.gov.lk/en'),
    ('NP', 'NPL', '네팔', 'india', '서남아', '네팔 중앙은행', 'https://www.nrb.org.np/'),
    ('BT', 'BTN', '부탄', 'india', '서남아', '부탄 왕립통화청', 'https://www.rma.org.bt/'),
    ('MV', 'MDV', '몰디브', 'india', '서남아', '몰디브 통화청', 'https://www.mma.gov.mv/'),
    ('AF', 'AFG', '아프가니스탄', 'india', '서남아', '아프가니스탄 중앙은행', 'https://dab.gov.af/'),
    ('PH', 'PHL', '필리핀', 'asean', '', '필리핀 중앙은행', 'https://www.bsp.gov.ph/'),
    ('SG', 'SGP', '싱가포르', 'asean', '', '싱가포르 통화청(MAS)', 'https://www.mas.gov.sg/'),
    ('ID', 'IDN', '인도네시아', 'asean', '', '인도네시아 중앙은행', 'https://www.bi.go.id/en/'),
    ('MY', 'MYS', '말레이시아', 'asean', '', '말레이시아 중앙은행', 'https://www.bnm.gov.my/'),
    ('VN', 'VNM', '베트남', 'asean', '', '베트남 국가은행', 'https://www.sbv.gov.vn/'),
    ('LA', 'LAO', '라오스', 'asean', '', '라오스 중앙은행', 'https://www.bol.gov.la/'),
    ('TH', 'THA', '태국', 'asean', '기타 아세안', '태국 중앙은행', 'https://www.bot.or.th/en/'),
    ('KH', 'KHM', '캄보디아', 'asean', '기타 아세안', '캄보디아 국립은행', 'https://www.nbc.gov.kh/'),
    ('MM', 'MMR', '미얀마', 'asean', '기타 아세안', '미얀마 중앙은행', 'https://www.cbm.gov.mm/'),
    ('BN', 'BRN', '브루나이', 'asean', '기타 아세안', '브루나이 중앙은행', 'https://www.bdcb.gov.bn/'),
    ('TL', 'TLS', '동티모르', 'asean', '기타 아세안', '동티모르 중앙은행', 'https://www.bancocentral.tl/'),
    ('AE', 'ARE', 'UAE', 'mea', '', 'UAE 중앙은행', 'https://www.centralbank.ae/en/'),
    ('KW', 'KWT', '쿠웨이트', 'mea', '', '쿠웨이트 중앙은행', 'https://www.cbk.gov.kw/en'),
    ('EG', 'EGY', '이집트', 'mea', '', '이집트 중앙은행', 'https://www.cbe.org.eg/en'),
    ('SA', 'SAU', '사우디', 'mea', '', '사우디 중앙은행(SAMA)', 'https://www.sama.gov.sa/en-US/'),
    ('IR', 'IRN', '이란', 'mea', '', '이란 중앙은행', 'https://www.cbi.ir/default_en.aspx'),
    ('IL', 'ISR', '이스라엘', 'mea', '', '이스라엘 중앙은행', 'https://www.boi.org.il/en/'),
    ('QA', 'QAT', '카타르', 'mea', '기타 중동·아프리카', '카타르 중앙은행', 'https://www.qcb.gov.qa/en/'),
    ('OM', 'OMN', '오만', 'mea', '기타 중동·아프리카', '오만 중앙은행', 'https://cbo.gov.om/'),
    ('BH', 'BHR', '바레인', 'mea', '기타 중동·아프리카', '바레인 중앙은행', 'https://www.cbb.gov.bh/'),
    ('IQ', 'IRQ', '이라크', 'mea', '기타 중동·아프리카', '이라크 중앙은행', 'https://cbi.iq/'),
    ('JO', 'JOR', '요르단', 'mea', '기타 중동·아프리카', '요르단 중앙은행', 'https://www.cbj.gov.jo/'),
    ('TR', 'TUR', '튀르키예', 'mea', '기타 중동·아프리카', '튀르키예 중앙은행', 'https://www.tcmb.gov.tr/'),
    ('ZA', 'ZAF', '남아프리카공화국', 'mea', '기타 중동·아프리카', '남아공 준비은행', 'https://www.resbank.co.za/'),
    ('NG', 'NGA', '나이지리아', 'mea', '기타 중동·아프리카', '나이지리아 중앙은행', 'https://www.cbn.gov.ng/'),
    ('KE', 'KEN', '케냐', 'mea', '기타 중동·아프리카', '케냐 중앙은행', 'https://www.centralbank.go.ke/'),
    ('ET', 'ETH', '에티오피아', 'mea', '기타 중동·아프리카', '에티오피아 국립은행', 'https://nbe.gov.et/'),
    ('MA', 'MAR', '모로코', 'mea', '기타 중동·아프리카', '모로코 중앙은행', 'https://www.bkam.ma/en'),
    ('DZ', 'DZA', '알제리', 'mea', '기타 중동·아프리카', '알제리 중앙은행', 'https://www.bank-of-algeria.dz/'),
]

WB_INDICATORS = {
    'gdp': 'NY.GDP.MKTP.CD',
    'gdpPerCapita': 'NY.GDP.PCAP.CD',
    'inflation': 'FP.CPI.TOTL.ZG',
}
WB_LICENSE = 'CC BY 4.0'
BIS_URL = 'https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.?lastNObservations=45&format=csv'
BIS_PAGE = 'https://data.bis.org/topics/CBPOL'
CUSTOMS_URL = 'https://apis.data.go.kr/1220000/nationtrade/getNationtradeList'
CUSTOMS_PAGE = 'https://www.data.go.kr/data/15101612/openapi.do'
COMTRADE_BASE = 'https://comtradeapi.un.org/public/v1'
COMTRADE_PAGE = 'https://comtradeplus.un.org/'
KOREA_M49 = 410
# UN Comtrade 는 대만을 별도 코드로 표기하지 않고 'Other Asia, nes'(490)로 집계한다.
COMTRADE_SPECIAL = {'TW': 490}


def log(message):
    print(message, file=sys.stderr)


def now_kst():
    return datetime.now(KST).replace(microsecond=0)


def http_get(url, timeout=40, retries=3, pause=2.0):
    """GET 요청. 실패 시 몇 번 재시도한다. 오류 메시지에 URL(인증키 포함 가능)을 넣지 않는다."""
    last = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': '*/*'})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            last = f'HTTP {error.code}'
        except Exception as error:  # 연결·TLS·시간 초과
            last = type(error).__name__ + (f': {error.reason}' if hasattr(error, 'reason') else '')
        time.sleep(pause * (attempt + 1))
    raise RuntimeError(last or 'unknown error')


def http_json(url, **kwargs):
    body = http_get(url, **kwargs)
    try:
        return json.loads(body)
    except ValueError:
        raise RuntimeError('JSON 아님(차단 페이지 가능)')


# ---------------------------------------------------------------- World Bank

def fetch_world_bank(iso3, iso2, indicator):
    url = f'https://api.worldbank.org/v2/country/{iso3}/indicator/{indicator}?format=json&per_page=100'
    data = http_json(url)
    rows = data[1] if isinstance(data, list) and len(data) > 1 and data[1] else []
    for row in rows:  # 최신 연도부터 내려온다
        if row.get('value') is not None:
            return {
                'value': row['value'],
                'year': row['date'],
                'source': 'World Bank',
                'license': WB_LICENSE,
                'url': f'https://data.worldbank.org/indicator/{indicator}?locations={iso2}',
            }
    return {'value': None, 'source': 'World Bank', 'url': f'https://data.worldbank.org/indicator/{indicator}?locations={iso2}',
            'note': 'World Bank 미수록'}


def world_bank_item(row, indicator, iso2):
    url = f'https://data.worldbank.org/indicator/{indicator}?locations={iso2}'
    if row:
        return {'value': row['value'], 'year': row['date'], 'source': 'World Bank', 'license': WB_LICENSE, 'url': url}
    return {'value': None, 'source': 'World Bank', 'url': url, 'note': 'World Bank 미수록'}


def fetch_world_bank_bulk(indicator):
    """전체 국가·전체 연도를 한 번에 받아 국가별 최신 유효값(ISO3 → row)을 돌려준다."""
    url = f'https://api.worldbank.org/v2/country/all/indicator/{indicator}?format=json&per_page=20000'
    data = http_json(url, timeout=90, retries=5, pause=3.0)
    if not (isinstance(data, list) and len(data) > 1 and isinstance(data[1], list)):
        raise RuntimeError('형식 오류')
    if data[0].get('pages', 1) != 1:
        raise RuntimeError('페이지 분할 응답')
    latest = {}
    for row in data[1]:
        iso3 = row.get('countryiso3code')
        if not iso3 or row.get('value') is None:
            continue
        if iso3 not in latest or row['date'] > latest[iso3]['date']:
            latest[iso3] = row
    return latest


# ---------------------------------------------------------------- BIS

def fetch_bis_rates():
    text = http_get(BIS_URL, timeout=60).decode('utf-8-sig')
    latest = {}
    for row in csv.DictReader(io.StringIO(text)):
        value = (row.get('OBS_VALUE') or '').strip()
        if not value or value.lower() == 'nan':
            continue
        area, period = row.get('REF_AREA'), row.get('TIME_PERIOD')
        if area not in latest or period > latest[area]['date']:
            latest[area] = {'value': float(value), 'date': period}
    return latest


# ---------------------------------------------------------------- UN Comtrade

def comtrade_partner_codes():
    data = http_json(f'{COMTRADE_BASE.replace("/public/v1", "")}/files/v1/app/reference/partnerAreas.json')
    by_iso3 = {}
    for row in data.get('results', []):
        if row.get('isGroup') or row.get('entryExpiredDate'):
            continue
        iso3 = row.get('PartnerCodeIsoAlpha3')
        if iso3:
            by_iso3[iso3] = int(row['id'])
    return by_iso3


def comtrade_latest_period(freq):
    data = http_json(f'{COMTRADE_BASE}/getDA/C/{freq}/HS?reporterCode={KOREA_M49}')
    periods = [str(row['period']) for row in data.get('data', []) if row.get('period')]
    return max(periods) if periods else None


def comtrade_values(freq, period, partner_codes):
    query = urllib.parse.urlencode({
        'reporterCode': KOREA_M49,
        'partnerCode': ','.join(str(code) for code in sorted(set(partner_codes))),
        'period': period,
        'flowCode': 'X,M',
        'cmdCode': 'TOTAL',
        'customsCode': 'C00',
        'motCode': 0,
        'partner2Code': 0,
    })
    data = http_json(f'{COMTRADE_BASE}/preview/C/{freq}/HS?{query}', timeout=60)
    if data.get('error'):
        raise RuntimeError(str(data['error'])[:120])
    values = {}
    for row in data.get('data', []):
        flow = 'exports' if row.get('flowCode') == 'X' else 'imports' if row.get('flowCode') == 'M' else None
        if flow and row.get('primaryValue') is not None:
            values.setdefault(int(row['partnerCode']), {})[flow] = float(row['primaryValue'])
    return values


def fmt_period(freq, period):
    return period if freq == 'A' else f'{period[:4]}-{period[4:6]}'


def trade_record(values, period_label):
    if not values or 'exports' not in values or 'imports' not in values:
        return None
    return {
        'period': period_label,
        'exports': values['exports'],
        'imports': values['imports'],
        'balance': values['exports'] - values['imports'],
    }


def fetch_comtrade(countries):
    codes_by_iso3 = comtrade_partner_codes()
    code_of = {}
    for c in countries:
        code = COMTRADE_SPECIAL.get(c['iso2']) or codes_by_iso3.get(c['iso3'])
        if code:
            code_of[c['iso2']] = code
    result = {'annual': {}, 'monthly': {}}
    meta = {}
    for freq, key in (('A', 'annual'), ('M', 'monthly')):
        time.sleep(1.5)
        period = comtrade_latest_period(freq)
        meta[key] = fmt_period(freq, period) if period else None
        if not period:
            continue
        time.sleep(1.5)
        values = comtrade_values(freq, period, code_of.values())
        for iso2, code in code_of.items():
            record = trade_record(values.get(code), fmt_period(freq, period))
            if record:
                result[key][iso2] = record
    return result, meta, code_of


# ---------------------------------------------------------------- 관세청

def customs_query(key, iso2, start, end):
    query = urllib.parse.urlencode({'serviceKey': key, 'strtYymm': start, 'endYymm': end, 'cntyCd': iso2})
    # 인증키가 포함된 URL은 절대 로그에 남기지 않는다.
    body = http_get(f'{CUSTOMS_URL}?{query}', timeout=20, retries=2)
    root = ET.fromstring(body)
    code = (root.findtext('.//resultCode') or '').strip()
    if code and code not in ('00', '0'):
        raise RuntimeError(f'resultCode {code}: {(root.findtext(".//resultMsg") or "").strip()[:80]}')
    rows = []
    for item in root.iter('item'):
        period = (item.findtext('year') or '').strip()
        if len(period) != 7 or period[4] != '.':
            continue  # '총계' 행 등 제외
        try:
            rows.append({
                'period': period.replace('.', '-'),
                'exports': float(item.findtext('expDlr') or 0),
                'imports': float(item.findtext('impDlr') or 0),
                'balance': float(item.findtext('balPayments') or 0),
            })
        except ValueError:
            continue
    return rows


def customs_probe():
    """인증키 없이 서버 연결 가능 여부만 확인한다."""
    try:
        http_get(CUSTOMS_URL, timeout=15, retries=1)
        return True, '연결 가능'
    except RuntimeError as error:
        message = str(error)
        if message.startswith('HTTP'):
            return True, f'연결 가능({message})'
        return False, message


def fetch_customs(countries):
    key = os.environ.get('DATA_GO_KR_SERVICE_KEY', '').strip()
    if not key:
        return {}, {'status': 'no_key', 'message': '환경변수 DATA_GO_KR_SERVICE_KEY 없음'}
    reachable, message = customs_probe()
    if not reachable:
        return {}, {'status': 'unreachable', 'message': f'apis.data.go.kr 연결 실패({message})'}
    today = now_kst().date()
    last_year = today.year - 1
    data, errors = {}, 0
    for c in countries:
        try:
            prev = customs_query(key, c['iso2'], f'{last_year}01', f'{last_year}12')
            time.sleep(0.3)
            this = customs_query(key, c['iso2'], f'{today.year}01', f'{today.year}12')
            time.sleep(0.3)
        except Exception as error:
            errors += 1
            log(f'  관세청 {c["name"]}: {error}')
            if errors >= 5 and not data:
                return {}, {'status': 'error', 'message': f'관세청 API 오류 반복({error})'}
            continue
        record = {}
        months = sorted(this + prev, key=lambda r: r['period'])
        if months:
            record['monthly'] = months[-1]
        if len(prev) == 12:
            record['annual'] = {
                'period': str(last_year),
                'exports': sum(r['exports'] for r in prev),
                'imports': sum(r['imports'] for r in prev),
                'balance': sum(r['balance'] for r in prev),
            }
        if record:
            data[c['iso2']] = record
    return data, {'status': 'ok', 'message': f'{len(data)}개국 수집'}


# ---------------------------------------------------------------- 조립

def load_previous():
    try:
        return json.loads(OUT_JSON.read_text(encoding='utf-8'))
    except Exception:
        return {}


def previous_country(previous, iso2):
    for c in previous.get('countries', []):
        if c.get('id') == iso2:
            return c
    return {}


def build(args):
    previous = load_previous()
    countries = [
        {'iso2': i2, 'iso3': i3, 'name': name, 'dept': dept, 'group': group, 'bankName': bank, 'bankUrl': bank_url}
        for i2, i3, name, dept, group, bank, bank_url in COUNTRIES
    ]
    status = {}

    # World Bank: 지표별 전체 국가 일괄 조회(요청 3회), 실패한 지표만 국가별로 재조회
    wb = {}
    if not args.only_customs:
        failures = 0
        for field, indicator in WB_INDICATORS.items():
            try:
                bulk = fetch_world_bank_bulk(indicator)
            except RuntimeError as error:
                log(f'  World Bank 일괄 {indicator}: {error} → 국가별 조회')
                bulk = None
            for c in countries:
                if bulk is not None:
                    wb[(c['iso2'], field)] = world_bank_item(bulk.get(c['iso3']), indicator, c['iso2'])
                    continue
                try:
                    wb[(c['iso2'], field)] = fetch_world_bank(c['iso3'], c['iso2'], indicator)
                except RuntimeError as error:
                    failures += 1
                    log(f'  World Bank {c["name"]} {indicator}: {error}')
                time.sleep(0.25)
        status['worldBank'] = {'status': 'ok' if not failures else 'partial', 'failures': failures}

    # BIS
    bis = None
    if not args.only_customs:
        try:
            bis = fetch_bis_rates()
            status['bis'] = {'status': 'ok', 'countries': len(bis)}
        except RuntimeError as error:
            status['bis'] = {'status': 'error', 'message': str(error)}

    # UN Comtrade
    comtrade, comtrade_meta = None, {}
    if not args.only_customs:
        try:
            comtrade, comtrade_meta, _ = fetch_comtrade(countries)
            status['comtrade'] = {'status': 'ok', **comtrade_meta}
        except RuntimeError as error:
            status['comtrade'] = {'status': 'error', 'message': str(error)}

    # 관세청
    customs = {}
    customs_file_meta = None
    prev_customs_status = previous.get('status', {}).get('customs', {})
    if args.customs_file:
        customs_file_meta = load_customs_file(args.customs_file)
        status['customs'] = {'status': 'pending'}
    elif args.skip_customs:
        status['customs'] = prev_customs_status or {'status': 'skipped'}
    else:
        customs, status['customs'] = fetch_customs(countries)
        # 키가 없거나 해외 IP라 실패해도, 직전에 PC 파일로 병합한 상태라면 그 상태를 유지
        if status['customs']['status'] != 'ok' and prev_customs_status.get('source') == 'file':
            status['customs'] = {**prev_customs_status, 'apiAttempt': status['customs']}
    status['customs']['checkedAt'] = now_kst().isoformat()

    out_countries = []
    for c in countries:
        prev = previous_country(previous, c['iso2'])
        entry = {
            'id': c['iso2'], 'iso3': c['iso3'], 'name': c['name'], 'dept': c['dept'],
            'group': c['group'], 'centralBank': {'name': c['bankName'], 'url': c['bankUrl']},
        }
        for field in WB_INDICATORS:
            fresh = wb.get((c['iso2'], field))
            entry[field] = fresh or prev.get(field) or {
                'value': None, 'source': 'World Bank',
                'url': f'https://data.worldbank.org/indicator/{WB_INDICATORS[field]}',
            }

        if bis is None:
            entry['policyRate'] = prev.get('policyRate') or {'value': None, 'source': 'BIS', 'url': BIS_PAGE}
        elif c['iso2'] in bis:
            entry['policyRate'] = {**bis[c['iso2']], 'unit': '%', 'source': 'BIS', 'url': BIS_PAGE}
        else:
            entry['policyRate'] = {'value': None, 'source': 'BIS', 'url': BIS_PAGE, 'note': 'BIS 미수록'}

        trade = {}
        if c['iso2'] in customs:
            trade['customs'] = {**customs[c['iso2']], 'source': '관세청 수출입무역통계', 'url': CUSTOMS_PAGE}
        elif prev.get('trade', {}).get('customs'):
            trade['customs'] = prev['trade']['customs']
        if comtrade is not None:
            annual = comtrade['annual'].get(c['iso2'])
            monthly = comtrade['monthly'].get(c['iso2'])
            if annual or monthly:
                trade['comtrade'] = {
                    'annual': annual, 'monthly': monthly,
                    'source': 'UN Comtrade (한국 보고 기준)', 'url': COMTRADE_PAGE,
                }
                if c['iso2'] in COMTRADE_SPECIAL:
                    trade['comtrade']['note'] = "UN Comtrade 'Other Asia, nes'(코드 490) 기준. 대만으로 집계되는 항목"
        elif prev.get('trade', {}).get('comtrade'):
            trade['comtrade'] = prev['trade']['comtrade']
        entry['trade'] = trade
        out_countries.append(entry)

    result = {
        'generatedAt': now_kst().isoformat(),
        'departments': DEPARTMENTS,
        'status': status,
        'sources': {
            'worldBank': {'name': 'World Bank Open Data', 'license': WB_LICENSE, 'url': 'https://data.worldbank.org/'},
            'bis': {'name': 'BIS Central bank policy rates', 'url': BIS_PAGE,
                    'terms': 'https://www.bis.org/terms_conditions.htm'},
            'customs': {'name': '관세청 국가별 수출입실적(GW)', 'url': CUSTOMS_PAGE, 'license': '이용허락범위 제한 없음'},
            'comtrade': {'name': 'UN Comtrade Database', 'url': COMTRADE_PAGE,
                         'terms': 'https://uncomtrade.org/docs/terms-and-conditions/'},
        },
        'countries': out_countries,
    }
    if customs_file_meta is not None:
        data, meta = customs_file_meta
        merged, unknown = merge_customs(result, data, meta, Path(args.customs_file).name)
        log(f'  관세청 파일 병합: {merged}개국, 최근 월 {meta.get("latestPeriod")}'
            + (f', 알 수 없는 코드 {unknown}' if unknown else ''))
    return result


def write(data):
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    OUT_JSON.write_text(text + '\n', encoding='utf-8')
    OUT_JS.write_text('window.COUNTRY_STATS = ' + text + ';\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--skip-customs', action='store_true', help='관세청 수집을 건너뜀(직전 값 유지)')
    parser.add_argument('--only-customs', action='store_true', help='관세청 값만 갱신하고 나머지는 직전 값 유지')
    parser.add_argument('--customs-file', metavar='PATH',
                        help='관세청 API 대신 PC에서 만든 customs-kr.json 을 병합(관세청 값 우선)')
    args = parser.parse_args()
    data = build(args)
    write(data)
    s = data['status']
    log('완료: ' + json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
