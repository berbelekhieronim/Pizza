#!/usr/bin/env python3
"""End-to-end check with nothing installed beyond Python 3.10+: simulate participants, analyse them, run the study
server, play one session through it, and use the researcher page. Exits non-zero on any failure.

    python3 tests/smoke_test.py
"""
import csv
import glob
import io
import json
import os
import re
import shutil
import socket
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
                    'n_adj_symmetry', 'adj_symmetry_excess', 'revision_rate'):
            check(col in rows[0], 'column ' + col)
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
            for st in started:
                http('POST', base + '/api/save', {'pid': st['pid'], 'stage': 'done', 'fields': fields})
            code, page = http('GET', base + '/admin?key=smoke-key&study=pilot-asd')
            check(code == 200 and b'Showing study <b>pilot-asd</b>: 3 sessions' in page, 'researcher page filters by study')
            code, z = http('GET', base + '/admin/r.zip?key=smoke-key&study=pilot-asd')
            zf = zipfile.ZipFile(io.BytesIO(z))
            pc = list(csv.DictReader(io.StringIO(zf.read('pizza-data/participants.csv').decode('utf-8'))))
            check(len(pc) == 3 and {r['study'] for r in pc} == {'pilot-asd'} and {r['source'] for r in pc} == {'charity'},
                  'per-study data download holds only that study, with group and source')
            saved = json.load(open(os.path.join(data, 'participants', 'SMOKE001.json'), encoding='utf-8'))
            check(saved.get('group') == 'ASD' and 'pz_final' in saved, 'session file has the group and the pizza')
        finally:
            srv.terminate()
            srv.wait(timeout=10)

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
