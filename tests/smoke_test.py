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
        code, page = http('GET', base + '/admin?key=%s&study=pilot-asd' % key)
        check(code == 200 and b'<b>2 sessions match</b>' in page and b'Studies and links' in page, 'Worker: researcher page filters by study')
        check(b'<b>3 sessions match</b>' in http('GET', base + '/admin?key=%s&stage=done&sort=n_pieces&dir=asc' % key)[1], 'Worker: filters by stage and sorts')
        rows = list(csv.DictReader(io.StringIO(http('GET', base + '/admin/sessions.csv?key=' + key)[1].decode('utf-8-sig'))))
        check({r['study'] for r in rows} == {'main', 'pilot-asd'} and len(rows) == 3, 'Worker: session list (.csv)')
        keys = set(re.findall(rb'admin\?key=([A-Za-z0-9_-]{12,})', http('GET', base + '/admin?key=' + key)[1])) - {key.encode()}
        skey = next((k.decode() for k in keys if b'for study <b>pilot-asd' in http('GET', base + '/admin?key=' + k.decode())[1]), 'missing')
        page = http('GET', base + '/admin?key=%s&study=main' % skey)[1]
        check(b'<b>2 sessions match</b>' in page and b'CFSMOKE1' not in page and b'New researcher link' not in page, 'Worker: a study\'s researcher link sees that study only')
        check(all(http(m, base + p + '?key=' + skey, b)[0] == 404 for m, p, b in
                  [('GET', '/admin/export', None), ('GET', '/admin/signatures', None), ('POST', '/admin/study-key', {})]),
              'Worker: a study\'s researcher link cannot export everything or change links')
        # the reports job, against this Worker
        r = subprocess.run([PY, os.path.join(ROOT, 'tools', 'cloud_sync.py'), '--site', base, '--key', key], capture_output=True, text=True, timeout=900)
        check(r.returncode == 0 and 'pilot-asd: 2 pizzas analysed' in r.stdout, 'reports job builds every study\'s reports and stores them')
        if r.returncode:
            print(r.stdout[-1500:], r.stderr[-1500:])
        check(b'Researcher page</a> \xc2\xb7 study pilot-asd' in http('GET', base + '/admin/reports/dashboard.html?key=' + skey)[1], 'Worker: serves a study\'s reports')
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
        r = subprocess.run([PY, os.path.join(ROOT, 'tools', 'cloud_sync.py'), '--site', base, '--key', key], capture_output=True, text=True, timeout=300)
        check(r.returncode == 0 and r.stdout.startswith('Up to date'), 'reports job does nothing when no session changed')
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


def main():
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
        for col in ('diet_class', 'atypicality_pct', 'mirror_match', 'mirror_score', 'rot_score', 'n_on_crust', 'face_detected', 'size_match_same', 't_submit', 'cluster',
                    'n_strong', 'n_safe_foods', 'n_sensory_reasons', 'neurotype', 'nd_identified', 'eat_any', 'self_picky', 'age_band',
                    'mv_straight', 'mv_pauses', 'mv_dwell', 'group', 'nut_kcal', 'nut_salt_g', 'top_kcal', 'nutrition_panel', 'n_adjustments',
                    'n_adj_symmetry', 'adj_symmetry_excess', 'revision_rate', 'nutri_revealed', 'n_changed_mind', 'post_nutri_d_kcal', 'post_nutri_direction'):
            check(col in rows[0], 'column ' + col)
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
            code, page = http('GET', base + '/admin?key=smoke-key')
            check(code == 200 and b'SMOKE001' in page and b'Studies and links' in page and b'Make personal links' in page, 'researcher page lists the session, studies and links')
            code, page = http('POST', base + '/admin/reports?key=smoke-key')
            check(code == 200 and os.path.exists(os.path.join(data, 'reports', 'dashboard.html')), 'builds the reports')
            check(os.path.exists(os.path.join(data, 'reports', 'explore.html')), 'builds the explore report')
            code, page = http('GET', base + '/admin/methods?key=smoke-key')
            check(code == 200 and b'how every number is counted' in page and b'Researcher page' in page, 'serves the Methods page')
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
            code, page = http('GET', base + '/admin?key=smoke-key&study=pilot-asd')
            check(code == 200 and b'<b>3 sessions match</b>' in page, 'researcher page filters by study')
            code, page = http('GET', base + '/admin?key=smoke-key&sort=n_pieces&desc=0&stage=done')
            check(code == 200 and b'<b>5 sessions match</b>' in page and page.index(b'OLD001') > 0, 'filters by stage and sorts')
            check(b'<b>0 sessions match</b>' in http('GET', base + '/admin?key=smoke-key&q=nobody')[1], 'searches by participant id')
            code, csv_all = http('GET', base + '/admin/sessions.csv?key=smoke-key')
            rows = list(csv.DictReader(io.StringIO(csv_all.decode('utf-8-sig'))))
            check(code == 200 and {r['pid'] for r in rows} == {'SMOKE001', 'OLD001'} | {i['invite'] for i in invites}
                  and {r['study'] for r in rows} == {'main', 'pilot-asd'}, 'session list (.csv) holds every session')
            # each study's researcher link sees, analyses and exports that study only
            keys = set(re.findall(rb'admin\?key=([A-Za-z0-9_-]{12,})', http('GET', base + '/admin?key=smoke-key')[1]))
            skey = next((k.decode() for k in keys if b'for study <b>pilot-asd' in http('GET', base + '/admin?key=' + k.decode())[1]), 'missing')
            code, page = http('GET', base + '/admin?key=%s&study=main' % skey)
            check(code == 200 and b'<b>3 sessions match</b>' in page and b'SMOKE001' not in page and b'New researcher link' not in page,
                  'a study\'s researcher link sees that study only')
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
