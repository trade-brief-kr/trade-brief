#!/usr/bin/env python3
"""Post-process and verify a Codex-generated report before publishing.

Usage:
  python3 tools/verify_report.py --input RAW.json --output REPORT.json [--log LOG.json]
                                 [--check-links] [--strict-links] [--no-network]
                                 [--grace-hours 1]

What it does (nothing is invented, items are only removed):
  1. Parses JSON; requires report.date == today (KST).
  2. Every bullet (topIssues + departments) must have source, http(s) url and
     publishedAt (ISO 8601 with offset). Missing/unparseable date -> removed.
  3. Window: publishedAt within 24h (+grace) of now; Kommersant/RBC bullets 48h.
     Dates embedded in the URL (…/2026/10/31/…, -2026-10-31, /20261031…) that
     fall before the window -> removed.
  4. Link HTTP re-check is OFF by default (Codex is trusted for source/url).
     With --check-links: curl each URL; 404/410/connection failure -> removed.
     2xx -> published date from page meta re-checked; 401/403/429/451/5xx
     (bot block / paywall) -> kept as "unverifiable" (removed with --strict-links);
     TLS reset/timeout with no HTTP response -> also "unverifiable"; DNS -> removed.
     --no-network is kept for compatibility (same as default: skip curl).
  5. Issues left with no bullets are dropped; departments normalised to
     cis, neasia, india, asean, mea. Reports must be dated within 4 days
     (reachable check only when --check-links).
  6. topIssues: first 5 surviving items; fewer than 5 -> fail.
  7. Schema check with build_report_js.validate. publishedAt is removed from the
     output so data/report.json keeps the existing format.
Output is written only on success; on failure a *.rejected.json is written next
to --output for inspection.
Quality warnings (cis 중앙아·코카서스·몽골 0건, asean 3건·3개국 미만) are logged in
log.qualityWarnings and stderr only; they never fail verification.
Exit codes: 0 ok, 12 unreadable/invalid JSON, 13 verification failed.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone, date as date_cls
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_report_js import validate  # noqa: E402

KST = timezone(timedelta(hours=9))
DEPTS = [('cis', '통상협력총괄과'), ('neasia', '동북아통상과'), ('india', '인도통상협력과'),
         ('asean', '아주통상과'), ('mea', '중동아프리카통상과')]
RU_48H_HOSTS = ('kommersant.ru', 'rbc.ru')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/130.0 Safari/537.36')
OUTLET_HOSTS = {'reuters': 'reuters.com', 'bloomberg': 'bloomberg.com', 'financial times': 'ft.com',
                'wall street journal': 'wsj.com', 'wsj': 'wsj.com', 'nikkei': 'nikkei.com', 'cnbc': 'cnbc.com',
                'associated press': 'apnews.com', 'ap': 'apnews.com', 'al jazeera': 'aljazeera.com',
                'kommersant': 'kommersant.ru', 'rbc': 'rbc.ru'}
BLOCKED = {401, 402, 403, 429, 451}
META_DATE = [
    r'<meta[^>]+(?:property|name|itemprop)=["\'](?:article:published_time|og:article:published_time|'
    r'datePublished|pubdate|publishdate|publish-date|parsely-pub-date|sailthru\.date|dc\.date|date)["\'][^>]*'
    r'content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\'](?:article:published_time|datePublished)["\']',
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'<time[^>]+datetime=["\']([^"\']+)["\']',
]


def parse_ts(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace('Z', '+00:00')
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        m = re.match(r'(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)(\.\d+)?([+-]\d{2}:?\d{2})?', text)
        if not m:
            return None
        off = m.group(4) or ''
        if off and ':' not in off:
            off = off[:3] + ':' + off[3:]
        try:
            ts = datetime.fromisoformat(f'{m.group(1)}T{m.group(2)}{off}')
        except ValueError:
            return None
    return ts if ts.utcoffset() is not None else None


def url_date(url):
    path = urlparse(url).path
    for pat in (r'/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)', r'[-_/](20\d{2})-(\d{2})-(\d{2})(?:[-_/.]|$)',
                r'/(20\d{2})(\d{2})(\d{2})\d{0,8}(?:[/._-]|$)'):
        m = re.search(pat, path)
        if m:
            try:
                return date_cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
    return None


class Checker:
    def __init__(self, network, strict):
        self.network, self.strict, self.cache = network, strict, {}

    def fetch(self, url):
        if url in self.cache:
            return self.cache[url]
        result = {'status': None, 'pageDate': None, 'contentType': '', 'curlExit': None}
        if self.network:
            for attempt in range(2):
                try:
                    proc = subprocess.run(
                        ['curl', '-sS', '-L', '--max-time', '25', '--max-filesize', '3000000', '-A', UA,
                         '-H', 'Accept-Language: en-US,en;q=0.9,ko;q=0.8', '-o', '-',
                         '-w', '\n__CURL__%{http_code} %{content_type}', url],
                        capture_output=True, timeout=40)
                    result['curlExit'] = proc.returncode
                    out = proc.stdout.decode('utf-8', 'replace')
                    body, _, tail = out.rpartition('\n__CURL__')
                    code, _, ctype = tail.partition(' ')
                    result['status'] = int(code) if code.isdigit() else 0
                    result['contentType'] = ctype.strip()
                    if 200 <= result['status'] < 300 and 'html' in ctype:
                        for pat in META_DATE:
                            m = re.search(pat, body[:600000], re.I)
                            if m and parse_ts(m.group(1)):
                                result['pageDate'] = m.group(1)
                                break
                except (subprocess.TimeoutExpired, OSError):
                    result['status'] = 0
                if result['status']:
                    break
        self.cache[url] = result
        return result

    def link_verdict(self, url):
        """Return (keep, status_label, page_ts)."""
        if not self.network:
            return True, 'not-checked', None
        r = self.fetch(url)
        s = r['status']
        if s and 200 <= s < 300:
            return True, 'ok', parse_ts(r['pageDate']) if r['pageDate'] else None
        if s in BLOCKED or (s and s >= 500):
            return (not self.strict), f'unverifiable-{s}', None
        # No HTTP response: DNS failure (curl 6) = dead link; TLS reset / timeout from the
        # box network (e.g. Korean sites such as yna.co.kr block overseas IPs) = unverifiable.
        if not s and r.get('curlExit') not in (None, 3, 6):
            return (not self.strict), f'unverifiable-net{r.get("curlExit")}', None
        return False, f'dead-{s}', None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--log')
    ap.add_argument('--check-links', action='store_true',
                    help='Opt-in: curl each URL (404/DNS drop items). Default is OFF; trust Codex.')
    ap.add_argument('--strict-links', action='store_true',
                    help='With --check-links: also drop bot-blocked/paywall links')
    ap.add_argument('--no-network', action='store_true',
                    help='Compatibility alias: skip curl (same as default)')
    ap.add_argument('--grace-hours', type=float, default=1.0)
    ap.add_argument('--now', help='ISO timestamp override (testing)')
    a = ap.parse_args(argv)

    now = parse_ts(a.now) if a.now else datetime.now(KST)
    today = now.astimezone(KST).date()
    grace = timedelta(hours=a.grace_hours)
    out_path = Path(a.output)
    # Network re-check OFF by default; only --check-links enables curl.
    use_network = bool(a.check_links) and not a.no_network
    log = {'now': now.isoformat(), 'removed': [], 'links': {}, 'unverifiable': 0,
           'networkCheck': use_network}

    def finish(code, msg, report=None):
        log['result'] = msg
        if report is not None and code != 0:
            out_path.with_name(out_path.stem + '.rejected.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if a.log:
            Path(a.log).write_text(json.dumps(log, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(('검증 통과: ' if code == 0 else '검증 실패: ') + msg, file=sys.stderr if code else sys.stdout)
        return code

    try:
        report = json.loads(Path(a.input).read_text(encoding='utf-8'))
        if not isinstance(report, dict):
            raise ValueError('최상위가 객체가 아님')
    except (OSError, ValueError) as e:
        return finish(12, f'JSON을 읽을 수 없음: {e}')

    if report.get('date') != today.isoformat():
        return finish(13, f"date가 오늘(KST {today})이 아님: {report.get('date')}", report)

    checker = Checker(use_network, a.strict_links)

    def check_bullet(b, where, hours):
        if not isinstance(b, dict):
            return 'bullet 형식 오류'
        url = b.get('url') or ''
        if not (isinstance(b.get('text'), str) and b['text'].strip()):
            return 'text 없음'
        if not (isinstance(b.get('source'), str) and b['source'].strip()):
            return 'source 없음'
        if urlparse(url).scheme not in ('http', 'https'):
            return 'url 없음'
        host = urlparse(url).netloc.lower()
        if any(host == h or host.endswith('.' + h) for h in RU_48H_HOSTS):
            hours = max(hours, 48)
        start = now - timedelta(hours=hours) - grace
        ts = parse_ts(b.get('publishedAt'))
        if ts is None:
            return 'publishedAt 확인 불가'
        if ts < start or ts > now + grace:
            return f'기간 밖 publishedAt {b.get("publishedAt")}'
        ud = url_date(url)
        if ud and ud < start.astimezone(KST).date() - timedelta(days=1):
            return f'URL 날짜가 기간 밖 {ud}'
        src = b['source'].strip().lower()
        expected = OUTLET_HOSTS.get(src)
        if expected and not (host == expected or host.endswith('.' + expected)):
            log.setdefault('warnings', []).append(f'{where}: source "{b["source"]}" 와 URL 도메인 {host} 불일치')
        keep, status, page_ts = checker.link_verdict(url)
        log['links'][url] = status
        if not keep:
            return f'링크 확인 실패({status})'
        if page_ts is not None and page_ts < start - timedelta(hours=12):
            return f'페이지 게시일이 기간 밖 {page_ts.isoformat()}'
        return None

    def drop(where, b, reason):
        log['removed'].append({'where': where, 'reason': reason,
                               'text': (b.get('text') if isinstance(b, dict) else str(b))[:120] if b else '',
                               'url': b.get('url') if isinstance(b, dict) else None})

    # Top issues
    tops = []
    for i, b in enumerate(report.get('topIssues') or []):
        why = check_bullet(b, f'topIssues[{i}]', 24)
        if why:
            drop(f'topIssues[{i}]', b, why)
        else:
            tops.append(b)
    log['topIssuesVerified'] = len(tops)
    report['topIssues'] = tops[:5]

    # Departments
    by_id = {d.get('id'): d for d in report.get('departments') or [] if isinstance(d, dict)}
    for d_id in list(by_id):
        if d_id not in dict(DEPTS):
            log['removed'].append({'where': f'departments.{d_id}', 'reason': '알 수 없는 부서 ID'})
    depts = []
    for d_id, name in DEPTS:
        dept = by_id.get(d_id) or {}
        issues = []
        for j, issue in enumerate(dept.get('issues') or []):
            if not isinstance(issue, dict):
                continue
            kept = []
            for k, b in enumerate(issue.get('bullets') or []):
                why = check_bullet(b, f'{d_id}.issues[{j}].bullets[{k}]', 24)
                if why:
                    drop(f'{d_id}.issues[{j}].bullets[{k}]', b, why)
                else:
                    kept.append(b)
            if kept:
                issue['bullets'] = kept
                issues.append(issue)
            else:
                log['removed'].append({'where': f'{d_id}.issues[{j}]', 'reason': '남은 bullet 없음',
                                       'text': str(issue.get('title'))[:120]})
        depts.append({'id': d_id, 'name': name, 'issues': issues})
    report['departments'] = depts

    # Reports (3~4 days, PDF preferred)
    reps = []
    for i, r in enumerate(report.get('reports') or []):
        try:
            rd = date_cls.fromisoformat(r.get('date'))
        except (TypeError, ValueError, AttributeError):
            drop(f'reports[{i}]', {'text': str(r)}, '발간일 형식 오류')
            continue
        if not (today - timedelta(days=4) <= rd <= today):
            drop(f'reports[{i}]', {'text': r.get('title', ''), 'url': r.get('url')}, f'발간일 기간 밖 {rd}')
            continue
        url = r.get('url') or ''
        if url:
            keep, status, _ = checker.link_verdict(url)
            log['links'][url] = status
            if not keep:
                drop(f'reports[{i}]', {'text': r.get('title', ''), 'url': url}, f'링크 확인 실패({status})')
                continue
        reps.append(r)
    report['reports'] = reps

    unverifiable = sorted({u for u, s in log['links'].items() if s.startswith('unverifiable')})
    log['unverifiable'] = len(unverifiable)
    notes = [n for n in report.get('notes') or [] if isinstance(n, str) and n.strip()]
    if unverifiable and use_network:
        notes.append(f'자동 링크 점검: 출처 링크 {len(log["links"])}개 중 {len(unverifiable)}개는 유료·봇 차단으로 '
                     '접속 확인이 불가해 조사 단계에서 확인한 게시일을 기준으로 함.')
    if notes:
        report['notes'] = notes
    log['issueCount'] = sum(len(d['issues']) for d in depts)
    log['issuesPerDept'] = {d['id']: len(d['issues']) for d in depts}
    # Quality warnings only (never a publish failure): user-approved minimums for cis / asean.
    qw = []
    cis_extra = {'카자흐스탄', '우즈베키스탄', '투르크메니스탄', '키르기스스탄', '타지키스탄',
                 '아제르바이잔', '아르메니아', '조지아', '몽골', '몰도바', '벨라루스'}
    for d in depts:
        if d['id'] == 'cis' and not any(set(i.get('countries') or []) & cis_extra for i in d['issues']):
            qw.append('통상협력총괄과: 러시아·우크라이나 외 중앙아·코카서스·몽골 이슈 0건')
        if d['id'] == 'asean':
            n_c = len({c for i in d['issues'] for c in (i.get('countries') or [])})
            if len(d['issues']) < 3 or n_c < 3:
                qw.append(f'아주통상과: 이슈 {len(d["issues"])}건, 국가 {n_c}개 (목표 3건·3개국 이상)')
    log['qualityWarnings'] = qw
    for w in qw:
        print('품질 경고(게시 영향 없음): ' + w, file=sys.stderr)

    # Dedupe Top Issues (same sentence) before counting.
    seen_txt, uniq = set(), []
    for b in tops:
        key = ' '.join(b['text'].split())
        if key in seen_txt:
            drop('topIssues', b, '중복 문장')
        else:
            seen_txt.add(key)
            uniq.append(b)
    tops = uniq
    report['topIssues'] = tops[:5]
    log['topIssuesVerified'] = len(tops)
    # publishedAt is a research/verification aid only: strip it so data/ keeps the existing format.
    for b in report['topIssues'] + [x for d in depts for i in d['issues'] for x in i['bullets']]:
        b.pop('publishedAt', None)
    if len(tops) < 5:
        return finish(13, f'검증된 Global Top Issues {len(tops)}개(5개 미만)', report)
    try:
        validate(report)
    except (ValueError, TypeError, KeyError) as e:
        return finish(13, f'스키마 오류: {e}', report)
    tmp = out_path.with_name(out_path.name + '.tmp')
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(out_path)
    return finish(0, f'Top {len(report["topIssues"])}개, 이슈 {log["issueCount"]}개, 제거 {len(log["removed"])}건, '
                     f'접속 확인 불가 링크 {len(unverifiable)}개 → {out_path}')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
