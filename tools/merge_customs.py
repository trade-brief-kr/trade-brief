#!/usr/bin/env python3
"""PC에서 만든 관세청 수집 파일(data/customs-kr.json)을 country-stats.json/js 에 병합한다.

관세청 API(apis.data.go.kr)는 해외 IP에서 접속되지 않아, 국내 PC에서
tools/fetch_customs.ps1 로 수집한 파일을 박스로 옮겨 병합한다.

  python3 tools/merge_customs.py --customs-file data/customs-kr.json
  python3 tools/merge_customs.py --customs-file data/customs-kr.json --dry-run

규칙
  - 관세청 값이 UN Comtrade 값보다 우선한다(화면은 trade.customs 를 먼저 표시).
    Comtrade 값은 지우지 않고 그대로 둔다.
  - 각 국가 trade.customs 에 출처·기준월(monthly.period, annual.period, last12.period)과
    PC 수집 시각(fetchedAt)을 기록한다.
  - 파일에 없는 국가는 기존 trade.customs 를 유지한다.
  - 인증키로 보이는 필드(serviceKey 등)가 있으면 병합을 거부한다.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS_JSON = ROOT / 'data' / 'country-stats.json'
STATS_JS = ROOT / 'data' / 'country-stats.js'
KST = timezone(timedelta(hours=9))
CUSTOMS_PAGE = 'https://www.data.go.kr/data/15101612/openapi.do'
CUSTOMS_SOURCE = '관세청 수출입무역통계'
MONTH_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
YEAR_RE = re.compile(r'^\d{4}$')
RANGE_RE = re.compile(r'^\d{4}-\d{2}~\d{4}-\d{2}$')
FORBIDDEN = re.compile(r'servicekey|service_key|authkey|apikey', re.I)


class CustomsFileError(ValueError):
    pass


def _record(value, pattern, where):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CustomsFileError(f'{where}: 객체가 아님')
    period = value.get('period')
    if not isinstance(period, str) or not pattern.match(period):
        raise CustomsFileError(f'{where}.period 형식 오류: {period!r}')
    out = {'period': period}
    for field in ('exports', 'imports', 'balance'):
        number = value.get(field)
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise CustomsFileError(f'{where}.{field} 숫자 아님')
        out[field] = float(number)
    return out


def load_customs_file(path):
    """customs-kr.json 을 읽고 검증해 {iso2: {monthly, annual, last12}} 와 메타를 돌려준다."""
    raw = Path(path).read_bytes()
    if raw.startswith(b'\xef\xbb\xbf'):
        raw = raw[3:]  # BOM 이 붙어 와도 허용
    text = raw.decode('utf-8')
    if FORBIDDEN.search(text):
        raise CustomsFileError('인증키로 보이는 필드가 있어 병합하지 않음')
    doc = json.loads(text)
    if doc.get('schema') != 'customs-kr/1':
        raise CustomsFileError(f'schema 불일치: {doc.get("schema")!r}')
    countries = doc.get('countries')
    if not isinstance(countries, dict) or not countries:
        raise CustomsFileError('countries 비어 있음')
    data = {}
    for iso2, item in countries.items():
        if not re.match(r'^[A-Z]{2}$', iso2) or not isinstance(item, dict):
            raise CustomsFileError(f'국가 코드 형식 오류: {iso2!r}')
        rec = {
            'monthly': _record(item.get('monthly'), MONTH_RE, f'{iso2}.monthly'),
            'annual': _record(item.get('annual'), YEAR_RE, f'{iso2}.annual'),
            'last12': _record(item.get('last12'), RANGE_RE, f'{iso2}.last12'),
        }
        rec = {k: v for k, v in rec.items() if v}
        if rec:
            data[iso2] = rec
    meta = {
        'generatedAt': doc.get('generatedAt'),
        'latestPeriod': doc.get('latestPeriod'),
        'errors': doc.get('errors') or {},
    }
    return data, meta


def merge(stats, customs, meta, file_label):
    """stats(country-stats 구조)를 제자리에서 갱신하고 병합 국가 수를 돌려준다."""
    merged, unknown = 0, sorted(set(customs) - {c.get('id') for c in stats.get('countries', [])})
    for country in stats.get('countries', []):
        rec = customs.get(country.get('id'))
        if not rec:
            continue
        trade = country.setdefault('trade', {})
        trade['customs'] = {
            **rec,
            'source': CUSTOMS_SOURCE,
            'url': CUSTOMS_PAGE,
            'basis': '한국 기준 · 수출 FOB / 수입 CIF · USD',
            'fetchedAt': meta.get('generatedAt'),
            'collectedBy': '국내 PC 수집 파일',
        }
        # 화면은 customs 를 먼저 쓰고 Comtrade 는 빈 칸 대체용으로만 쓴다(우선순위 명시).
        trade['priority'] = ['customs', 'comtrade']
        merged += 1
    stats.setdefault('status', {})['customs'] = {
        'status': 'ok' if merged else 'error',
        'source': 'file',
        'file': file_label,
        'message': f'{merged}개국 반영(국내 PC 수집)' + (f', 실패 {len(meta["errors"])}개국' if meta['errors'] else ''),
        'latestPeriod': meta.get('latestPeriod'),
        'fetchedAt': meta.get('generatedAt'),
        'checkedAt': datetime.now(KST).replace(microsecond=0).isoformat(),
    }
    sources = stats.setdefault('sources', {})
    sources.setdefault('customs', {'name': '관세청 국가별 수출입실적(GW)', 'url': CUSTOMS_PAGE,
                                   'license': '이용허락범위 제한 없음'})
    sources['customs']['latestPeriod'] = meta.get('latestPeriod')
    return merged, unknown


def write_stats(stats, json_path=STATS_JSON, js_path=STATS_JS):
    text = json.dumps(stats, ensure_ascii=False, indent=2)
    Path(json_path).write_text(text + '\n', encoding='utf-8')
    Path(js_path).write_text('window.COUNTRY_STATS = ' + text + ';\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--customs-file', required=True, help='PC에서 만든 customs-kr.json 경로')
    parser.add_argument('--stats-file', default=str(STATS_JSON), help='병합 대상 country-stats.json')
    parser.add_argument('--dry-run', action='store_true', help='검증·요약만 하고 파일은 쓰지 않음')
    args = parser.parse_args()

    stats_json = Path(args.stats_file)
    stats_js = stats_json.with_suffix('.js')
    try:
        customs, meta = load_customs_file(args.customs_file)
    except (OSError, ValueError) as error:
        print(f'관세청 파일 오류: {error}', file=sys.stderr)
        return 2
    stats = json.loads(stats_json.read_text(encoding='utf-8'))
    merged, unknown = merge(stats, customs, meta, Path(args.customs_file).name)
    if unknown:
        print(f'경고: country-stats 에 없는 국가 코드 무시 {unknown}', file=sys.stderr)
    if meta['errors']:
        print(f'참고: PC 수집 실패 국가 {sorted(meta["errors"])} (기존 값 유지)', file=sys.stderr)
    print(f'병합 {merged}개국, 최근 월 {meta.get("latestPeriod")}, 수집 시각 {meta.get("generatedAt")}', file=sys.stderr)
    if not args.dry_run:
        write_stats(stats, stats_json, stats_js)
        print(f'저장: {stats_json.name}, {stats_js.name}', file=sys.stderr)
    return 0 if merged else 1


if __name__ == '__main__':
    sys.exit(main())
