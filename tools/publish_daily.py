#!/usr/bin/env python3
"""Validate data/report.json and publish it (latest + archive) in one step.

Usage: python3 tools/publish_daily.py [--allow-any-date]

1. Validates data/report.json (same rules as build_report_js.py).
2. Checks that report.date is today in KST (skip with --allow-any-date).
3. Writes data/archive/<date>.json and data/archive/<date>.js (file:// fallback),
   overwriting the same date on re-runs.
4. Rebuilds data/archive/index.json and data/archive/index.js (newest first).
5. Rebuilds data/report.js.
On any error nothing is published: all outputs are written to temp files first
and only moved into place after everything succeeded. Exit code 1 on failure.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_report_js import ROOT, validate  # noqa: E402

KST = timezone(timedelta(hours=9))
DATA = ROOT / 'data'
ARCHIVE = DATA / 'archive'
HEADLINE_MAX = 120


def js_literal(value):
    return json.dumps(value, ensure_ascii=False, indent=2).replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def headline(report):
    text = ' '.join(report['topIssues'][0]['text'].split())
    return text if len(text) <= HEADLINE_MAX else text[:HEADLINE_MAX - 1].rstrip() + '…'


def index_entry(report):
    titles = [issue['title'] for dept in report['departments'] for issue in dept['issues']]
    return {
        'date': report['date'],
        'topIssueHeadline': headline(report),
        # Used by the site's keyword search (top issues + issue titles).
        'keywords': [b['text'] for b in report['topIssues']] + titles,
    }


def main(argv):
    allow_any_date = '--allow-any-date' in argv
    staged = []  # (temp_path, final_path)
    try:
        report = json.loads((DATA / 'report.json').read_text(encoding='utf-8'))
        validate(report)
        today = datetime.now(KST).date().isoformat()
        if not allow_any_date and report['date'] != today:
            raise ValueError(f"date: 오늘(KST {today})이 아닙니다: {report['date']} (--allow-any-date로 무시 가능)")
        date = report['date']
        ARCHIVE.mkdir(parents=True, exist_ok=True)

        # Collect existing archive (excluding today's, which is replaced).
        entries = {date: index_entry(report)}
        for path in sorted(ARCHIVE.glob('????-??-??.json')):
            if path.stem == date:
                continue
            old = json.loads(path.read_text(encoding='utf-8'))
            validate(old)
            if old['date'] != path.stem:
                raise ValueError(f'{path.name}: 파일명과 date({old["date"]})가 다릅니다.')
            entries[old['date']] = index_entry(old)
        index = sorted(entries.values(), key=lambda e: e['date'], reverse=True)

        def stage(final, text):
            temp = final.with_name(final.name + '.tmp')
            temp.write_text(text, encoding='utf-8')
            staged.append((temp, final))

        body = js_literal(report)
        stage(ARCHIVE / f'{date}.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        stage(ARCHIVE / f'{date}.js',
              'window.REPORT_ARCHIVE = window.REPORT_ARCHIVE || {};\n'
              f'window.REPORT_ARCHIVE[{json.dumps(date)}] = {body};\n')
        stage(ARCHIVE / 'index.json', json.dumps(index, ensure_ascii=False, indent=2) + '\n')
        stage(ARCHIVE / 'index.js', 'window.REPORT_INDEX = ' + js_literal(index) + ';\n')
        stage(DATA / 'report.js', 'window.REPORT_DATA = ' + body + ';\n')
        for temp, final in staged:
            temp.replace(final)
        staged.clear()
    except (OSError, ValueError, TypeError, KeyError) as error:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
        print(f'게시 실패(아무 파일도 변경하지 않음): {error}', file=sys.stderr)
        return 1
    print(f'게시 완료: {date} (보관 {len(index)}일) → data/report.js, data/archive/{date}.json/.js, data/archive/index.json/.js')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
