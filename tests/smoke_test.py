#!/usr/bin/env python3
"""End-to-end check with nothing installed beyond Python 3.10+: simulate participants, analyse them, run the study
server, play one session through it, and use the researcher page. Exits non-zero on any failure.

    python3 tests/smoke_test.py
"""
import csv
import glob
import gzip
import io
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
failures = []
results = []          # (section, ok, what) for the CI job summary
section = ['']


def check(cond, what):
    print(('  ok    ' if cond else '  FAIL  ') + what)
    results.append((section[0], bool(cond), what))
    if not cond:
        failures.append(what)


def heading(name):
    print(name)
    section[0] = name


def write_summary(path, seconds):
    """A Markdown report of every check (GitHub shows it on the run's page when path is $GITHUB_STEP_SUMMARY)."""
    sha = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    r_ver = subprocess.run(['Rscript', '-e', 'cat(R.version$major, R.version$minor, sep=".")'], capture_output=True, text=True).stdout if shutil.which('Rscript') else ''
    lines = ['## Pizza Builder checks: %s' % ('all %d passed' % len(results) if not failures else '%d of %d FAILED' % (len(failures), len(results))),
             '', 'Commit `%s` · Python %s · %s · node %s · %.0f s' % (sha or '?', sys.version.split()[0], ('R ' + r_ver) if r_ver else 'no R',
                                                                  'yes' if shutil.which('node') else 'no', seconds), '']
    for sec in dict.fromkeys(r[0] for r in results):
        rs = [r for r in results if r[0] == sec]
        lines += ['<details%s><summary><b>%s</b>: %d/%d</summary>' % ('' if all(r[1] for r in rs) else ' open', sec, sum(r[1] for r in rs), len(rs)), '',
                  '| | check |', '|---|---|'] + ['| %s | %s |' % ('✅' if ok else '❌', what.replace('|', '\\|')) for _, ok, what in rs] + ['', '</details>', '']
    with open(path, 'a', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def run(*args):
    r = subprocess.run([PY] + list(args), cwd=ROOT, capture_output=True, text=True, timeout=600)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-2000:])
    return r.returncode == 0


def http(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'} if body is not None else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def deploy_api_checks():
    """cloudflare/deploy.py's use of Cloudflare's API (account, workers.dev address, Turnstile), against a stand-in."""
    import http.server
    import threading
    calls, widgets = [], []

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, result, code=200):
            body = json.dumps({'success': code == 200, 'result': result, 'errors': [] if code == 200 else [{'code': 9109, 'message': 'Unauthorized'}]}).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)

        def handle_any(self):
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(n)) if n else None
            calls.append((self.command, self.path))
            p = self.path
            if self.headers.get('Authorization') != 'Bearer good-token':
                return self.reply(None, 403)
            if p == '/accounts':
                return self.reply([{'id': 'acc0123456789', 'name': 'Lab'}])
            if p.endswith('/workers/subdomain'):
                return self.reply({'subdomain': body['subdomain']} if self.command == 'PUT' else {'subdomain': None})
            if p.endswith('/challenges/widgets') and self.command == 'POST':
                widgets.append(dict(body, sitekey='0xSITE', secret='0xSECRET'))
                return self.reply(widgets[-1])
            if p.endswith('/challenges/widgets'):
                return self.reply([{k: v for k, v in w.items() if k != 'secret'} for w in widgets])
            if '/challenges/widgets/' in p:
                return self.reply(widgets[0])
            return self.reply([])
        do_GET = do_POST = do_PUT = handle_any

    srv = http.server.HTTPServer(('127.0.0.1', 0), Api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = dict(os.environ, PIZZA_CF_API='http://127.0.0.1:%d' % srv.server_address[1], CLOUDFLARE_API_TOKEN='good-token')
    env.pop('CLOUDFLARE_ACCOUNT_ID', None)
    code = ('import sys, json; sys.path.insert(0, "cloudflare"); import deploy\n'
            'u = deploy.site_url(create=True); print(json.dumps([deploy.account_id(), u, deploy.ensure_turnstile(u.split("/")[2]), deploy.ensure_turnstile(u.split("/")[2])]))')
    r = subprocess.run([PY, '-c', code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    out = json.loads(r.stdout.strip().split('\n')[-1]) if r.returncode == 0 else None
    check(out is not None and out[0] == 'acc0123456789' and out[1] == 'https://pizza-study.pizza-acc01234.workers.dev',
          'deploy: finds the account and registers a workers.dev address when there is none')
    check(out is not None and out[2] == ['0xSITE', '0xSECRET'] and out[3] == ['0xSITE', '0xSECRET'] and len(widgets) == 1
          and widgets[0]['domains'] == ['pizza-study.pizza-acc01234.workers.dev'], 'deploy: creates the Turnstile bot check for the site once')
    r = subprocess.run([PY, 'cloudflare/deploy.py', 'check'], cwd=ROOT, env=dict(env, CLOUDFLARE_API_TOKEN='bad-token'), capture_output=True, text=True, timeout=60)
    check(r.returncode == 1 and 'FAIL  account' in r.stdout and 'Unauthorized' in r.stdout, 'deploy: a token that cannot do the job is reported, step by step')
    srv.shutdown()


def cloudflare_checks(tmp, fields):
    """The Cloudflare version (cloudflare/): the Worker in the local Workers runtime (wrangler dev, with local D1 and
    R2), the same participant and researcher routes as the Python server, and the reports job (tools/cloud_sync.py)."""
    heading('cloudflare')
    sys.path.insert(0, os.path.join(ROOT, 'server'))
    import store
    norm = lambda t: re.sub(r'\s+', ' ', re.sub(r'--[^\n]*', '', t)).strip()
    mig = open(os.path.join(ROOT, 'cloudflare', 'migrations', '0001_init.sql'), encoding='utf-8').read()
    check(norm(mig) == norm(store.SCHEMA), 'the D1 schema is the schema of server/store.py')
    deploy_api_checks()
    exe = os.path.join(ROOT, 'cloudflare', 'node_modules', '.bin', 'wrangler')
    if not os.path.exists(exe):
        print('  skip  the Worker itself: run "npm ci" in cloudflare/ to test it (CI does)')
        check(not os.environ.get('PIZZA_REQUIRE_CLOUDFLARE'), 'wrangler is installed (cloudflare/node_modules)')
        return
    cf = os.path.join(ROOT, 'cloudflare')
    state = os.path.join(tmp, 'wrangler-state')
    env = dict(os.environ, WRANGLER_SEND_METRICS='false', CI='1')
    subprocess.run([PY, os.path.join(cf, 'deploy.py'), 'build'], check=True, capture_output=True)
    r = subprocess.run([exe, 'd1', 'migrations', 'apply', 'pizza-study', '--local', '--persist-to', state], cwd=cf, env=env, capture_output=True, text=True)
    check(r.returncode == 0, 'applies the D1 migrations')
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    log = open(os.path.join(tmp, 'wrangler.log'), 'w')
    srv = subprocess.Popen([exe, 'dev', '--local', '--ip', '127.0.0.1', '--port', str(port), '--persist-to', state, '--var', 'ADMIN_KEY:smoke-owner-key'], cwd=cf, env=env,
                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    base, key = 'http://127.0.0.1:%d' % port, 'smoke-owner-key'
    try:
        for _ in range(150):
            try:
                if http('GET', base + '/study.json')[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(0.2)
        code, page = http('GET', base + '/')
        check(code == 200 and b'pizza-builder.js' in page, 'Worker: participant page')
        check('nutrition_reveal' in json.loads(http('GET', base + '/study.json')[1]), 'Worker: passes the nutrition-reveal setting to the page')
        pst = json.loads(http('GET', base + '/study.json?study=pilot-2026-11')[1])
        check(pst['lang'] == 'pl' and pst['consent_choice'] is True and pst['followup'] == 'metryczka' and pst['cheeses'] == ['none', 'light', 'extra', 'vegan']
              and pst['bake_picture'] is True, 'Worker: passes the Pizza Pilot 11.2026 flow (Polish, consent yes / no, metryczka, cheeses, baked pizza)')
        check(http('GET', base + '/pizza-builder.js')[0] == 200, 'Worker: serves the task script')
        check(json.loads(http('GET', base + '/api/start?group=ASD&pid=CFSMOKE1')[1]).get('pid') == 'CFSMOKE1', 'Worker: starts a session')
        check(http('POST', base + '/api/save', {'pid': 'CFSMOKE1', 'stage': 'done', 'fields': fields})[0] == 200, 'Worker: saves a session')
        check(http('POST', base + '/api/save', {'pid': '../../etc', 'fields': {'pz_final': '[]'}})[0] == 404, 'Worker: rejects a bad participant id')
        check(http('GET', base + '/admin')[0] == 403 and http('GET', base + '/admin?key=wrong')[0] == 403, 'Worker: researcher page needs the password')
        body = urllib.parse.urlencode({'study': 'pilot-asd', 'group': 'ASD', 'source': 'charity', 'count': '2'}).encode()
        urllib.request.urlopen(urllib.request.Request(base + '/admin/invites?key=' + key, data=body, method='POST'))
        invites = list(csv.DictReader(io.StringIO(http('GET', base + '/admin/invites.csv?key=%s&study=pilot-asd' % key)[1].decode('utf-8-sig'))))
        check(len(invites) == 2 and invites[0]['link'].endswith('?i=' + invites[0]['invite']), 'Worker: makes personal invite links')
        started = [json.loads(http('GET', base + '/api/start?i=' + i['invite'])[1]) for i in invites]
        check(all(st.get('pid') == i['invite'] for st, i in zip(started, invites)), 'Worker: an invite link is its participant\'s id')
        check('error' in json.loads(http('GET', base + '/api/start?i=nosuchone')[1]), 'Worker: refuses unknown invite links')
        http('POST', base + '/api/save', {'pid': started[0]['pid'], 'stage': 'followup', 'fields': {'pz_counts': 'pep:2', 'restarts': '1'}})
        back = json.loads(http('GET', base + '/api/start?i=' + invites[0]['invite'])[1])
        check(back.get('stage') == 'followup' and back.get('counts') == 'pep:2' and back.get('restarts') == '1', 'Worker: a returning participant resumes')
        for st in started:
            http('POST', base + '/api/save', {'pid': st['pid'], 'stage': 'done', 'fields': fields})
        check(api(base, 'sessions', key, study='pilot-asd')['total'] == 2, 'Worker: researcher page filters by study')
        check(api(base, 'sessions', key, study='all', stage='done', sort='n_pieces', dir='asc')['total'] == 3, 'Worker: filters by stage and sorts')
        rows = list(csv.DictReader(io.StringIO(http('GET', base + '/admin/sessions.csv?key=' + key)[1].decode('utf-8-sig'))))
        check({r['study'] for r in rows} == {'main', 'pilot-asd'} and len(rows) == 3, 'Worker: session list (.csv)')
        client_checks(base, key, 'CFSMOKE1', 'Worker: ')
        skey = researcher_access_checks(base, key, 'pilot-asd', 2, 3, 'CFSMOKE1', 'Worker: ')
        inclusion_checks(base, key, skey, 'pilot-asd', 'CFSMOKE1', 'Worker: ')
        check(all(http(m, base + p + '?key=' + skey, b)[0] == 404 for m, p, b in
                  [('GET', '/admin/export', None), ('GET', '/admin/signatures', None), ('POST', '/admin/study-key', {})]),
              'Worker: a study\'s researcher link cannot export everything or change links')
        # the reports job, against this Worker (the test study's synthetic data set to 25 first, to keep this quick)
        code, _ = post_form(base + '/admin/api/synthetic?key=' + key, {'study': 'tests', 'n': '25'})
        before = next(x for x in api(base, 'state', key)['studies'] if x['id'] == 'tests')['synthetic']
        r = subprocess.run([PY, os.path.join(ROOT, 'tools', 'cloud_sync.py'), '--site', base, '--key', key], capture_output=True, text=True, timeout=900)
        check(r.returncode == 0 and 'pilot-asd: 2 pizzas analysed' in r.stdout, 'reports job builds every study\'s reports and stores them')
        after = next(x for x in api(base, 'state', key)['studies'] if x['id'] == 'tests')['synthetic']
        rep = http('GET', base + '/admin/reports/explore.html?' + urllib.parse.urlencode({'key': key, 'study': 'tests'}))[1].decode('utf-8', 'replace')
        check(code == 200 and before == {'n': 25, 'stored': 0, 'choices': [0, 25, 50, 100, 200, 500]} and after['stored'] == 25
              and api(base, 'sessions', key, study='tests', stage='synthetic')['total'] == 25 and 'Includes 25 synthetic pizzas' in rep,
              'Worker: the chosen synthetic data is generated by the reports job, flagged, and in the test study\'s reports')
        if r.returncode:
            print(r.stdout[-1500:], r.stderr[-1500:])
        check(b'<h1>Overview</h1>' in http('GET', base + '/admin/reports/dashboard.html?key=' + skey)[1], 'Worker: serves a study\'s reports')
        z = zipfile.ZipFile(io.BytesIO(http('GET', base + '/admin/r.zip?key=' + skey)[1]))
        pc = list(csv.DictReader(io.StringIO(z.read('pizza-data/participants.csv').decode('utf-8'))))
        check(len(pc) == 2 and {r['study'] for r in pc} == {'pilot-asd'} and 'pizza-data/load_pizza.R' in z.namelist(), 'Worker: a study\'s R download holds that study only')
        dbp = os.path.join(tmp, 'cf-copy.sqlite')
        dbb = http('GET', base + '/admin/database.sqlite?key=' + skey)[1]
        open(dbp, 'wb').write(gzip.decompress(dbb) if dbb[:2] == b'\x1f\x8b' else dbb)   # stored compressed; browsers unpack it
        con = sqlite3.connect(dbp)
        check(con.execute('SELECT DISTINCT study FROM sessions').fetchall() == [('pilot-asd',)], 'Worker: a study\'s database copy holds that study only')
        con.close()
        check(b'how every number is counted' in http('GET', base + '/admin/methods?key=' + key)[1], 'Worker: serves the Methods page')
        b = api(base, 'state', key, study='pilot-asd')['build']
        check(b['status']['state'] == 'done' and any('Done in' in x for x in b['status']['log']) and any('pilot-asd: 2 pizzas' in x for x in b['status']['log']),
              'the researcher page shows the build\'s progress and log')
        r = subprocess.run([PY, os.path.join(ROOT, 'tools', 'cloud_sync.py'), '--site', base, '--key', key], capture_output=True, text=True, timeout=300)
        check(r.returncode == 0 and r.stdout.startswith('Up to date'), 'reports job does nothing when no session changed')
        urllib.request.urlopen(urllib.request.Request(base + '/admin/reports?key=' + key, data=b'', method='POST'))
        wanted = api(base, 'state', key)['build']['wanted']
        r = subprocess.run([PY, os.path.join(ROOT, 'tools', 'cloud_sync.py'), '--site', base, '--key', key], capture_output=True, text=True, timeout=600)
        check(wanted and r.returncode == 0 and r.stdout.startswith('Up to date') and not api(base, 'state', key)['build']['wanted'],
              '"Build reports" with nothing new finishes at once (no analysis) and clears the request')
        pid = api(base, 'sessions', key, study='pilot-asd')['rows'][0]['pid']
        post_form(base + '/admin/api/inclusion?key=' + key, {'pid': pid, 'value': 'exclude'})
        st = api(base, 'state', key, study='pilot-asd')
        r = subprocess.run([PY, os.path.join(ROOT, 'tools', 'cloud_sync.py'), '--site', base, '--key', key], capture_output=True, text=True, timeout=600)
        started = next((x for x in r.stdout.splitlines() if x.startswith('Started')), '')
        check(not st['reports']['fresh'] and st['build']['pending'] and 'pilot-asd' in started and 'tests' not in started
              and api(base, 'state', key, study='pilot-asd')['reports']['fresh'],
              'an inclusion choice marks the reports out of date; the next build redoes only the studies it touches')
        post_form(base + '/admin/api/inclusion?key=' + key, {'pid': pid, 'value': 'auto'})
        counting_checks(base, key, fields, 'Worker: ')
        r = subprocess.run([PY, os.path.join(ROOT, 'tools', 'cloud_sync.py'), '--site', base, '--key', key, '--only', 'main'], capture_output=True, text=True, timeout=600)
        started = next((x for x in r.stdout.splitlines() if x.startswith('Started')), '')
        check(r.returncode == 0 and started == 'Started: 1 to build (main).' and api(base, 'state', key, study='main')['reports']['fresh']
              and not api(base, 'state', key, study='all')['reports']['fresh'],
              '"Build reports" on a study\'s page builds that study only (not "all" or the other studies)' + ('' if r.returncode == 0 else ' - ' + r.stderr[-300:]))
    finally:
        os.killpg(srv.pid, 15)
        srv.wait(timeout=20)
        log.close()
    # bot protection: with Turnstile configured, a new session needs the check; too many starts from one address
    # are refused (Cloudflare's test keys: this secret never passes)
    srv = subprocess.Popen([exe, 'dev', '--local', '--ip', '127.0.0.1', '--port', str(port), '--persist-to', state, '--var', 'ADMIN_KEY:smoke-owner-key',
                            '--var', 'TURNSTILE_SITE_KEY:2x00000000000000000000AB', '--var', 'TURNSTILE_SECRET:2x0000000000000000000000000000000AA',
                            '--var', 'R2_LIMIT_BYTES:50000', '--var', 'R2_WRITES_PER_MONTH:99999999999', '--var', 'D1_LIMIT_BYTES:1000'],
                           cwd=cf, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        for _ in range(150):
            try:
                if http('GET', base + '/robots.txt')[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(0.2)
        check(json.loads(http('GET', base + '/api/start?pid=BOTCHECK1')[1]).get('verify') == '2x00000000000000000000AB'
              and json.loads(http('GET', base + '/api/start?pid=BOTCHECK1&ts=forged')[1]).get('verify'), 'Worker: a new session needs the bot check (Turnstile)')
        check(json.loads(http('GET', base + '/api/start?pid=CFSMOKE1')[1]).get('pid') == 'CFSMOKE1', 'Worker: a returning participant is not checked again')
        check(b'Disallow: /' in http('GET', base + '/robots.txt')[1], 'Worker: asks search engines to stay away')
        # hard caps on R2 (the only part that bills by use): here 50 kB, already used by the reports above
        st = json.loads(http('GET', base + '/admin/storage?key=' + key)[1])
        check(st['limits']['bytes'] == 50000 and st['limits']['writes'] == 800000 and st['used'] > 50000,
              'Worker: R2 caps can be lowered but never raised above the free tier')
        req = urllib.request.Request(base + '/admin/files/reports/all/extra.csv?key=' + key, data=b'x' * 1000, method='PUT')
        try:
            code = urllib.request.urlopen(req).status
        except urllib.error.HTTPError as e:
            code = e.code
        check(code == 507, 'Worker: refuses to store more than the storage cap')
        r = subprocess.run([PY, os.path.join(ROOT, 'tools', 'cloud_sync.py'), '--site', base, '--key', key, '--force'], capture_output=True, text=True, timeout=300)
        check(r.returncode != 0 and 'over the limit' in (r.stdout + r.stderr), 'reports job stops before going over the storage cap')
        check(0 < st['db'] and st['limits']['db'] == 1000, 'Worker: knows the database size (data cap, at most 450 MB: D1 is free up to 500 MB)')
        body = urllib.parse.urlencode({'study': 'pilot-asd', 'count': '1'}).encode()
        urllib.request.urlopen(urllib.request.Request(base + '/admin/invites?key=' + key, data=body, method='POST'))
        inv = list(csv.DictReader(io.StringIO(http('GET', base + '/admin/invites.csv?key=%s&study=pilot-asd' % key)[1].decode('utf-8-sig'))))[-1]
        check('not taking new participants' in json.loads(http('GET', base + '/api/start?i=' + inv['invite'])[1]).get('error', '')
              and json.loads(http('GET', base + '/api/start?pid=CFSMOKE1')[1]).get('pid') == 'CFSMOKE1',
              'Worker: over the data cap, new participants are turned away (returning ones can finish)')
        # last: this uses up the minute's new sessions for this address
        codes = [http('GET', base + '/api/start')[0] for _ in range(35)]
        check(429 in codes, 'Worker: too many new sessions from one address are refused')
    finally:
        os.killpg(srv.pid, 15)
        srv.wait(timeout=20)


def post_form(url, form):
    req = urllib.request.Request(url, method='POST', data=urllib.parse.urlencode(form).encode(),
                                 headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def client_checks(base, key, pid, label):
    """The device the participant page records (browser, system, time zone, trouble saving or in the page): listed on the
    Sessions tab and in the session list download, with the times also in Warsaw time."""
    sys.path.insert(0, os.path.join(ROOT, 'server'))
    import server as SRV
    cl = {'client': json.dumps({'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0', 'browser': 'Chrome 130', 'os': 'Windows 11', 'tz': 'Europe/Warsaw'}),
          'browser': 'Chrome 130', 'os': 'Windows 11', 'tz': 'Europe/Warsaw', 'save_fails': '2',
          'client_errors': json.dumps([['2026-11-10T12:00:00Z', 'build', 'TypeError: x'], ['2026-11-10T12:00:01Z', 'build', 'ReferenceError: y']])}
    check(http('POST', base + '/api/save', {'pid': pid, 'fields': cl})[0] == 200, label + 'saves the participant\'s browser, system and any trouble')
    row = next((r for r in api(base, 'sessions', key, study='all')['rows'] if r['pid'] == pid), {})
    rows = list(csv.DictReader(io.StringIO(http('GET', base + '/admin/sessions.csv?key=' + key)[1].decode('utf-8-sig'))))
    c = next((r for r in rows if r['pid'] == pid), {})
    check(row.get('browser') == 'Chrome 130' and row.get('os') == 'Windows 11' and row.get('tz') == 'Europe/Warsaw' and row.get('save_fails') == '2'
          and c.get('browser') == 'Chrome 130' and c.get('os') == 'Windows 11' and c.get('n_client_errors') == '2' and c.get('save_fails') == '2'
          and c.get('started_warsaw') == SRV.warsaw(c.get('started')) and c.get('started_warsaw') not in (None, '', 'NA')
          and all(r.get('browser') == 'NA' for r in rows if r['pid'] != pid),
          label + 'Sessions tab and session list (.csv): browser, system, time zone, retried saves, page errors, times in Warsaw time (NA where not recorded)')
    one = api(base, 'session', key, pid=pid) or {}
    listed = api(base, 'sessions', key, study='all', pids=pid + ',nosuchone')['rows']
    check(one.get('record', {}).get('browser') == 'Chrome 130' and one.get('row', {}).get('pid') == pid and [r['pid'] for r in listed] == [pid],
          label + 'one session opens with every field (the session panel, #sessions/<id>); a report\'s list of ids filters the Sessions tab')


def counting_checks(base, key, fields, label):
    """The "built a pizza" counter, the Sessions tab and the analysis use one rule: the own pizza was finished (its
    summary), not the stage the session was left at; a late, older save never moves a session back; a program-driven
    browser is left out automatically."""
    def built():
        return next(x for x in api(base, 'state', key)['studies'] if x['id'] == 'main')['built']
    before = built()
    pids = [json.loads(http('GET', base + '/api/start?pid=CNT%d' % i)[1])['pid'] for i in range(4)]
    unfinished = dict(fields, pz_summary=json.dumps(dict(json.loads(fields['pz_summary']), finished=False)))
    http('POST', base + '/api/save', {'pid': pids[0], 'stage': 'build', 'fields': fields})                    # finished, tab closed while baking
    http('POST', base + '/api/save', {'pid': pids[1], 'stage': 'build', 'fields': unfinished})                # still building
    http('POST', base + '/api/save', {'pid': pids[2], 'stage': 'followup', 'fields': fields})
    http('POST', base + '/api/save', {'pid': pids[2], 'stage': 'build', 'fields': {}})                        # an older save arriving late
    http('POST', base + '/api/save', {'pid': pids[3], 'stage': 'done', 'fields': dict(fields, browser_flags='automated')})
    rows = {r['pid']: r for r in api(base, 'sessions', key, study='main')['rows']}
    check(built() - before == 2 and rows[pids[0]]['analysis'] == 'included' and rows[pids[1]]['analysis'] == 'left_out'
          and rows[pids[2]]['stage'] == 'followup' and rows[pids[2]]['analysis'] == 'included' and rows[pids[3]]['analysis'] == 'left_out',
          label + '"built a pizza" counts the finished pizzas the reports analyse (one closed while baking counts, one still being built does not); '
          'a late older save does not move a session back; a program-driven browser is left out automatically')
    flagged = {r['pid'] for r in api(base, 'sessions', key, study='main', stage='flagged')['rows']}
    check(pids[3] in flagged and pids[0] not in flagged, label + 'Sessions tab: the "needs a look" filter finds browser flags')
    for p_ in pids:
        post_form(base + '/admin/api/inclusion?key=' + key, {'pid': p_, 'value': 'exclude'})   # out of the way of later counts


def inclusion_checks(base, key, skey, study, other_pid, label):
    """The Sessions tab's Analysis choice: set by a researcher (not by a participant's save), shown and filtered."""
    row = api(base, 'sessions', key, study=study)['rows'][0]
    pid = row['pid']
    http('POST', base + '/api/save', {'pid': pid, 'stage': row['stage'], 'fields': {'inclusion': 'exclude'}})
    find = lambda **f: next((r for r in api(base, 'sessions', key, study=study, **f)['rows'] if r['pid'] == pid), None)
    check(find()['inclusion'] == '', label + 'a participant\'s save cannot set whether they are analysed')
    code, body = post_form(base + '/admin/api/inclusion?key=' + key, {'pid': pid, 'value': 'exclude'})
    check(code == 200 and json.loads(body)['ok'] and find()['inclusion'] == 'exclude' and find(stage='left_out') and not find(stage='included'),
          label + 'Sessions tab: a researcher excludes a session; it shows, and the "left out" filter finds it')
    code, body = http('GET', base + '/admin/sessions.csv?' + urllib.parse.urlencode({'key': key, 'study': study}))
    rows = list(csv.DictReader(io.StringIO(body.decode('utf-8-sig')))) if code == 200 else []
    mine = [r for r in rows if r['pid'] == pid]
    check(mine and mine[0]['analysis'] == 'left_out' and mine[0]['inclusion'] == 'exclude' and all(r['analysis'] in ('included', 'left_out', 'no_pizza') for r in rows),
          label + 'the session list download says what the analysis does with each session, and the researcher\'s choice')
    code, _ = post_form(base + '/admin/api/inclusion?key=' + skey, {'pid': other_pid, 'value': 'include'})
    check(code == 404, label + 'a study\'s researcher link cannot change a session of another study')
    check(http('GET', base + '/admin/api/session?' + urllib.parse.urlencode({'key': skey, 'pid': other_pid}))[0] == 404,
          label + 'a study\'s researcher link cannot open a session of another study')
    code, _ = post_form(base + '/admin/api/inclusion?key=' + skey, {'pid': pid, 'value': 'auto'})
    check(code == 200 and find()['inclusion'] == '', label + 'back to automatic')


def api(base, path, key, **params):
    """The researcher page's data (/admin/api/state or /admin/api/sessions) as JSON, or None."""
    code, body = http('GET', base + '/admin/api/' + path + '?' + urllib.parse.urlencode(dict(params, key=key)))
    return json.loads(body) if code == 200 else None


def key_of(link):
    return urllib.parse.parse_qs(urllib.parse.urlparse(link or '').query).get('key', ['missing'])[0]


def researcher_access_checks(base, key, study, n_study, n_all, other_pid, label):
    """The same checks on both servers: the study chooser, the owner's links, a study's researcher link (that study
    only) and the researcher link for all studies (every study, no link management)."""
    code, page = http('GET', base + '/admin?key=' + key)
    st = api(base, 'state', key)
    check(code == 200 and b'Choose a study' in page and st and st['scope'] == 'owner' and st['study'] is None
          and {s['id'] for s in st['studies']} >= {'main', study, 'tests'} and st['global_link'], label + 'researcher page: a study chooser with every study')
    one = api(base, 'state', key, study=study)
    check(one['study'] == study and one['studies'][[s['id'] for s in one['studies']].index(study)]['n'] == n_study, label + 'researcher page: one study with its counts')
    row = one['studies'][[s['id'] for s in one['studies']].index(study)]
    check(row['n'] == row['done'] + row['active'] + row['stopped'] and row['done'] <= row['built'] <= row['n']
          and api(base, 'sessions', key, study=study, stage='active')['total'] == row['active']
          and api(base, 'sessions', key, study=study, stage='stopped')['total'] == row['stopped'],
          label + 'sessions split into finished, in progress and stopped (no save for 30 minutes), with filters')
    skey = key_of(next(s['researcher_link'] for s in st['studies'] if s['id'] == study))
    sst, d = api(base, 'state', skey, study='main'), api(base, 'sessions', skey, study='main')
    check(sst['scope'] == 'study' and [s['id'] for s in sst['studies']] == [study] and not sst.get('global_link') and 'researcher_link' not in sst['studies'][0]
          and d['total'] == n_study and other_pid not in [r['pid'] for r in d['rows']], label + 'a study\'s researcher link sees that study only')
    gkey = key_of(st['global_link'])
    g = api(base, 'state', gkey)
    check(g and g['scope'] == 'all' and not g.get('global_link') and api(base, 'sessions', gkey, study='all')['total'] == n_all
          and http('POST', base + '/admin/study-key?key=' + gkey, {})[0] in (403, 404), label + 'the researcher link for all studies sees every study but changes no links')
    return skey


def cloudflare_only():
    """python3 tests/smoke_test.py --only cloudflare: just the Cloudflare section (about a minute), run by the deploy
    workflow before it deploys."""
    tmp = tempfile.mkdtemp(prefix='pizza-smoke-cf-')
    try:
        check(run('examples/simulate.py', os.path.join(tmp, 'sample'), '5', '6', 'AB'), 'simulate participants')
        sample = json.load(open(sorted(glob.glob(os.path.join(tmp, 'sample', '*.json')))[0], encoding='utf-8'))
        cloudflare_checks(tmp, {k: v for k, v in sample.items() if k.startswith('pz')})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('\n%s' % ('all checks passed' if not failures else '%d check(s) failed' % len(failures)))
    sys.exit(1 if failures else 0)


def main():
    if sys.argv[1:3] == ['--only', 'cloudflare']:
        return cloudflare_only()
    t_start = time.time()
    keep = os.environ.get('PIZZA_KEEP_OUTPUT')          # CI: keep the reports built from simulated data, as a run artifact
    tmp = tempfile.mkdtemp(prefix='pizza-smoke-')
    try:
        heading('analysis')
        check(run('examples/simulate.py', os.path.join(tmp, 'sample'), '5', '24', 'AB'), 'simulate 24 participants')
        check(run('examples/simulate.py', os.path.join(tmp, 'ref'), '9', '40', 'B'), 'simulate a reference of 40 pizzas')
        out = os.path.join(tmp, 'out')
        check(run('analysis/analyse.py', *sorted(glob.glob(os.path.join(tmp, 'sample', '*.json'))), '--group', 'group',
                  '--reference', *sorted(glob.glob(os.path.join(tmp, 'ref', '*.json'))), '--out', out), 'analyse.py runs')
        for f in ('participants.csv', 'ingredients_long.csv', 'events_long.csv', 'profiles.csv',
                  'dashboard.html', 'profiles.html', 'arrangement.html', 'gallery.html', 'explore.html', 'explore.csv', 'methods.html',
                  'pieces_long.csv', 'removals_long.csv', 'adjustments_long.csv', 'variables.csv', 'load_pizza.R'):
            check(os.path.getsize(os.path.join(out, f)) > 0 if os.path.exists(os.path.join(out, f)) else False, 'writes ' + f)
        rows = list(csv.DictReader(open(os.path.join(out, 'participants.csv'), encoding='utf-8')))
        check(len(rows) == 24, 'one row per participant')
        ex = open(os.path.join(out, 'explore.html'), encoding='utf-8').read()
        planned = [r for r in csv.DictReader(open(os.path.join(out, 'explore.csv'), encoding='utf-8')) if r['grouping'] == 'planned']
        check(ex.count('class="hyp ') == 9 and 'Ideas to test' in ex and ex.count('class="cost"') == 9 and planned and all(r['q'] != '' for r in planned),
              'Explore: the 9 ideas to test, as their own family, each with its number of tests and the people it needs (rows in explore.csv)')
        pr = open(os.path.join(out, 'profiles.html'), encoding='utf-8').read()
        exrows = list(csv.DictReader(open(os.path.join(out, 'explore.csv'), encoding='utf-8')))
        screen = [r for r in exrows if r['grouping'] != 'planned']
        check('Against chance' not in ex and 'corrected over' in ex and not any(r['key'].startswith(('mv_', 'drop_', 'cons_')) or r['key'] in ('nut_vitC_mg', 'hover_total_ms') for r in screen)
              and 'n_per_group_80' not in exrows[0] and not any(r['grouping'] == 'neurotype' and r['vs'] == 'the rest' for r in screen),
              'Explore audit: one correction over the page, no chance tests, no movement/hover/micronutrient screening, neurotype against Not ND')
        check(('No clear clusters' in pr) != ('Compare two clusters' in pr) and 'Compare two participants' not in pr
              and 'Searching for types' in pr and pr.count('<td class="l">') >= 4 and 'Build behaviour and preferences' in pr,
              'Profiles: types searched in four families against no-types datasets; clusters only when they pass; behaviour × preferences')

        leads = ex[ex.index('id="leads"'):ex.index('id="g-')]
        check('Device (touch / mouse)' not in ex and 'id="other"' in ex and 'Gender' not in leads and 'Revealed the nutrition while building more often' not in ex
              and ex.index('id="planned"') < ex.index('id="leads"') < ex.index('id="g-'),
              'Explore: ideas first, leads only from the study\'s groupings, demographics folded away, no grouping compared on the measure that defines it')
        mh = open(os.path.join(out, 'methods.html'), encoding='utf-8').read()
        check('id="sample-sizes"' in mh and '<b>38</b> per group' in mh and 'Noether' in mh and 'n_per_group' in ex.split('Ideas to test')[0] + mh,
              'Methods: how the sample sizes are worked out, with worked examples checked against the code')
        # a build saved part-way but never finished (the participant stopped before "I'm done") is left out and listed
        src = sorted(glob.glob(os.path.join(tmp, 'sample', '*.json')))
        part = os.path.join(tmp, 'partial'); os.makedirs(part)
        for i, path in enumerate(src[:3]):
            d = json.load(open(path, encoding='utf-8'))
            if i == 2:
                summ = d['pz_summary'] if isinstance(d['pz_summary'], dict) else json.loads(d['pz_summary'])
                summ['finished'] = False
                d['pz_summary'] = summ
                for k in [k for k in d if k.startswith('pzt_')]:
                    del d[k]
            d['stage'] = 'build' if i == 2 else 'done'
            json.dump(d, open(os.path.join(part, 'p%d.json' % i), 'w', encoding='utf-8'))
        pout = os.path.join(tmp, 'out-partial')
        ok = run('analysis/analyse.py', *sorted(glob.glob(os.path.join(part, '*.json'))), '--out', pout)
        prow = list(csv.DictReader(open(os.path.join(pout, 'participants.csv'), encoding='utf-8'))) if ok else []
        exc = list(csv.DictReader(open(os.path.join(pout, 'excluded.csv'), encoding='utf-8'))) if ok else []
        dc = json.load(open(os.path.join(pout, 'data_check.json'), encoding='utf-8')) if ok else {}
        check(ok and 'p2' not in {r['pid'] for r in prow} and [(r['pid'], r['build'], r['reason']) for r in exc] == [('p2', 'pz', 'not finished')],
              'an unfinished build is left out of the analysis and listed in excluded.csv')
        check(dc.get('own') == 2 and dc.get('left_out') == 1 and dc.get('built_sessions') == 2 and dc.get('ok') is True
              and 'Data check' in open(os.path.join(pout, 'dashboard.html'), encoding='utf-8').read(),
              'data check: analysed own pizzas match the sessions past the build, shown on the overview')
        # the researcher's choice on the Sessions tab overrides the rule: keep the unfinished pizza in, leave a finished one out
        for name, v in (('p0', 'exclude'), ('p2', 'include')):
            d = json.load(open(os.path.join(part, name + '.json'), encoding='utf-8'))
            d['inclusion'] = v
            json.dump(d, open(os.path.join(part, name + '.json'), 'w', encoding='utf-8'))
        ok = run('analysis/analyse.py', *sorted(glob.glob(os.path.join(part, '*.json'))), '--out', pout)
        prow = list(csv.DictReader(open(os.path.join(pout, 'participants.csv'), encoding='utf-8'))) if ok else []
        dc = json.load(open(os.path.join(pout, 'data_check.json'), encoding='utf-8')) if ok else {}
        check(ok and sorted((r['pid'], r['inclusion']) for r in prow if r['build'] == 'pz') == [('p1', 'auto'), ('p2', 'researcher')]
              and dc.get('ok') is True and dc.get('researcher_excluded') == ['p0'],
              'a researcher\'s include / exclude overrides the automatic rule, and the data check still adds up')
        for col in ('diet_class', 'atypicality_pct', 'mirror_match', 'mirror_score', 'rot_score', 'n_on_crust', 'face_detected', 'size_match_same', 't_submit', 'cluster',
                    'n_strong', 'n_safe_foods', 'n_sensory_reasons', 'neurotype', 'nd_identified', 'eat_any', 'self_picky', 'age_band',
                    'mv_straight', 'mv_pauses', 'mv_dwell', 'group', 'nut_kcal', 'nut_salt_g', 'top_kcal', 'nutrition_panel', 'n_adjustments',
                    'n_adj_symmetry', 'adj_symmetry_excess', 'revision_rate', 'nutri_revealed', 'n_changed_mind', 'post_nutri_d_kcal', 'post_nutri_direction'):
            check(col in rows[0], 'column ' + col)
        own_rows = [r for r in rows if r['build'] == 'pz']
        check(own_rows and all(r['meat_or_fish'] == str(int(r['diet_class'] in ('meat', 'pescatarian'))) for r in own_rows)
              and any(r['diet_class'] == 'pescatarian' for r in own_rows),
              'meat_or_fish is 1 exactly for pizzas with meat or seafood (anchovies, shrimp, tuna count)')
        # the nutrition-reveal setting (every other simulated participant): columns filled only where it was on, and the
        # replay that finds the pizza at the moment the nutrition was seen ends with exactly the finished pizza
        on = [r for r in rows if r['nutrition_reveal'] == '1']
        off = [r for r in rows if r['nutrition_reveal'] == '0']
        check(on and off and all(r['nutri_seen'] == '1' and r['post_nutri_direction'] != 'NA' for r in on)
              and all(r['nutri_revealed'] == 'NA' and r['post_nutri_d_kcal'] == 'NA' for r in off)
              and any(r['nutri_revealed'] == '1' for r in on) and any(r['n_changed_mind'] == '1' for r in on),
              'reveal setting: who revealed, changed their mind and how the pizza changed, only where it was on')
        sys.path[:0] = [os.path.join(ROOT, 'analysis')]
        import analyse as AN
        ok_replay = True
        for path in sorted(glob.glob(os.path.join(tmp, 'sample', '*.json'))):
            d = json.load(open(path, encoding='utf-8'))
            fin, ev = json.loads(d['pz_final']), json.loads(d['pz_events'])
            st = AN.replay_pieces(ev, len(ev) - 1, {f[0]: f[5] for f in fin})
            ok_replay &= sorted((k, v['ing'], round(v['s'], 6)) for k, v in st.items()) == sorted((f[0], f[1], round(f[5] * f[8], 6)) for f in fin)
        check(ok_replay, 'reveal setting: the replay of every simulated log ends with the finished pizza, sizes included')
        # every output column must be described on the Methods page (analysis/methods.py)
        sys.path[:0] = [os.path.join(ROOT, 'analysis')]
        import methods
        for f in ('participants', 'ingredients_long', 'events_long', 'profiles', 'explore', 'pieces_long', 'removals_long', 'adjustments_long'):
            missing = methods.undocumented(next(csv.reader(open(os.path.join(out, f + '.csv'), encoding='utf-8'))))
            check(not missing, 'Methods page describes every column of %s.csv%s' % (f, (' - missing: ' + ', '.join(missing)) if missing else ''))
        var = list(csv.DictReader(open(os.path.join(out, 'variables.csv'), encoding='utf-8')))
        check(all(v['description'] and v['type'] for v in var), 'variables.csv gives every column a type and a description')
        check(all(v != '' for r in rows for v in r.values()), 'participants.csv writes missing values as NA, never blank')
        if shutil.which('Rscript'):
            r_code = ('source("load_pizza.R"); pz <- load_pizza("."); w <- pizza_wide(pz); '
                      'stopifnot(is.factor(pz$participants$neurotype), is.ordered(pz$participants$diet_class), is.integer(pz$participants$n_pieces), '
                      'nrow(w) == length(unique(pz$participants$pid)), nrow(pz$pieces_long) == sum(pz$participants$n_pieces)); cat("R-OK")')
            res = subprocess.run(['Rscript', '-e', r_code], cwd=out, capture_output=True, text=True)
            check(res.returncode == 0 and 'R-OK' in res.stdout and 'Warning' not in res.stderr, 'R: load_pizza() reads every table with its types%s' % (
                '' if res.returncode == 0 else ' - ' + res.stderr[-300:]))
        else:
            print('  skip  R checks (Rscript not installed)')
        ex = open(os.path.join(out, 'explore.html'), encoding='utf-8').read()
        tests = list(csv.DictReader(open(os.path.join(out, 'explore.csv'), encoding='utf-8')))
        check('Neurotype (self-described)' in ex and 'Recruitment group' in ex and {'neurotype', 'group'} <= {t['grouping'] for t in tests},
              'explore.html screens the self-described neurotype and the study-link group')
        check(all(0 <= float(t['q']) <= 1 and -1 <= float(t['delta']) <= 1 for t in tests), 'explore.csv: effect sizes in -1..1, q in 0..1')

        # a pilot's first sessions: one participant with a plain pizza, then two; every chart must cope with all-equal values
        first = sorted(glob.glob(os.path.join(tmp, 'sample', '*.json')))[:2]
        plain = json.load(open(first[0], encoding='utf-8'))
        plain.update(pz_final='[]', pz_events=json.dumps([[0, 'start', ''], [3000, 'done'], [3400, 'finish']]))
        json.dump(plain, open(os.path.join(tmp, 'plain.json'), 'w'))
        check(run('analysis/analyse.py', os.path.join(tmp, 'plain.json'), '--group', 'group', '--out', os.path.join(tmp, 'o1')), 'one participant with a plain pizza')
        check(run('analysis/analyse.py', os.path.join(tmp, 'plain.json'), first[1], '--group', 'group', '--out', os.path.join(tmp, 'o2')), 'two participants')

        heading('study server')
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        data = os.path.join(tmp, 'data')
        # a session saved as a file by an earlier server version, to be imported into the database on start
        os.makedirs(os.path.join(data, 'participants'))
        legacy = dict(json.load(open(sorted(glob.glob(os.path.join(tmp, 'sample', '*.json')))[1], encoding='utf-8')),
                      pid='OLD001', stage='done', group='NT', started='2026-01-02T10:00:00Z', updated='2026-01-02T10:05:00Z')
        json.dump(legacy, open(os.path.join(data, 'participants', 'OLD001.json'), 'w', encoding='utf-8'))
        srv = subprocess.Popen([PY, 'server/server.py', '--port', str(port), '--data', data, '--key', 'smoke-key'], cwd=ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = 'http://127.0.0.1:%d' % port
        try:
            for _ in range(50):
                try:
                    http('GET', base + '/study.json')
                    break
                except OSError:
                    time.sleep(0.2)
            # the test study starts with its synthetic sessions (study.json "synthetic"); check them, then remove them so
            # the counts below are of the sessions this test makes
            syn = api(base, 'state', 'smoke-key', study='tests')
            trow = next(r for r in syn['studies'] if r['id'] == 'tests')
            code, _ = post_form(base + '/admin/api/synthetic?key=smoke-key', {'study': 'tests', 'n': '25'})
            st25 = api(base, 'state', 'smoke-key', study='tests')
            r25 = next(r for r in st25['studies'] if r['id'] == 'tests')
            d25 = api(base, 'sessions', 'smoke-key', study='tests', stage='synthetic')
            real = api(base, 'sessions', 'smoke-key', study='tests', stage='real')
            check(trow['synthetic'] and trow['synthetic']['n'] == 100 and trow['synthetic']['stored'] == 100 and trow['n'] == 0
                  and code == 200 and r25['synthetic']['stored'] == 25 and d25['total'] == 25 and all(r['pid'].startswith('SYN-') for r in d25['rows'])
                  and real['total'] == 0 and post_form(base + '/admin/api/synthetic?key=smoke-key', {'study': 'main', 'n': '25'})[0] == 404,
                  'synthetic data: the test study starts with 100, the chooser sets 25, flagged and filtered, left out of the real counts; only for the test study')
            rep = http('GET', base + '/admin/reports/explore.html?' + urllib.parse.urlencode({'key': 'smoke-key', 'study': 'tests'}))[1].decode('utf-8', 'replace')
            check('Includes 25 synthetic pizzas' in rep and 'Ideas to test' in rep, 'synthetic data: the test study\'s reports are built from it, with a banner saying so')
            post_form(base + '/admin/api/synthetic?key=smoke-key', {'study': 'tests', 'n': '0'})
            check(api(base, 'sessions', 'smoke-key', study='tests')['total'] == 0, 'synthetic data: 0 removes it')
            code, page = http('GET', base + '/')
            check(code == 200 and b'pizza-builder.js' in page and b'Part ' not in page, 'participant page (the task only: no part counter)')
            check('nutrition_reveal' in json.loads(http('GET', base + '/study.json')[1]), 'passes the nutrition-reveal setting to the page')
            check(http('GET', base + '/pizza-builder.js')[0] == 200, 'serves the task script')
            code, body = http('GET', base + '/api/start?group=ASD&pid=SMOKE001')
            check(code == 200 and json.loads(body)['pid'] == 'SMOKE001', 'starts a session')
            sample = json.load(open(sorted(glob.glob(os.path.join(tmp, 'sample', '*.json')))[0], encoding='utf-8'))
            fields = {k: v for k, v in sample.items() if k.startswith('pz')}
            check(http('POST', base + '/api/save', {'pid': 'SMOKE001', 'stage': 'done', 'fields': fields})[0] == 200, 'saves a session')
            check(http('POST', base + '/api/save', {'pid': '../../etc', 'fields': {'pz_final': '[]'}})[0] == 404, 'rejects a bad participant id')
            check(http('GET', base + '/admin')[0] == 403, 'researcher page needs the password')
            check('SMOKE001' in [r['pid'] for r in api(base, 'sessions', 'smoke-key', study='all')['rows']], 'researcher page lists the session')
            code, page = http('POST', base + '/admin/reports?key=smoke-key')
            check(code == 200 and os.path.exists(os.path.join(data, 'reports', 'dashboard.html')), 'builds the reports')
            check(os.path.exists(os.path.join(data, 'reports', 'explore.html')), 'builds the explore report')
            code, page = http('GET', base + '/admin/methods?key=smoke-key')
            check(code == 200 and b'how every number is counted' in page, 'serves the Methods page')
            code, z = http('GET', base + '/admin/r.zip?key=smoke-key')
            names = zipfile.ZipFile(io.BytesIO(z)).namelist() if code == 200 and z[:2] == b'PK' else []
            check({'pizza-data/variables.csv', 'pizza-data/load_pizza.R', 'pizza-data/pieces_long.csv', 'pizza-data/README.txt',
                   'pizza-data/raw/SMOKE001.json'} <= set(names), 'downloads the data for R as a zip')
            code, z = http('GET', base + '/admin/data.zip?key=smoke-key')
            check(code == 200 and z[:2] == b'PK', 'downloads all data as a zip')
            # a study-specific pilot: personal invite links and an open study link, kept apart and filterable
            body = urllib.parse.urlencode({'study': 'pilot-asd', 'group': 'ASD', 'source': 'charity', 'count': '3'}).encode()
            req = urllib.request.Request(base + '/admin/invites?key=smoke-key', data=body, method='POST')
            try:
                urllib.request.urlopen(req)
            except urllib.error.HTTPError:
                pass
            code, inv_csv = http('GET', base + '/admin/invites.csv?key=smoke-key&study=pilot-asd')
            invites = list(csv.DictReader(io.StringIO(inv_csv.decode('utf-8-sig'))))
            check(code == 200 and len(invites) == 3 and invites[0]['link'].endswith('?i=' + invites[0]['invite']), 'makes personal invite links')
            started = [json.loads(http('GET', base + '/api/start?i=' + i['invite'])[1]) for i in invites]
            check(all(st.get('pid') == i['invite'] for st, i in zip(started, invites)), 'an invite link is its participant\'s id')
            check('error' in json.loads(http('GET', base + '/api/start?i=nosuchone')[1]) and 'error' in json.loads(http('GET', base + '/api/start?study=nosuchstudy')[1]),
                  'refuses unknown invite and study links')
            # coming back mid-study: the session reports where it was, with what the follow-up needs
            http('POST', base + '/api/save', {'pid': started[0]['pid'], 'stage': 'followup', 'fields': {'pz_counts': 'pep:2', 'restarts': '1'}})
            back = json.loads(http('GET', base + '/api/start?i=' + invites[0]['invite'])[1])
            check(back.get('stage') == 'followup' and back.get('counts') == 'pep:2' and back.get('restarts') == '1',
                  'a returning participant resumes at their part, with the build\'s counts and restart count')
            for st in started:
                http('POST', base + '/api/save', {'pid': st['pid'], 'stage': 'done', 'fields': fields})
            check(api(base, 'sessions', 'smoke-key', study='pilot-asd')['total'] == 3, 'researcher page filters by study')
            d = api(base, 'sessions', 'smoke-key', study='all', stage='done', sort='n_pieces', dir='asc')
            check(d['total'] == 5 and 'OLD001' in [r['pid'] for r in d['rows']]
                  and [r['n_pieces'] for r in d['rows']] == sorted(r['n_pieces'] for r in d['rows']), 'filters by stage and sorts')
            check(api(base, 'sessions', 'smoke-key', study='all', q='nobody')['total'] == 0, 'searches by participant id')
            code, csv_all = http('GET', base + '/admin/sessions.csv?key=smoke-key')
            rows = list(csv.DictReader(io.StringIO(csv_all.decode('utf-8-sig'))))
            check(code == 200 and {r['pid'] for r in rows} == {'SMOKE001', 'OLD001'} | {i['invite'] for i in invites}
                  and {r['study'] for r in rows} == {'main', 'pilot-asd'}, 'session list (.csv) holds every session')
            # each study's researcher link sees, analyses and exports that study only
            client_checks(base, 'smoke-key', 'SMOKE001', '')
            skey = researcher_access_checks(base, 'smoke-key', 'pilot-asd', 3, 5, 'SMOKE001', '')
            inclusion_checks(base, 'smoke-key', skey, 'pilot-asd', 'SMOKE001', '')
            # the R download carries analysed sessions only: an excluded one is in neither the tables nor raw/
            gone = invites[1]['invite']
            post_form(base + '/admin/api/inclusion?key=smoke-key', {'pid': gone, 'value': 'exclude'})
            zf = zipfile.ZipFile(io.BytesIO(http('GET', base + '/admin/r.zip?key=smoke-key&study=pilot-asd')[1]))
            pc = {r['pid'] for r in csv.DictReader(io.StringIO(zf.read('pizza-data/participants.csv').decode('utf-8')))}
            raw = {n.split('/')[-1][:-5] for n in zf.namelist() if n.startswith('pizza-data/raw/')}
            check(gone not in pc and gone not in raw and raw == pc and gone in zf.read('pizza-data/excluded.csv').decode('utf-8'),
                  'the R download leaves an excluded session out of raw/ too (only its id and reason in excluded.csv)')
            post_form(base + '/admin/api/inclusion?key=smoke-key', {'pid': gone, 'value': 'auto'})
            code, z = http('GET', base + '/admin/r.zip?key=' + skey)
            pc = list(csv.DictReader(io.StringIO(zipfile.ZipFile(io.BytesIO(z)).read('pizza-data/participants.csv').decode('utf-8'))))
            check(len(pc) == 3 and {r['study'] for r in pc} == {'pilot-asd'}, 'a study\'s researcher link downloads that study only')
            code, dbb = http('GET', base + '/admin/database.sqlite?key=' + skey)
            dbp = os.path.join(tmp, 'study-copy.db')
            open(dbp, 'wb').write(dbb)
            con = sqlite3.connect(dbp)
            check(code == 200 and con.execute('SELECT DISTINCT study FROM sessions').fetchall() == [('pilot-asd',)]
                  and con.execute('SELECT COUNT(*) FROM study_keys').fetchone()[0] == 0, 'a study\'s database copy holds that study only, without keys')
            con.close()
            check(http('POST', base + '/admin/study-key?key=' + skey, {})[0] in (403, 404), 'only the owner can change researcher links')
            code, z = http('GET', base + '/admin/r.zip?key=smoke-key&study=pilot-asd')
            zf = zipfile.ZipFile(io.BytesIO(z))
            pc = list(csv.DictReader(io.StringIO(zf.read('pizza-data/participants.csv').decode('utf-8'))))
            check(len(pc) == 3 and {r['study'] for r in pc} == {'pilot-asd'} and {r['source'] for r in pc} == {'charity'},
                  'per-study data download holds only that study, with group and source')
            con = sqlite3.connect(os.path.join(data, 'study.db'))
            grp = con.execute("SELECT grp FROM sessions WHERE pid = 'SMOKE001'").fetchone()
            nf = con.execute("SELECT COUNT(*) FROM fields WHERE pid = 'SMOKE001' AND name = 'pz_final'").fetchone()[0]
            old = con.execute("SELECT stage, grp FROM sessions WHERE pid = 'OLD001'").fetchone()
            con.close()
            check(grp == ('ASD',) and nf == 1, 'the database has the session, its group and the pizza')
            check(old == ('done', 'NT'), 'sessions saved as files by earlier versions are imported')
            ok = run('analysis/analyse.py', os.path.join(data, 'study.db'), '--study', 'pilot-asd', '--out', os.path.join(tmp, 'from-db'))
            pc = list(csv.DictReader(open(os.path.join(tmp, 'from-db', 'participants.csv'), encoding='utf-8'))) if ok else []
            check(len(pc) == 3 and {r['study'] for r in pc} == {'pilot-asd'}, 'analyse.py reads the database, one study at a time (--study)')
            # Pizza Pilot 11.2026: its own flow (Polish, consent yes / no, metryczka, its cheeses, the baked pizza at the end)
            pst = json.loads(http('GET', base + '/study.json?study=pilot-2026-11')[1])
            check(pst['title'] == 'Pizza Pilot 11.2026' and pst['lang'] == 'pl' and pst['consent_choice'] is True and pst['followup'] == 'metryczka'
                  and pst['cheeses'] == ['none', 'light', 'extra', 'vegan'] and pst['nutrition_panel'] is True and pst['bake_picture'] is True and pst['show_code'] is False,
                  'Pizza Pilot 11.2026: Polish, consent yes / no, metryczka, its cheeses, nutrition table, the baked pizza at the end')
            pids = [json.loads(http('GET', base + '/api/start?study=pilot-2026-11')[1])['pid'] for _ in range(3)]
            http('POST', base + '/api/save', {'pid': pids[0], 'stage': 'declined', 'fields': {'consent': 'declined 2026-11-08T10:00:00Z'}})
            met = {'style': 'metryczka', 'finished': True, 'met': {'age': 31, 'autism': 'self', 'adhd': 'no', 'gender': 'nonbinary', 'trans': 'yes', 'diet': ['vegan', 'allergy'],
                                                                 'sleep': 'good', 'hours': 7, 'pets': ['cat', 'other'], 'petsOther': 'axolotl'},
                   'survey': [{'id': 'age', 'type': 'number'}, {'id': 'sleep', 'type': 'single'}, {'id': 'hours', 'type': 'number'}, {'id': 'pets', 'type': 'multi'}],
                   'about': {'neuro': ['autistic'], 'dx': {'autistic': 'self'}, 'eating': [], 'age': '25-34', 'ageYears': 31, 'gender': 'nonbinary', 'trans': 'yes'},
                   'diet': ['vegan'], 'health': ['allergy'], 'dietOther': ''}
            vsum = dict(sample['pz_summary'] if isinstance(sample['pz_summary'], dict) else json.loads(sample['pz_summary']), cheese='vegan', sauce='tomato')
            vfin = [f for f in json.loads(sample['pz_final']) if f[1] not in ('pep', 'ham', 'chk', 'kan', 'anc', 'shr', 'tun', 'egg', 'gor')]
            http('POST', base + '/api/save', {'pid': pids[1], 'stage': 'done', 'fields': {'consent': '2026-11-08T10:00:00Z', 'pz_final': json.dumps(vfin),
                                                                                          'pz_summary': json.dumps(vsum), 'pz_events': sample['pz_events'] if isinstance(sample['pz_events'], str) else json.dumps(sample['pz_events']),
                                                                                          'pzf_data': json.dumps(met)}})
            # a pizza captured before tofu was on the tray (task 0.14.0): it still analyses, with tofu NA (not offered), not 0
            osum = dict(vsum, v='0.14.0', tray=[k for k in vsum['tray'] if k != 'tof'], sauce='bbq', cheese='none')
            ofin = [f for f in vfin if f[1] != 'tof']
            http('POST', base + '/api/save', {'pid': pids[2], 'stage': 'done', 'fields': {'consent': '2026-11-08T09:00:00Z', 'pz_final': json.dumps(ofin),
                                                                                          'pz_summary': json.dumps(osum), 'pz_events': sample['pz_events'] if isinstance(sample['pz_events'], str) else json.dumps(sample['pz_events']),
                                                                                          'pzf_data': json.dumps(met)}})
            pl = api(base, 'state', 'smoke-key', study='pilot-2026-11')
            prow = next(r for r in pl['studies'] if r['id'] == 'pilot-2026-11')
            dec = api(base, 'sessions', 'smoke-key', study='pilot-2026-11', stage='declined')
            check(prow['title'] == 'Pizza Pilot 11.2026' and prow['n'] == 3 and prow['active'] == 0 and dec['total'] == 1 and pl['stages']['declined'],
                  'Pizza Pilot 11.2026: listed with its title; a refusal is its own stage, never "in progress"')
            ok = run('analysis/analyse.py', os.path.join(data, 'study.db'), '--study', 'pilot-2026-11', '--out', os.path.join(tmp, 'pilot'))
            pcs = {r['pid']: r for r in csv.DictReader(open(os.path.join(tmp, 'pilot', 'participants.csv'), encoding='utf-8'))} if ok else {}
            pc = [pcs.get(pids[1], {})]
            old, new = pcs.get(pids[2], {}), pcs.get(pids[1], {})
            ings = list(csv.DictReader(open(os.path.join(tmp, 'pilot', 'ingredients_long.csv'), encoding='utf-8'))) if ok else []
            check(old.get('n_tof') == 'NA' and new.get('n_tof') not in (None, '', 'NA') and old.get('diet_class') == 'vegan' and old.get('sauce') == 'bbq'
                  and old.get('sample_norm_dev') not in (None, '', 'NA') and old.get('n_pep') == '0' and not any(r['pid'] == pids[2] and r['ing'] == 'tof' for r in ings)
                  and any(r['pid'] == pids[1] and r['ing'] == 'tof' for r in ings),
                  'Pizza Pilot 11.2026: a pizza from before tofu (0.14.0) still analyses; its tofu count is NA (not offered), not 0; BBQ sauce keeps it vegan')
            check(len(pcs) == 2 and pc[0]['cheese'] == 'vegan' and pc[0]['diet_class'] == 'vegan' and pc[0]['age_years'] == '31' and pc[0]['age_band'] == '25-34'
                  and pc[0]['transgender'] == '1' and pc[0]['gender'] == 'nonbinary' and pc[0]['neurotype'] == 'Autistic' and pc[0]['dx_autistic'] == 'self'
                  and pc[0]['diet'] == 'vegan' and pc[0]['health_allergy'] == '1' and pc[0]['diet_special'] == '1'
                  and pc[0]['q_sleep'] == 'good' and pc[0]['q_hours'] == '7' and pc[0]['q_pets'] == 'cat other' and pc[0]['q_pets_cat'] == '1'
                  and pc[0]['q_pets_text'] == 'axolotl' and pc[0]['q_pets_other'] == '1' and 'q_age' not in pc[0],
                  'Pizza Pilot 11.2026: the analysis reads the metryczka (age, transgender, autism / ADHD, gender, diets) and vegan cheese keeps a pizza vegan')
            counting_checks(base, 'smoke-key', fields, '')
        finally:
            srv.terminate()
            srv.wait(timeout=10)

        cloudflare_checks(tmp, fields)

        if shutil.which('node'):
            heading('javascript')
            for f in ('pizza-builder.js', 'preview.js'):
                check(subprocess.run(['node', '--check', f], cwd=ROOT).returncode == 0, 'syntax ' + f)
            # the demo preview's face detector must give the same answers as analyse.py
            sys.path[:0] = [os.path.join(ROOT, 'tests'), os.path.join(ROOT, 'analysis')]
            import face_benchmark as FB
            g, cases = FB.Gen(3), []
            for _, make in FB.FACES + FB.NOT_FACES:
                for _ in range(15):
                    ps = make(g)
                    r = FB.A.face_detect(ps)
                    cases.append({'ps': ps, 'py': r and [sorted(r['eyes']), r['mouth'], r['nose'], r['deco']]})
            js = ("global.window = global; require(%s); const cs = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
                  "console.log(JSON.stringify(cs.map(c => { const r = PizzaPreview.faceDetect(c.ps);"
                  " return r && [r.eyes.slice().sort((a, b) => a - b), r.mouth, r.nose, r.deco]; })));" % json.dumps(os.path.join(ROOT, 'preview.js')))
            out = subprocess.run(['node', '-e', js], input=json.dumps(cases), capture_output=True, text=True)
            same = out.returncode == 0 and json.loads(out.stdout) == [c['py'] for c in cases]
            cases_faces = cases
            check(same, 'face detection agrees between preview.js and analyse.py (%d pizzas)' % len(cases))
            cases = []
            for c in cases_faces:
                if len(c['ps']) >= 2:
                    m, ax, ctr = FB.A.best_mirror(c['ps'])
                    r, k, _ = FB.A.best_rotation(c['ps'])
                    cases.append({'ps': c['ps'], 'py': [m, round(ax, 6), r, k]})
            js = ("global.window = global; require(%s); const cs = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
                  "console.log(JSON.stringify(cs.map(c => { const s = PizzaPreview.symmetry(c.ps); return [s.matched, Math.round(s.axis * 1e6) / 1e6, s.rotMatched, s.k]; })));"
                  % json.dumps(os.path.join(ROOT, 'preview.js')))
            out_ = subprocess.run(['node', '-e', js], input=json.dumps(cases), capture_output=True, text=True)
            check(out_.returncode == 0 and json.loads(out_.stdout) == [c['py'] for c in cases],
                  'symmetry (matches, axis, rotation) agrees between preview.js and analyse.py (%d pizzas)' % len(cases))
            # nutrition: the task's panel (PizzaBuilder.nutrition) and analyse.py give the same numbers
            ncases = []
            for path in sorted(glob.glob(os.path.join(tmp, 'sample', '*.json'))):
                d = json.load(open(path, encoding='utf-8'))
                summ = json.loads(d['pz_summary'])
                ps = [{'ing': f[1], 'x': f[2], 'y': f[3], 'rot': f[4], 's': f[5] * f[8], 'g': f[8]} for f in json.loads(d['pz_final'])]
                py = FB.A.nutrition_measures(ps, summ)
                ncases.append({'ps': [{'ing': p_['ing'], 'size': p_['s']} for p_ in ps], 'sauce': summ.get('sauce') or 'tomato', 'cheese': summ.get('cheese') or 'normal',
                               'py': [round(py[FB.A.NUT_COL[k]], 6) for k in FB.A.NUTRIENTS]})
                if len(ncases) <= 3:                       # and the same pizzas with vegan cheese
                    pv = FB.A.nutrition_measures(ps, dict(summ, cheese='vegan'))
                    ncases.append({'ps': ncases[-1]['ps'], 'sauce': ncases[-1]['sauce'], 'cheese': 'vegan', 'py': [round(pv[FB.A.NUT_COL[k]], 6) for k in FB.A.NUTRIENTS]})
            js = ("global.window = global; global.document = undefined; require(%s); const cs = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
                  "const K = %s; console.log(JSON.stringify(cs.map(c => { const t = PizzaBuilder.nutrition(c.ps, c.sauce, c.cheese, true); return K.map(k => Math.round(t[k] * 1e6) / 1e6); })));"
                  % (json.dumps(os.path.join(ROOT, 'pizza-builder.js')), json.dumps(FB.A.NUTRIENTS)))
            out_ = subprocess.run(['node', '-e', js], input=json.dumps(ncases), capture_output=True, text=True)
            got = json.loads(out_.stdout) if out_.returncode == 0 else []
            same = len(got) == len(ncases) and all(abs(a - b) < 1e-4 for c, g in zip(ncases, got) for a, b in zip(c['py'], g))
            check(same, 'nutrition agrees between the task (pizza-builder.js) and analyse.py (%d pizzas)%s' % (len(ncases), '' if out_.returncode == 0 else ' - ' + out_.stderr[-200:]))
            nut = json.load(open(os.path.join(ROOT, 'analysis', 'nutrition.json'), encoding='utf-8'))
            embedded = re.search(r'var NUTRITION = (\{.*?\});\n', open(os.path.join(ROOT, 'pizza-builder.js'), encoding='utf-8').read())
            check(embedded and json.loads(embedded.group(1)) == nut, 'the task embeds the same nutrition table as analysis/nutrition.json')
            # the participant page under privacy settings and blockers (the full browser runs are in docs/BROWSERS.md):
            # storage only through the guarded helpers, unsaved fields sent on leaving without relying on sendBeacon,
            # starts retried, the person check never left waiting, colours locked, a message without JavaScript
            pg = open(os.path.join(ROOT, 'server', 'participate.html'), encoding='utf-8').read()
            raw_storage = [m.start() for m in re.finditer(r'(?<!window\.)\b(sessionStorage|localStorage)\.', pg)]
            check(not raw_storage and "addEventListener('visibilitychange'" in pg and "keepalive: true" in pg and "'error-callback'" in pg
                  and 'name="darkreader-lock"' in pg and 'content="only light"' in pg and '<noscript>' in pg and 'r.status === 429' in pg,
                  'participant page: works with storage blocked, saves on leaving without sendBeacon, retries busy starts, never waits forever on the person check, keeps its colours, explains when JavaScript is off')
            # Warsaw time (session list download): the EU summer-time rule in server.py (and the Worker, checked against it
            # above) agrees with the time-zone database of node / the researcher's browser, around both changes of the clock
            sys.path.insert(0, os.path.join(ROOT, 'server'))
            import server as SRV
            ts = ['2026-03-29T00:59:59Z', '2026-03-29T01:00:00Z', '2026-10-25T00:59:59Z', '2026-10-25T01:00:00Z', '2026-11-10T13:35:12Z',
                  '2026-07-01T22:30:00Z', '2027-03-28T01:00:00Z', '2025-12-31T23:30:00Z', '2028-10-29T00:30:00Z']
            js = ("const f = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Warsaw', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'});"
                  "console.log(JSON.stringify(%s.map(t => f.format(new Date(t)))));" % json.dumps(ts))
            out_ = subprocess.run(['node', '-e', js], capture_output=True, text=True)
            check(out_.returncode == 0 and json.loads(out_.stdout) == [SRV.warsaw(t) for t in ts],
                  'Warsaw time in the session list agrees with the time-zone database, around summer time (%d times)' % len(ts))
            # every topping in every table (CLAUDE.md: the tables that must stay in step), tofu included
            js = ("global.window = global; global.document = undefined; require(%s); require(%s); var I = PizzaBuilder.ingredients;"
                  "var cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
                  "console.log(JSON.stringify({ing: Object.keys(I), tier: Object.keys(I).filter(k => I[k].tier), def: PizzaBuilder.defaultIngredients,"
                  " cat: Object.fromEntries(Object.keys(I).map(k => [k, I[k].cat])), pl: PizzaBuilder.names('pl'), vegan: PizzaBuilder.veganSauces.sort(),"
                  " diet: cases.map(c => PizzaPreview.dietClass(c.ps, c.summ))}));"
                  % (json.dumps(os.path.join(ROOT, 'pizza-builder.js')), json.dumps(os.path.join(ROOT, 'preview.js'))))
            A = FB.A
            dcases = [{'ps': [{'ing': i} for i in ps], 'summ': {'sauce': sa, 'cheese': ch}} for ps in ([], ['tof'], ['tof', 'mus'], ['egg'], ['tun'], ['pep', 'tof'])
                      for sa in (None, 'none', 'tomato', 'white', 'bbq') for ch in (None, 'none', 'light', 'normal', 'extra', 'vegan')]
            out_ = subprocess.run(['node', '-e', js], input=json.dumps(dcases), capture_output=True, text=True)
            t = json.loads(out_.stdout) if out_.returncode == 0 else {}
            real = [k for k in t.get('ing', []) if k != 'tom']
            pv_src = open(os.path.join(ROOT, 'preview.js'), encoding='utf-8').read()
            pv_tables = [re.search(r'var %s = \{(.*?)\};' % n, pv_src, re.S).group(1) for n in ('NAMES', 'FOOT', 'SIZE', 'CATS')]
            sim = {f: json.loads(re.search(r'^TRAY = (\[.*?\])$', open(os.path.join(ROOT, f), encoding='utf-8').read(), re.M).group(1).replace("'", '"'))
                   for f in ('examples/simulate.py', 'analysis/synthetic.py')}
            missing = [k for k in real if not (k in A.CATS and k in A.NAMES and k in A.TIER and k in A.SIZE and k in A.FOOT and k in A.COLORS
                                               and k in nut['toppings'] and k in t['tier'] and t['pl'].get(k) and all(re.search(r'\b%s:' % k, tb) for tb in pv_tables)
                                               and ('%s' % k) in open(os.path.join(ROOT, 'CODEBOOK.md'), encoding='utf-8').read())]
            check(out_.returncode == 0 and 'tof' in real and not missing and set(t['def']) <= set(real) and 'tof' in t['def']
                  and all(sim[n] == t['def'] for n in sim) and all(A.CATS[k] == t['cat'][k] or (A.CATS[k], t['cat'][k]) in (('seafood', 'fish'),) for k in real),
                  'every topping (tofu too) is in every table: task, analysis, preview, nutrition, Polish names, codebook, both simulators%s'
                  % (' - missing: ' + ', '.join(missing) if missing else '' if out_.returncode == 0 else ' - ' + out_.stderr[-200:]))
            pyc = [A.pizza_diet_class(c['ps'], c['summ']) for c in dcases]
            check(t.get('vegan') == sorted(k for k, v in A.SAUCE_DIET.items() if v == 'vegan' and k != 'none') == ['bbq', 'tomato']
                  and t.get('diet') == pyc and A.pizza_diet_class([{'ing': 'tof'}], {'sauce': 'bbq', 'cheese': 'vegan'}) == 'vegan'
                  and A.pizza_diet_class([{'ing': 'tof'}], {'sauce': 'white', 'cheese': 'none'}) == 'vegetarian'
                  and A.pizza_diet_class([], {'sauce': 'tomato', 'cheese': 'light'}) == 'vegetarian',
                  'sauces: the ones marked vegan in the task (tomato, BBQ) are the vegan ones in the analysis; the diet of the whole pizza (toppings, sauce, cheese) agrees between preview.js and analyse.py (%d bases and toppings)' % len(dcases))
            # a study's own wording (tools/texts.py): every text exported, overrides applied without touching the defaults
            tcsv = os.path.join(tmp, 'teksty.csv')
            ok = run('tools/texts.py', 'export', 'pilot-2026-11', tcsv)
            trows = list(csv.reader(open(tcsv, encoding='utf-8-sig')))[1:] if ok else []
            js = ("global.window = global; global.document = undefined; require(%s); var own = {'task.steps.2': 'S2', 'task.metDx.formal': 'F', 'names.pep': 'Salami', 'task.nutri.names.kcal': 'K'};"
                  "var T = PizzaBuilder.texts('pl', own), D = PizzaBuilder.texts('pl');"
                  "console.log(JSON.stringify([T.steps[1], T.metDx[1][1], PizzaBuilder.names('pl', own).pep, T.nutri.names.kcal, D.steps[1] !== 'S2', D.metDx[1][1] !== 'F', PizzaBuilder.text.steps[1] !== 'S2']));"
                  % json.dumps(os.path.join(ROOT, 'pizza-builder.js')))
            out_ = subprocess.run(['node', '-e', js], capture_output=True, text=True)
            check(len(trows) >= 120 and all(r[0] and r[2] for r in trows) and out_.returncode == 0 and json.loads(out_.stdout) == ['S2', 'F', 'Salami', 'K', True, True, True],
                  'tools/texts.py exports every text of Pizza Pilot 11.2026 (%d); a study\'s own wording replaces the built-in texts, the defaults stay' % len(trows))
            # every language complete (no text missing or left in English, same placeholders and answers) and every study's own texts valid
            r = subprocess.run([PY, os.path.join(ROOT, 'tools', 'texts.py'), 'check'], capture_output=True, text=True, timeout=300)
            check(r.returncode == 0 and 'all well' in r.stdout, 'texts: every language complete and every study\'s own texts valid (tools/texts.py check)' + ('' if r.returncode == 0 else ' - ' + r.stdout[-600:]))
            bad = json.load(open(os.path.join(ROOT, 'server', 'study.json'), encoding='utf-8'))
            bad['studies']['pilot-2026-11']['texts'] = {'task.nope': 'x', 'task.promptBuild': ' ', 'task.nutri.perSlice': 'no number', 'names.pep': 'Salami'}
            bad['studies']['pilot-2026-11']['survey'] = [{'id': 'age', 'type': 'number'}, {'id': 'Sleep', 'type': 'single'}, {'id': 'pets', 'type': 'multi', 'text': 'Pets?'},
                                                     {'id': 'mood', 'type': 'single', 'text': {'pl': 'Nastrój?'}, 'options': [['good', 'dobry'], ['bad', 'zły']]}]
            badp = os.path.join(tmp, 'bad-study.json')
            json.dump(bad, open(badp, 'w', encoding='utf-8'), ensure_ascii=False)
            r = subprocess.run([PY, os.path.join(ROOT, 'tools', 'texts.py'), 'check'], capture_output=True, text=True, timeout=300, env=dict(os.environ, PIZZA_STUDY_JSON=badp))
            d = subprocess.run([PY, os.path.join(ROOT, 'tools', 'texts.py'), 'diff', 'pilot-2026-11'], capture_output=True, text=True, timeout=300, env=dict(os.environ, PIZZA_STUDY_JSON=badp))
            check(r.returncode == 1 and 'task.nope: unknown key' in r.stdout and 'task.promptBuild: empty' in r.stdout and 'perSlice: must keep {x}' in r.stdout
                  and 'names.pep' not in r.stdout and 'names.pep' in d.stdout and 'Salami' in d.stdout
                  and 'survey: question 2: "id" must be' in r.stdout and 'survey: pets: needs "options"' in r.stdout and 'mood' not in r.stdout.split('survey:', 1)[-1].split('\n')[0],
                  'texts: a study\'s unknown, empty or placeholder-losing texts are caught, and a broken post-pizza survey; diff lists what a study changed')
            tcsv2 = os.path.join(tmp, 'teksty2.csv')
            env_bad = dict(os.environ, PIZZA_STUDY_JSON=badp)
            subprocess.run([PY, os.path.join(ROOT, 'tools', 'texts.py'), 'export', 'pilot-2026-11', tcsv2], capture_output=True, text=True, timeout=300, env=env_bad)
            srows = [x for x in csv.reader(open(tcsv2, encoding='utf-8-sig')) if x and x[0].startswith('survey.mood')]
            check([x[0] for x in srows] == ['survey.mood.text', 'survey.mood.options.good', 'survey.mood.options.bad'] and srows[0][2] == 'Nastrój?',
                  'texts: a study\'s own survey questions are in its texts sheet (wording and answers) for translation')
            g1 = FB.A.piece_grams({'ing': 'tom', 's': 1.0})
            check(abs(FB.A.piece_grams({'ing': 'tom', 's': 2.0}) - 4 * g1) < 1e-9 and abs(FB.A.piece_grams({'ing': 'tom', 's': 0.5}) - g1 / 4) < 1e-9,
                  'a piece twice as big weighs 4x (grams follow area)')

        heading('face benchmark')
        sys.path[:0] = [os.path.join(ROOT, 'tests'), os.path.join(ROOT, 'analysis')]
        import face_benchmark as FB
        res = FB.run(60, quiet=True)
        hit = sum(res[label] for label, _ in FB.FACES) / len(FB.FACES)
        fp = sum(res[label] for label, _ in FB.NOT_FACES) / len(FB.NOT_FACES)
        check(hit >= 0.7 and fp <= 0.05, 'finds %.0f%% of drawn faces, flags %.1f%% of non-faces' % (100 * hit, 100 * fp))
    finally:
        if keep and os.path.isdir(os.path.join(tmp, 'out')):
            shutil.copytree(os.path.join(tmp, 'out'), keep, dirs_exist_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        write_summary(os.environ['GITHUB_STEP_SUMMARY'], time.time() - t_start)
    print('\n%s' % ('all checks passed' if not failures else '%d check(s) failed' % len(failures)))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
