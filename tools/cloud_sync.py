#!/usr/bin/env python3
"""Builds the reports and downloads of the pizza study on Cloudflare, and stores them back on the site.

    PIZZA_SITE_URL=https://pizza-study.<you>.workers.dev PIZZA_ADMIN_KEY=... python3 tools/cloud_sync.py [--force]

Run by .github/workflows/reports.yml (when sessions finish, on "Rebuild now", and every 6 hours), or by hand from any
computer with Python. It asks the site what changed since the last run (count and newest save per study), and when
something did:
1. downloads every session (owner-only /admin/export) into a local SQLite database with the schema of server/store.py;
2. for everything ("all"), the main study and each study: runs analysis/analyse.py, and makes the R download (tables,
   variables.csv, load_pizza.R, raw sessions), the raw sessions zip and a copy of the database (that study only);
3. uploads them to the site's R2 storage (owner-only PUT /admin/files/...), where the researcher page serves them.

It prints counts only, never participant data, so its log is safe in a public repository's Actions log. The local
copies are deleted at the end (pass --keep DIR to keep them). Standard library only.
"""
import argparse
import calendar
import concurrent.futures
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))
sys.path.insert(1, os.path.join(ROOT, 'analysis'))                # synthetic.py
from store import Store  # noqa: E402
from server import R_FILES, R_README  # noqa: E402

UA = {'User-Agent': 'pizza-study-sync/1'}
REPORT_FILES = ('.html', '.csv')
SKIP = {'gallery.html'}                      # needs its pizzas/ folder; not on the researcher page


class Site:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip('/'), key

    def _req(self, method, path, data=None, params=None, ctype=None):
        q = urllib.parse.urlencode(dict(params or {}, key=self.key))
        req = urllib.request.Request('%s%s?%s' % (self.url, path, q), data=data, method=method, headers=dict(UA, **({'Content-Type': ctype} if ctype else {})))
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code == 507:
                    sys.exit('Stopped: the site refused to store more. %s' % e.read().decode('utf-8', 'replace')[:300])
                if e.code == 429 and attempt < 3:      # rate-limited: wait and try again
                    time.sleep(20)
                    continue
                if e.code in (401, 403):
                    sys.exit('The site refused the key (HTTP %d): PIZZA_ADMIN_KEY must be the owner\'s researcher password.' % e.code)
                if attempt == 3 or e.code < 500:
                    raise
            except urllib.error.URLError:
                if attempt == 3:
                    raise
            time.sleep(2 ** (attempt + 1))

    def get_json(self, path, **params):
        body = self._req('GET', path, params=params)
        return None if body is None else json.loads(body)

    def put(self, name, data):
        self._req('PUT', '/admin/files/' + name, data=data, ctype='application/octet-stream')

    def status(self, state, line='', step='', **extra):
        """Progress for the researcher page (and this log): running / done / failed, with a line for the page's log."""
        if line:
            print(line, flush=True)
        run = os.environ.get('GITHUB_RUN_ID')
        body = dict(extra, state=state, line=line, step=step or line,
                    run_url='%s/%s/actions/runs/%s' % (os.environ.get('GITHUB_SERVER_URL', 'https://github.com'), os.environ.get('GITHUB_REPOSITORY', ''), run) if run else '')
        try:
            self._req('POST', '/admin/status', data=json.dumps(body).encode(), ctype='application/json')
        except Exception:                      # progress is a nicety: never fail the build over it
            pass


def code_version():
    """The analysis code's hash: reports are rebuilt for everyone when it changes."""
    h = hashlib.sha1()
    for f in ('analysis/analyse.py', 'analysis/methods.py', 'analysis/r_export.py', 'analysis/load_pizza.R', 'analysis/nutrition.json'):
        with open(os.path.join(ROOT, f), 'rb') as fh:
            h.update(fh.read())
    return h.hexdigest()[:16]


def download(site, path):
    """All sessions, fields, invites and condition counters into a local study.db."""
    st = Store(path)
    db = st.db()
    after, n = '', 0
    while True:
        page = site.get_json('/admin/export', after=after, limit=25)
        if not page or not page['sessions']:
            break
        with st.tx() as c:
            for s in page['sessions']:
                cols = list(s)
                c.execute('INSERT OR REPLACE INTO sessions (%s) VALUES (%s)' % (', '.join(cols), ', '.join('?' * len(cols))), [s[k] for k in cols])
            c.executemany('INSERT OR REPLACE INTO fields VALUES (?, ?, ?, ?)', [(f['pid'], f['name'], f['value'], f['updated']) for f in page['fields']])
        n += len(page['sessions'])
        after = page['sessions'][-1]['pid']
    tables = site.get_json('/admin/export/tables') or {}
    with st.tx() as c:
        c.executemany('INSERT OR REPLACE INTO invites VALUES (?, ?, ?, ?, ?, ?)',
                      [(i['token'], i['study'], i['grp'], i['source'], i['note'], i['created']) for i in tables.get('invites', [])])
        c.executemany('INSERT OR REPLACE INTO meta VALUES (?, ?)', [(m['k'], m['v']) for m in tables.get('meta', [])])
    db.close()
    st.local.db = None
    return n


def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
    return buf.getvalue()


def build_scope(st, db_path, scope, work):
    """Reports and downloads of one scope ('all', 'main' or a study id): {stored name: bytes}, own pizzas analysed, the data check."""
    f = {'study': None if scope == 'all' else '' if scope == 'main' else scope}
    out = os.path.join(work, 'out-' + scope)
    cmd = [sys.executable, os.path.join(ROOT, 'analysis', 'analyse.py'), db_path, '--out', out] + ([] if scope == 'all' else ['--study', scope])
    # the measure cache: each pizza's slow measures are computed once and reused by every study and later runs
    env = dict(os.environ, PIZZA_MEASURE_CACHE=os.environ.get('PIZZA_MEASURE_CACHE') or os.path.join(work, 'measure-cache'))
    records = list(st.records(f))
    if not any(rec.get('pz_final') for rec in records):     # no pizza in this set yet: nothing to analyse (saves a run)
        r = subprocess.CompletedProcess(cmd, 1, '', 'No pizza fields found')
    else:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, env=env)
    files, n, check = {}, 0, {}
    raw = [('raw/%s.json' % rec['pid'], json.dumps(rec)) for rec in records]
    if r.returncode == 0 and os.path.exists(os.path.join(out, 'participants.csv')):
        with open(os.path.join(out, 'participants.csv'), encoding='utf-8') as fh:
            n = max(0, sum(1 for _ in fh) - 1)
        try:
            with open(os.path.join(out, 'data_check.json'), encoding='utf-8') as fh:
                check = json.load(fh)
            n = check['own']
        except (OSError, ValueError, KeyError):
            pass
        for name in sorted(os.listdir(out)):
            if name.endswith(REPORT_FILES) and name not in SKIP:
                with open(os.path.join(out, name), 'rb') as fh:
                    files['reports/%s/%s' % (scope, name)] = fh.read()
        r_files = [('pizza-data/README.txt', R_README)]
        for name in R_FILES:
            if os.path.exists(os.path.join(out, name)):
                with open(os.path.join(out, name), 'rb') as fh:
                    r_files.append(('pizza-data/' + name, fh.read()))
        files['exports/%s/pizza-data-R.zip' % scope] = zip_bytes(r_files + [('pizza-data/' + name, data) for name, data in raw])
    elif 'No pizza fields found' not in (r.stderr + r.stdout):
        print('  %s: the analysis failed (exit %d); its last lines:\n%s' % (scope, r.returncode, '\n'.join((r.stderr or r.stdout).strip().split('\n')[-3:])))
    files['exports/%s/sessions.zip' % scope] = zip_bytes([('participants/%s.json' % rec['pid'], json.dumps(rec)) for rec in records])
    copy = os.path.join(work, 'copy-%s.sqlite' % scope)
    st.backup(copy, f['study'])
    with open(copy, 'rb') as fh:
        files['exports/%s/study.sqlite.gz' % scope] = gzip.compress(fh.read(), 6, mtime=0)   # served unpacked
    return files, n, check


def sync_synthetic(site, wanted):
    """Brings each test study's synthetic sessions (analysis/synthetic.py) to the number chosen on the researcher page:
    sends the missing ones, and the site removes those above it. True if anything changed."""
    import synthetic
    changed = False
    for sid, n in wanted.items():
        have, page = set(), 1
        while True:                                             # the synthetic sessions the site holds now
            d = site.get_json('/admin/api/sessions', study=sid, stage='synthetic', page=page) or {'rows': [], 'pages': 1}
            have |= {r['pid'] for r in d['rows']}
            if page >= d.get('pages', 1):
                break
            page += 1
        add = [x for x in synthetic.sessions(n, sid) if x['pid'] not in have]
        drop = sum(1 for p in have if int(p[len(synthetic.PREFIX):]) > n)
        if not add and not drop:
            continue
        for i in range(0, max(len(add), 1), 50):
            body = json.dumps({'study': sid, 'add': add[i:i + 50], 'keep': n}).encode()
            site._req('POST', '/admin/synthetic-sync', data=body, ctype='application/json')
        site.status('waiting', '%s: synthetic sessions brought to %d (%d added, %d removed).' % (sid, n, len(add), drop))
        changed = True
    return changed


def brief_check(c):
    """What the researcher page shows of the data check: the counts and whether sessions and pizzas add up."""
    return {k: c[k] for k in ('sessions', 'typical', 'left_out', 'built_sessions', 'ok') if k in c} or None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--site', default=os.environ.get('PIZZA_SITE_URL'), help='the site (default: $PIZZA_SITE_URL)')
    ap.add_argument('--key', default=os.environ.get('PIZZA_ADMIN_KEY'), help='the owner\'s researcher password (default: $PIZZA_ADMIN_KEY)')
    ap.add_argument('--force', action='store_true', help='rebuild everything, even if nothing changed')
    ap.add_argument('--keep', default=None, help='keep the downloaded database and the reports in this folder')
    ap.add_argument('--wait', type=int, default=0, metavar='SECONDS',
                    help='first wait until no session was saved for this long (the site starts the job with 300 when a session '
                         'finishes, so sessions finishing close together share one build); at most 30 minutes')
    a = ap.parse_args()
    if not a.site or not a.key:
        sys.exit('Set PIZZA_SITE_URL and PIZZA_ADMIN_KEY (or pass --site and --key).')
    site = Site(a.site, a.key)
    info = site.get_json('/admin/signatures')
    if info is None:
        sys.exit('%s does not look like the pizza study on Cloudflare (no /admin/signatures).' % a.site)
    t_start = time.time()
    while a.wait:                              # quiet period: the waiting happens here on GitHub, not on Cloudflare
        last = info['signatures']['all'].split('|', 1)[1]
        quiet = time.time() - calendar.timegm(time.strptime(last[:19], '%Y-%m-%dT%H:%M:%S')) if last else a.wait
        left = a.wait - quiet
        if left <= 0 or time.time() - t_start > 1800:
            break
        site.status('waiting', step='Waiting for %d quiet minutes after the last save (last save %s UTC)' % (a.wait // 60, last[11:19]))
        time.sleep(min(left + 2, 60))
        info = site.get_json('/admin/signatures')
    if sync_synthetic(site, info.get('synthetic') or {}):    # a test study's synthetic sessions changed: new signatures
        info = site.get_json('/admin/signatures')
    sigs = info['signatures']
    state = site.get_json('/admin/files/state.json') or {}
    version = code_version()
    wanted = info.get('wanted')                # "Build reports" was pressed on the researcher page: build what changed
    if state.get('code') != version:           # the analysis changed: everything is rebuilt once
        a.force = True
    scopes = ['all'] + sorted(s for s in sigs if s != 'all')
    todo = [s for s in scopes if a.force or (state.get('scopes') or {}).get(s) != sigs[s]]
    if sigs['all'].startswith('0|'):
        todo = []
    if not todo:
        print('Up to date: %s.' % ', '.join('%s %s sessions' % (s, sigs[s].split('|')[0]) for s in scopes))
        if wanted or not sigs['all'].startswith('0|'):     # tell the site what the reports include, so it stops asking
            site.status('done', 'Up to date: nothing new since the last build.' if wanted else '', clear_wanted=wanted or '',
                        built_upto=sigs['all'].split('|', 1)[1])
        return
    work = a.keep or tempfile.mkdtemp(prefix='pizza-sync-')
    os.makedirs(work, exist_ok=True)
    t0 = time.time()
    site.status('running', 'Started: %s to build (%s).' % (len(todo), ', '.join(todo)), step='Downloading the sessions')
    try:
        db_path = os.path.join(work, 'study.db')
        if os.path.exists(db_path):
            os.remove(db_path)
        site.status('running', 'Downloaded %d sessions.' % download(site, db_path))
        st = Store(db_path)
        new_state = {'code': version, 'scopes': dict(state.get('scopes') or {})}
        stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        # a study holding exactly the sessions of "all" (e.g. all data so far is in one study) gets a copy of all's
        # reports instead of a second identical analysis; the others are analysed side by side
        count = lambda sc: sigs[sc].split('|')[0]
        same = {sc for sc in todo if sc != 'all' and count(sc) == count('all') and sigs[sc].split('|')[1] == sigs['all'].split('|')[1]}
        if same and 'all' not in todo:
            todo = ['all'] + todo
        analyse = [sc for sc in todo if sc not in same]
        site.status('running', 'Analysing %s side by side%s.' % (', '.join(analyse), ('; %s will reuse the analysis of all' % ', '.join(sorted(same))) if same else ''),
                    step='Analysing %d of %d sets' % (len(analyse), len(todo)))

        def store(scope, files, n, check, t1, note=''):
            files['reports/%s/.built' % scope] = json.dumps({'when': stamp, 'n': n, 'sig': sigs[scope], 'check': brief_check(check), 'code': version}).encode()
            if scope == 'all' and 'reports/all/methods.html' in files:
                files['methods.html'] = files['reports/all/methods.html']
            files = {k: v if isinstance(v, bytes) else v.encode('utf-8') for k, v in files.items()}
            room = site.get_json('/admin/storage')
            after = room['used'] - sum(room['files'].get(k, 0) for k in files) + sum(len(v) for v in files.values())
            if after > room['limits']['bytes']:
                sys.exit('Stopped before uploading %s: storage would reach %.2f GB, over the limit of %.2f GB. Nothing was stored for it. '
                         'Remove a study from "studies" in server/study.json or raise R2_LIMIT_BYTES (cloudflare/README.md).'
                         % (scope, after / 1e9, room['limits']['bytes'] / 1e9))
            if room['writes'] + len(files) > room['limits']['writes']:
                sys.exit('Stopped before uploading %s: this month\'s storage writes would pass the limit of %d.' % (scope, room['limits']['writes']))
            for name, data in files.items():
                site.put(name, data)
            new_state['scopes'][scope] = sigs[scope]
            done_n[0] += 1
            site.status('running', '%s: %d pizzas %s, %d files stored (%.0f s).' % (scope, n, note or 'analysed', len(files), time.time() - t1),
                        step='Stored %d of %d sets' % (done_n[0], len(todo)))

        done_n, built = [0], {}
        t1 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(4, os.cpu_count() or 2))) as pool:
            jobs = {pool.submit(build_scope, st, db_path, sc, work): sc for sc in analyse}
            for fut in concurrent.futures.as_completed(jobs):
                sc = jobs[fut]
                files, n, check = fut.result()
                built[sc] = (files, n, check)
                store(sc, files, n, check, t1)
        for sc in sorted(same):                # the copies: all's reports under the study's name
            files, n, check = built['all']
            copy = {k.replace('reports/all/', 'reports/%s/' % sc).replace('exports/all/', 'exports/%s/' % sc): v
                    for k, v in files.items() if k.startswith(('reports/all/', 'exports/all/')) and not k.endswith('/.built')}
            store(sc, copy, n, check, t1, note='(same sessions as all: copied)')
        site.put('state.json', json.dumps(new_state).encode())
        site.status('done', 'Done in %.0f s.' % (time.time() - t0), clear_wanted=wanted or '', built_upto=sigs['all'].split('|', 1)[1])
    except SystemExit as e:
        site.status('failed', 'Stopped: %s' % e)
        raise
    except Exception as e:
        site.status('failed', 'Failed: %s: %s' % (type(e).__name__, str(e)[:200]))
        raise
    finally:
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
