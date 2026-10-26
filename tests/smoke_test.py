#!/usr/bin/env python3
"""End-to-end check with nothing installed beyond Python 3.10+: simulate participants, analyse them, run the study
server, play one session through it, and use the researcher page. Exits non-zero on any failure.

    python3 tests/smoke_test.py
"""
import csv
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
failures = []


def check(cond, what):
    print(('  ok    ' if cond else '  FAIL  ') + what)
    if not cond:
        failures.append(what)


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


def main():
    tmp = tempfile.mkdtemp(prefix='pizza-smoke-')
    try:
        print('analysis')
        check(run('examples/simulate.py', os.path.join(tmp, 'sample'), '5', '24', 'AB'), 'simulate 24 participants')
        check(run('examples/simulate.py', os.path.join(tmp, 'ref'), '9', '40', 'B'), 'simulate a reference of 40 pizzas')
        out = os.path.join(tmp, 'out')
        check(run('analysis/analyse.py', *sorted(glob.glob(os.path.join(tmp, 'sample', '*.json'))), '--group', 'group',
                  '--reference', *sorted(glob.glob(os.path.join(tmp, 'ref', '*.json'))), '--out', out), 'analyse.py runs')
        for f in ('participants.csv', 'ingredients_long.csv', 'events_long.csv', 'profiles.csv',
                  'dashboard.html', 'profiles.html', 'arrangement.html', 'gallery.html'):
            check(os.path.getsize(os.path.join(out, f)) > 0 if os.path.exists(os.path.join(out, f)) else False, 'writes ' + f)
        rows = list(csv.DictReader(open(os.path.join(out, 'participants.csv'), encoding='utf-8')))
        check(len(rows) == 24, 'one row per participant')
        for col in ('diet_class', 'atypicality_pct', 'sym_mirror', 'n_on_crust', 'face_detected', 'size_match_same', 't_submit', 'cluster',
                    'n_strong', 'n_safe_foods', 'n_sensory_reasons'):
            check(col in rows[0], 'column ' + col)

        # a pilot's first sessions: one participant with a plain pizza, then two; every chart must cope with all-equal values
        first = sorted(glob.glob(os.path.join(tmp, 'sample', '*.json')))[:2]
        plain = json.load(open(first[0], encoding='utf-8'))
        plain.update(pz_final='[]', pz_events=json.dumps([[0, 'start', ''], [3000, 'done'], [3400, 'finish']]))
        json.dump(plain, open(os.path.join(tmp, 'plain.json'), 'w'))
        check(run('analysis/analyse.py', os.path.join(tmp, 'plain.json'), '--group', 'group', '--out', os.path.join(tmp, 'o1')), 'one participant with a plain pizza')
        check(run('analysis/analyse.py', os.path.join(tmp, 'plain.json'), first[1], '--group', 'group', '--out', os.path.join(tmp, 'o2')), 'two participants')

        print('study server')
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        data = os.path.join(tmp, 'data')
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
            check(code == 200 and b'pizza-builder.js' in page, 'participant page')
            check(http('GET', base + '/pizza-builder.js')[0] == 200, 'serves the task script')
            code, body = http('GET', base + '/api/start?group=ASD&pid=SMOKE001')
            check(code == 200 and json.loads(body)['pid'] == 'SMOKE001', 'starts a session')
            sample = json.load(open(sorted(glob.glob(os.path.join(tmp, 'sample', '*.json')))[0], encoding='utf-8'))
            fields = {k: v for k, v in sample.items() if k.startswith('pz')}
            check(http('POST', base + '/api/save', {'pid': 'SMOKE001', 'stage': 'done', 'fields': fields})[0] == 200, 'saves a session')
            check(http('POST', base + '/api/save', {'pid': '../../etc', 'fields': {'pz_final': '[]'}})[0] == 404, 'rejects a bad participant id')
            check(http('GET', base + '/admin')[0] == 403, 'researcher page needs the password')
            code, page = http('GET', base + '/admin?key=smoke-key')
            check(code == 200 and b'SMOKE001' in page and b'Links to send' in page, 'researcher page lists the session and links')
            code, page = http('POST', base + '/admin/reports?key=smoke-key')
            check(code == 200 and os.path.exists(os.path.join(data, 'reports', 'dashboard.html')), 'builds the reports')
            code, z = http('GET', base + '/admin/data.zip?key=smoke-key')
            check(code == 200 and z[:2] == b'PK', 'downloads all data as a zip')
            saved = json.load(open(os.path.join(data, 'participants', 'SMOKE001.json'), encoding='utf-8'))
            check(saved.get('group') == 'ASD' and 'pz_final' in saved, 'session file has the group and the pizza')
        finally:
            srv.terminate()
            srv.wait(timeout=10)

        if shutil.which('node'):
            print('javascript')
            for f in ('pizza-builder.js', 'preview.js'):
                check(subprocess.run(['node', '--check', f], cwd=ROOT).returncode == 0, 'syntax ' + f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('\n%s' % ('all checks passed' if not failures else '%d check(s) failed' % len(failures)))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
