#!/usr/bin/env python3
"""Validate the daily report and create its file:// compatible script."""
import json
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEPARTMENTS = {'cis', 'neasia', 'india', 'asean', 'mea'}
CATEGORIES = {'국제·외교', '정책·규제', '경제동향', '산업동향', '대외교역', '중동정세'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def obj(value, path):
    require(isinstance(value, dict), f'{path}: 객체여야 합니다.')


def string(value, path):
    require(isinstance(value, str) and bool(value.strip()), f'{path}: 비어 있지 않은 문자열이어야 합니다.')


def array(value, path):
    require(isinstance(value, list), f'{path}: 배열이어야 합니다.')


def url(value, path):
    if value is None or value == '':
        return
    string(value, path)
    parsed = urlparse(value)
    require(parsed.scheme in ('http', 'https') and bool(parsed.netloc), f'{path}: http 또는 https URL이어야 합니다.')


def day(value, path):
    string(value, path)
    try:
        parsed = date.fromisoformat(value)
        require(parsed.isoformat() == value, f'{path}: YYYY-MM-DD 형식이어야 합니다.')
    except ValueError:
        raise ValueError(f'{path}: 유효한 YYYY-MM-DD 날짜여야 합니다.') from None


def bullet(value, path):
    obj(value, path)
    string(value.get('text'), path + '.text')
    string(value.get('source'), path + '.source')
    url(value.get('url'), path + '.url')
    # Optional republish / mirror link (kept alongside original url).
    url(value.get('altUrl'), path + '.altUrl')


def countries(value, path):
    array(value, path)
    for i, country in enumerate(value):
        string(country, f'{path}[{i}]')


def validate(data):
    obj(data, 'report')
    day(data.get('date'), 'date')
    string(data.get('generatedAt'), 'generatedAt')
    try:
        timestamp = datetime.fromisoformat(data['generatedAt'])
        require(timestamp.utcoffset() is not None, 'generatedAt: 시간대 오프셋이 필요합니다.')
    except ValueError as error:
        raise ValueError(f'generatedAt: 시간대가 포함된 ISO 8601 날짜·시간이어야 합니다. ({error})') from None
    string(data.get('coverage'), 'coverage')
    array(data.get('topIssues'), 'topIssues')
    require(len(data['topIssues']) == 5, 'topIssues: 정확히 5개여야 합니다.')
    for i, value in enumerate(data['topIssues']):
        bullet(value, f'topIssues[{i}]')
    array(data.get('departments'), 'departments')
    seen = set()
    for i, dept in enumerate(data['departments']):
        path = f'departments[{i}]'
        obj(dept, path)
        ident = dept.get('id')
        require(isinstance(ident, str) and ident in DEPARTMENTS, f'{path}.id: 알려진 부서 ID가 필요합니다.')
        require(ident not in seen, f'{path}.id: 중복 부서 ID {ident}')
        seen.add(ident)
        string(dept.get('name'), path + '.name')
        array(dept.get('issues'), path + '.issues')
        for j, issue in enumerate(dept['issues']):
            ip = f'{path}.issues[{j}]'
            obj(issue, ip)
            countries(issue.get('countries'), ip + '.countries')
            require(isinstance(issue.get('category'), str) and issue['category'] in CATEGORIES, ip + '.category: 알려진 카테고리가 필요합니다.')
            string(issue.get('title'), ip + '.title')
            array(issue.get('bullets'), ip + '.bullets')
            require(bool(issue['bullets']), ip + '.bullets: 최소 1개가 필요합니다.')
            for k, value in enumerate(issue['bullets']):
                bullet(value, f'{ip}.bullets[{k}]')
    array(data.get('reports'), 'reports')
    for i, report in enumerate(data['reports']):
        path = f'reports[{i}]'
        obj(report, path)
        string(report.get('org'), path + '.org')
        string(report.get('title'), path + '.title')
        day(report.get('date'), path + '.date')
        ident = report.get('department')
        require(isinstance(ident, str) and ident in DEPARTMENTS, path + '.department: 알려진 부서 ID가 필요합니다.')
        countries(report.get('countries'), path + '.countries')
        url(report.get('url'), path + '.url')
    if 'notes' in data:
        array(data['notes'], 'notes')
        for i, note in enumerate(data['notes']):
            string(note, f'notes[{i}]')


def main():
    try:
        data = json.loads((ROOT / 'data/report.json').read_text(encoding='utf-8'))
        validate(data)
        # Serialize rather than interpolate input; escape JS line separators.
        output = json.dumps(data, ensure_ascii=False, indent=2).replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
        target = ROOT / 'data/report.js'
        temporary = target.with_suffix('.js.tmp')
        temporary.write_text('window.REPORT_DATA = ' + output + ';\n', encoding='utf-8')
        temporary.replace(target)
    except (OSError, ValueError, TypeError) as error:
        print(f'보고서 생성 실패: {error}', file=sys.stderr)
        return 1
    print('생성 완료: data/report.js')
    return 0


if __name__ == '__main__':
    sys.exit(main())
