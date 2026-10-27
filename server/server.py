#!/usr/bin/env python3
"""Pizza study server: run the pizza task for real participants without Qualtrics, e.g. from a GitHub Codespace.

    python3 server/server.py            # then share the participant link it prints
    python3 server/server.py --links    # print the links again (e.g. in a new terminal)

Participants open the link, read the intro, consent, and do practice -> build -> ratings. Everything they do is
saved as they go into the SQLite database data/study.db (store.py), which analysis/analyse.py reads directly. The
researcher page (/admin, password printed at start) filters and sorts sessions, builds the reports and exports the
data; each study has its own researcher link that sees that study only.

Participant links can carry:  ?pid=<id>  (e.g. a Prolific ID; otherwise a random one is made)
                              &group=<label>  (e.g. ASD / NT; analyse.py can compare groups by it)
                              &cond=<condition>  (otherwise conditions from study.json are assigned in turn)

Edit study.json (next to this file) for the title, intro text, consent sentence, completion message or redirect
(e.g. a Prolific completion URL), conditions, groups (a ready-made link per group on the researcher page), and whether
to add the "typical participant" build and the "About you" questions (about_you).
Standard library only.
"""
import argparse
import csv
import hashlib
import http.server
import io
import json
import os
import re
import secrets
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import zipfile
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from store import Store, SORTABLE, STAGES, ACTIVITY, ANALYSIS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                          # the repository root
PID_RE = re.compile(r'^[A-Za-z0-9_-]{4,64}$')
MAX_BODY = 2_000_000
LOCK = threading.Lock()
BUILD_LOCK = threading.Lock()


STUDY_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,39}$')
STUDY_KEYS = ('title', 'intro', 'consent', 'completion_message', 'completion_redirect', 'typical_build', 'about_you', 'conditions', 'groups',
              'nutrition_panel', 'nutrition_show', 'nutrition_base', 'nutrition_reveal', 'condition_settings')


def load_study(study_id=''):
    """study.json; with a study id, that study's settings ("studies": {id: {...}}) override the main ones."""
    try:
        with open(os.path.join(HERE, 'study.json'), encoding='utf-8') as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    if study_id:
        cfg = dict(cfg, **{k: v for k, v in (cfg.get('studies') or {}).get(study_id, {}).items() if k in STUDY_KEYS + ('description',)})
    return cfg


def studies():
    """{id: settings} of the studies in study.json (the main study, id '', is always there)."""
    return {k: v for k, v in (load_study().get('studies') or {}).items() if STUDY_RE.match(k)}


class Study:
    """The study server's state: the database (store.py), reports and the Methods page, under one data folder."""
    def __init__(self, data_dir, key):
        self.data = data_dir
        self.key = key
        os.makedirs(self.data, exist_ok=True)
        self.store = Store(os.path.join(self.data, 'study.db'))
        n = self.store.import_files(self.data)              # sessions saved as JSON files by earlier versions, once
        if n:
            print('  Imported %d earlier session%s into the database.' % (n, '' if n == 1 else 's'), flush=True)

    def resolve(self, invite, study):
        """(study id, invite record or None, error message or None) for a link's ?i= / ?study=."""
        if invite:
            inv = self.store.invite(invite)
            return (inv['study'], inv, None) if inv else ('', None, 'This personal link is not valid. Please check that you copied all of it.')
        if study and study not in studies():
            return '', None, 'This study link is not valid. Please check that you copied all of it.'
        return study or '', None, None

    def new_session(self, pid, group, cond, invite='', study='', source=''):
        """Start (or resume) a participant: assigns a condition in turn when the study lists any. A personal invite
        link is the participant's id, so opening it again (on any device) resumes the same session."""
        study, inv, err = self.resolve(invite, study)
        if err:
            return {'error': err}
        with LOCK:
            if inv:
                pid, group, source = invite, inv['grp'], inv['source']
            pid = pid if (pid and PID_RE.match(pid)) else 'P' + secrets.token_hex(4)
            rec = self.store.get(pid)
            if rec is not None and not inv and rec.get('study', '') != study:     # an id from another study: start afresh
                pid, rec = 'P' + secrets.token_hex(4), None
            if rec is None:
                conds = load_study(study).get('conditions') or []
                if not cond and conds:
                    cond = self.store.next_condition(study, conds)
                self.store.create(pid, study, group or '', source or '', invite if inv else '', cond or '')
                rec = self.store.get(pid)
            return rec

    def save(self, pid, fields, stage):
        return PID_RE.match(pid or '') is not None and self.store.save(pid, fields, stage)

    def methods_page(self):
        """The Methods page, rebuilt whenever the analysis code is newer than the last copy."""
        path = os.path.join(self.data, 'methods.html')
        src = [os.path.join(ROOT, 'analysis', f) for f in ('analyse.py', 'methods.py')]
        if not os.path.exists(path) or os.path.getmtime(path) < max(os.path.getmtime(f) for f in src):
            with BUILD_LOCK:
                r = subprocess.run([sys.executable, src[1], path], capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                return '<!doctype html><body><h1>Methods</h1><pre>%s</pre></body>' % escape((r.stderr or r.stdout)[-3000:])
        with open(path, encoding='utf-8') as f:
            return f.read()

    def reports_dir(self, f):
        """Reports are kept per filter: data/reports (everything), data/reports-<study>, or data/reports-<hash> for
        any other filter of the session list."""
        sig = filter_slug(f)
        return os.path.join(self.data, 'reports' + ('-' + sig if sig else ''))

    def build_reports(self, f, force=False):
        """Runs the analysis on the sessions matching the filter. Skipped when none of them changed since the last
        build. Returns (built: bool, message)."""
        out = self.reports_dir(f)
        sig = self.store.signature(f)
        if sig.startswith('0|'):
            return False, 'No sessions match.'
        stamp = os.path.join(out, '.built')
        try:
            with open(stamp, encoding='utf-8') as fh:
                old = fh.read().split('\n')[1]
        except (OSError, IndexError):
            old = None
        if not force and old == sig:
            return False, ''
        with BUILD_LOCK:
            tmp, src = out + '.new', out + '.in'
            for d in (tmp, src):
                shutil.rmtree(d, ignore_errors=True)
            os.makedirs(src)
            files = []
            for rec in self.store.records(f):                 # the matching sessions, as the analysis reads them
                path = os.path.join(src, rec['pid'] + '.json')
                with open(path, 'w', encoding='utf-8') as fh:
                    json.dump(rec, fh)
                files.append(path)
            try:
                r = subprocess.run([sys.executable, os.path.join(ROOT, 'analysis', 'analyse.py')] + files + ['--out', tmp],
                                   capture_output=True, text=True, timeout=1800)
            except subprocess.TimeoutExpired:
                return False, 'The analysis took longer than 30 minutes and was stopped.'
            finally:
                shutil.rmtree(src, ignore_errors=True)
            if r.returncode != 0 or not os.path.exists(os.path.join(tmp, 'participants.csv')):
                err = (r.stderr or r.stdout).strip()
                if 'No pizza fields found' in err:
                    return False, 'No finished pizzas yet among these sessions: reports need at least one participant who has built a pizza.'
                return False, 'The analysis failed:\n' + err[-1500:]
            shutil.rmtree(out, ignore_errors=True)
            os.replace(tmp, out)                          # swap in the new reports only when they are complete
            with open(stamp, 'w', encoding='utf-8') as fh:
                fh.write(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + '\n' + sig)
            return True, r.stdout.strip().split('\n')[-1]

    def reports_info(self, f):
        try:
            with open(os.path.join(self.reports_dir(f), '.built'), encoding='utf-8') as fh:
                when = fh.read().split('\n')[0]
        except OSError:
            return None
        n, check = 0, {}
        try:
            with open(os.path.join(self.reports_dir(f), 'participants.csv'), encoding='utf-8') as fh:
                n = max(0, sum(1 for _ in fh) - 1)
            with open(os.path.join(self.reports_dir(f), 'data_check.json'), encoding='utf-8') as fh:
                check = json.load(fh)
            n = check['own']
        except (OSError, ValueError, KeyError):
            pass
        return when, n, {k: check[k] for k in ('sessions', 'typical', 'left_out', 'built_sessions', 'ok') if k in check} or None


FILTER_KEYS = ('study', 'grp', 'source', 'stage', 'neuro', 'cond', 'q', 'since', 'until')


def filter_slug(f):
    """A short, stable name for a filter (for the reports folder): '' for none, the study for a study only."""
    used = {k: v for k, v in f.items() if v not in (None, '') or (k == 'study' and v == '')}
    if not used:
        return ''
    if list(used) == ['study']:
        return used['study'] or 'main'
    return hashlib.sha1(json.dumps(used, sort_keys=True).encode()).hexdigest()[:12]


R_FILES = ['participants.csv', 'ingredients_long.csv', 'pieces_long.csv', 'removals_long.csv', 'adjustments_long.csv', 'events_long.csv', 'profiles.csv', 'explore.csv',
           'excluded.csv', 'data_check.json', 'variables.csv', 'load_pizza.R', 'methods.html']
R_README = """Pizza study data, ready for R
=============================

In R (no packages needed):

    setwd("pizza-data")                  # this folder
    source("load_pizza.R")
    pz <- load_pizza(".")                # a list of data frames, read with the right types and factor levels
    people <- pizza_wide(pz)             # one row per participant: own pizza (+ typical pizza) + profile scores
    pizza_describe("mirror_score", pz)   # what a column means

Tables (UTF-8 CSV, missing values = NA, yes/no = 1/0, times in ms, positions in pizza radii):
    participants.csv      one row per finished pizza (pid + build: pz = own pizza, pzt = typical-participant pizza)
    ingredients_long.csv  one row per participant x build x topping on the tray
    pieces_long.csv       one row per piece on a finished pizza
    removals_long.csv     one row per piece taken off the pizza: which topping, how, when (changes of mind)
    adjustments_long.csv  one row per piece moved or resized after placing: what it did (symmetry, grouping, spacing, ...)
    events_long.csv       one row per logged action
    profiles.csv          one row per participant: standardised profile scores and cluster
    explore.csv           one row per group comparison shown in explore.html
    excluded.csv          pizzas left out of every table: unfinished ("I'm done" not pressed) or excluded by a researcher
                          on the Sessions tab (column reason); a researcher can also keep an unfinished one in
                          (participants.csv column inclusion = researcher)
    data_check.json       sessions, analysed and left-out pizzas, and whether they add up (also on the Overview page)
    variables.csv         every column of every table: type, factor levels, unit, description
    methods.html          how every number is counted (open in a browser)
    raw/                  each participant's session exactly as the study saved it (JSON)
"""
NEURO_NAMES = {'autistic': 'Autistic', 'adhd': 'ADHD', 'dys': 'Dyslexic etc.', 'otherND': 'Other ND', 'none': 'None', 'pnts': 'Prefer not to say'}


STAGE_NAMES = {'intro': 'reading the intro', 'practice': 'practice', 'build': 'building', 'typical': 'typical pizza', 'followup': 'questions', 'done': 'finished'}
PAGE = 100
ALL_KEY = '*'                                         # study_keys row of the researcher link for all studies
NOT_BUILT = ('<!doctype html><meta charset="utf-8"><body style="font:15px system-ui,sans-serif;color:#6e635b;max-width:640px;margin:48px auto;'
             'padding:0 16px"><p>%s</p></body>')


class Handler(http.server.BaseHTTPRequestHandler):
    study = None                                      # set in main()
    server_version = 'PizzaStudy/2'

    def log_message(self, fmt, *args):                # keep the terminal for the useful lines only; keys stay out of it
        if not self.path.startswith('/api/save'):
            sys.stderr.write('%s %s\n' % (time.strftime('%H:%M:%S'), re.sub(r'key=[^&\s"]+', 'key=…', fmt % args)))

    # ---- helpers
    def send(self, code, body, ctype='text/html; charset=utf-8', headers=None):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')   # researcher links carry their key
        self.send_header('X-Robots-Tag', 'noindex, nofollow')  # nothing here is for search engines
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def file(self, path, ctype):
        try:
            with open(path, 'rb') as f:
                self.send(200, f.read(), ctype)
        except OSError:
            self.send(404, 'Not found', 'text/plain')

    def query(self):
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

    def arg(self, k, default=''):
        return self.query().get(k, [default])[0]

    def scope(self):
        """Who is asking: ('owner', None) with the server's key; ('all', None) with the researcher link for all studies
        (sees every study, manages no links); ('study', id) with a study's researcher link; else None."""
        key = self.arg('key')
        if key and secrets.compare_digest(key, self.study.key):
            return ('owner', None)
        sid = self.study.store.study_for_key(key) if key else None
        if sid == ALL_KEY:
            return ('all', None)
        return ('study', sid) if sid is not None else None

    def filters(self, scope):
        """The session filter from the query; a study researcher always sees their own study only."""
        q = self.query()
        f = {k: q.get(k, [''])[0].strip()[:80] for k in FILTER_KEYS}
        if scope[0] == 'study':
            f['study'] = scope[1]
        elif f['study'] in ('', 'all') or not (f['study'] == 'main' or STUDY_RE.match(f['study'])):
            f['study'] = None
        else:
            f['study'] = '' if f['study'] == 'main' else f['study']
        if f['stage'] not in STAGES + ACTIVITY + ANALYSIS:
            f['stage'] = ''
        for k in ('since', 'until'):
            if not re.match(r'^\d{4}-\d\d-\d\d$', f[k]):
                f[k] = ''
        return f

    def qs(self, f, **extra):
        """Query string with the key and the filter (and any extra parameters)."""
        d = {'key': self.arg('key')}
        for k in FILTER_KEYS:
            v = f.get(k)
            if k == 'study':
                if v is not None and self.scope()[0] != 'study':
                    d['study'] = v or 'main'
            elif v:
                d[k] = v
        d.update({k: v for k, v in extra.items() if v not in (None, '')})
        return urllib.parse.urlencode(d)

    def denied_page(self):
        return ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Pizza Study Admin</title>'
                '<body style="font:16px system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px"><h1>Researcher page</h1>'
                '<p>This page needs a researcher link, which ends in <code>/admin?key=...</code>. The study owner finds theirs in the codespace '
                'terminal (or with <code>python3 server/server.py --links</code>) and can give each study\'s researchers a link for that study.</p></body>')

    def body_form(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n <= 0 or n > 10000:
            return {}
        return {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode('utf-8', 'replace')).items()}

    def body_json(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n <= 0 or n > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(n).decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return None

    def download(self, data, ctype, name):
        return self.send(200, data, ctype, {'Content-Disposition': 'attachment; filename="%s"' % name})

    def tag(self, f):
        slug = filter_slug(f)
        return ('-' + slug if slug else '') + '-' + time.strftime('%Y%m%d-%H%M')

    # ---- routes
    def do_GET(self):
        route = urllib.parse.urlparse(self.path).path
        if route in ('/', '/index.html'):
            return self.file(os.path.join(HERE, 'participate.html'), 'text/html; charset=utf-8')
        if route in ('/pizza-builder.js', '/preview.js'):
            return self.file(os.path.join(ROOT, route[1:]), 'application/javascript; charset=utf-8')
        if route == '/robots.txt':
            return self.send(200, 'User-agent: *\nDisallow: /\n', 'text/plain; charset=utf-8')
        if route == '/study.json':
            sid, _, _ = self.study.resolve(self.arg('i'), self.arg('study'))
            s = load_study(sid)
            return self.send(200, json.dumps({k: s.get(k) for k in STUDY_KEYS if k not in ('conditions', 'groups')}), 'application/json')
        if route == '/api/start':
            g = self.arg
            rec = self.study.new_session(g('pid') or g('PROLIFIC_PID'), g('group'), g('cond'), g('i'), g('study'), g('source'))
            if 'error' in rec:
                return self.send(200, json.dumps({'error': rec['error']}), 'application/json')
            return self.send(200, json.dumps({'pid': rec['pid'], 'cond': rec.get('cond', ''), 'stage': rec.get('stage', 'intro'),
                                              'counts': rec.get('pz_counts', ''), 'restarts': str(rec.get('restarts') or 0)}), 'application/json')
        if not route.startswith('/admin'):
            return self.send(404, 'Not found', 'text/plain')
        scope = self.scope()
        if scope is None:
            return self.send(403, self.denied_page())
        f = self.filters(scope)
        st = self.study.store
        if route == '/admin':                            # the researcher page: one app (admin.html), data from the two routes below
            return self.file(os.path.join(HERE, 'admin.html'), 'text/html; charset=utf-8')
        if route == '/admin/api/state':
            return self.send(200, json.dumps(self.state(scope, f)), 'application/json')
        if route == '/admin/api/sessions':
            try:
                page = max(1, int(self.arg('page', '1')))
            except ValueError:
                page = 1
            rows, total, done = st.query(f, self.arg('sort', 'started'), self.arg('dir', 'desc') != 'asc', PAGE, (page - 1) * PAGE)
            return self.send(200, json.dumps({'rows': rows, 'total': total, 'done': done, 'page': page, 'pages': max(1, -(-total // PAGE))}), 'application/json')
        if route == '/admin/sessions.csv':                 # the session list as shown (filtered, sorted), quick: no analysis
            rows, _, _ = st.query(f, self.arg('sort', 'started'), self.arg('dir', 'desc') != 'asc', limit=10 ** 9)
            buf = io.StringIO()
            w = csv.writer(buf)
            cols = ['pid', 'study', 'grp', 'source', 'invite', 'cond', 'stage', 'started', 'updated', 'finished', 'seconds', 'restarts', 'consent', 'n_pieces', 'neuro', 'analysis', 'inclusion']
            w.writerow(['group' if c == 'grp' else c for c in cols])
            for r in rows:
                w.writerow(['main' if c == 'study' and not r[c] else 'auto' if c == 'inclusion' and not r[c] else ('NA' if r[c] is None else r[c]) for c in cols])
            return self.download(buf.getvalue().encode('utf-8'), 'text/csv; charset=utf-8', 'sessions%s.csv' % self.tag(f))
        if route == '/admin/invites.csv':
            sid = f['study']
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(['invite', 'link', 'study', 'group', 'source', 'note', 'created', 'status', 'started', 'last_saved'])
            base = self.base_url() + '/?i='
            for inv in st.invites(sid):
                status = 'finished' if inv['stage'] == 'done' else 'started' if inv['stage'] else 'not opened'
                w.writerow([inv['token'], base + inv['token'], inv['study'] or 'main', inv['grp'], inv['source'], inv['note'], inv['created'], status,
                            inv['started'] or '', inv['updated'] or ''])
            return self.download(('\ufeff' + buf.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8', 'invite-links%s.csv' % self.tag({'study': sid}))
        if route == '/admin/r.zip':
            built, msg = self.study.build_reports(f)
            folder = self.study.reports_dir(f)
            if not os.path.exists(os.path.join(folder, 'variables.csv')):
                return self.back(f, msg or 'No finished pizzas among these sessions, so there is nothing to analyse.')
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                z.writestr('pizza-data/README.txt', R_README)
                for name in R_FILES:
                    if os.path.exists(os.path.join(folder, name)):
                        z.write(os.path.join(folder, name), 'pizza-data/' + name)
                for rec in st.records(f):
                    z.writestr('pizza-data/raw/%s.json' % rec['pid'], json.dumps(rec))
            return self.download(buf.getvalue(), 'application/zip', 'pizza-data-R%s.zip' % self.tag(f))
        if route == '/admin/data.zip':
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                for rec in st.records(f):
                    z.writestr('participants/%s.json' % rec['pid'], json.dumps(rec))
            return self.download(buf.getvalue(), 'application/zip', 'pizza-sessions%s.zip' % self.tag(f))
        if route == '/admin/database.sqlite':               # a consistent copy: everything (owner) or one study
            sid = f['study'] if scope[0] == 'study' or f['study'] is not None else None
            fd, tmp = tempfile.mkstemp(suffix='.sqlite')
            os.close(fd)
            try:
                st.backup(tmp, sid)
                with open(tmp, 'rb') as fh:
                    data = fh.read()
            finally:
                os.remove(tmp)
            return self.download(data, 'application/vnd.sqlite3', 'pizza-study%s.sqlite' % self.tag({'study': sid} if sid is not None else {}))
        if route == '/admin/methods':
            return self.send(200, self.study.methods_page())
        m = re.match(r'^/admin/reports/([A-Za-z0-9_.-]+)$', route)
        if m and not m.group(1).startswith('.'):
            built, msg = self.study.build_reports(f)       # brings the reports up to date with the newest matching sessions
            path = os.path.join(self.study.reports_dir(f), m.group(1))
            if not os.path.exists(path):
                return self.send(200, NOT_BUILT % escape(msg or 'There are no finished pizzas in this study yet, so there is nothing to report.'))
            if m.group(1).endswith('.html'):
                return self.file(path, 'text/html; charset=utf-8')
            return self.file(path, 'text/csv; charset=utf-8')
        return self.send(404, 'Not found', 'text/plain')

    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        if route == '/api/save':
            body = self.body_json()
            if not isinstance(body, dict) or not isinstance(body.get('fields'), dict):
                return self.send(400, '{"ok":false}', 'application/json')
            ok = self.study.save(body.get('pid'), body['fields'], body.get('stage'))
            return self.send(200 if ok else 404, json.dumps({'ok': ok}), 'application/json')
        if not route.startswith('/admin'):
            return self.send(404, 'Not found', 'text/plain')
        scope = self.scope()
        if scope is None:
            return self.send(403, self.denied_page())
        f = self.filters(scope)
        msg = ''
        if route == '/admin/api/inclusion':                 # the Sessions tab: analyse this session or not (the reports rebuild when opened)
            form = self.body_form()
            ok = self.study.store.set_inclusion(form.get('pid', ''), form.get('value', ''), scope[1] if scope[0] == 'study' else None)
            return self.send(200 if ok else 404, json.dumps({'ok': ok}), 'application/json')
        if route == '/admin/reports':
            built, msg = self.study.build_reports(f, force=True)
            msg = msg or 'Reports are up to date.'
        elif route == '/admin/invites':
            form = self.body_form()
            sid = '' if form.get('study', '') == 'main' else form.get('study', '')
            if scope[0] == 'study':
                sid = scope[1]                              # a study's researchers make links for their study only
            try:
                count = max(1, min(500, int(form.get('count') or 0)))
            except ValueError:
                count = 0
            if sid and sid not in studies():
                msg = 'Unknown study %s: add it to "studies" in server/study.json first.' % sid
            elif not count:
                msg = 'Say how many links to make (1-500).'
            else:
                self.study.store.create_invites(sid, form.get('group', '').strip(), form.get('source', '').strip(), form.get('note', '').strip(), count)
                msg = 'Made %d personal link%s for %s. Download them with "Personal links (.csv)".' % (count, '' if count == 1 else 's', sid or 'the main study')
        elif route == '/admin/study-key' and scope[0] == 'owner':
            sid = self.body_form().get('study', '')
            sid = ALL_KEY if sid == 'all' else '' if sid == 'main' else sid
            self.study.store.reset_study_key(sid)
            msg = 'Made a new researcher link for %s: the old one no longer works.' % ('all studies' if sid == ALL_KEY else sid or 'the main study')
        else:
            return self.send(404, 'Not found', 'text/plain')
        # redirect so that reloading the page does not repeat the action
        return self.back(f, msg)

    def back(self, f, msg):
        """Back to the researcher page (same study and tab) with a message."""
        tab = self.arg('tab') if re.match(r'^[a-z]{1,20}$', self.arg('tab')) else ''
        return self.send(303, '', headers={'Location': '/admin?' + self.qs(f, msg=msg) + ('#' + tab if tab else '')})

    def base_url(self):
        if os.environ.get('CODESPACE_NAME'):             # the codespace's public address, whatever the proxy sends
            return public_url(self.server.server_address[1])
        host = self.headers.get('X-Forwarded-Host') or self.headers.get('Host') or 'localhost'
        proto = self.headers.get('X-Forwarded-Proto') or ('https' if host.endswith('.app.github.dev') else 'http')
        return '%s://%s' % (proto, host)

    def state(self, scope, f):
        """Everything the researcher page shows apart from the session list: who is asking, the studies with their
        counts and links, the report status of the chosen study, and the filter choices."""
        st = self.study.store
        own = scope[0] == 'owner'
        ids = [scope[1]] if scope[0] == 'study' else [''] + sorted(studies())
        counts = st.counts_by_study()
        out = []
        for sid in ids:
            cfg = load_study(sid)
            invs = st.invites(sid)
            n, done, built, active = counts.get(sid, (0, 0, 0, 0))
            row = {'id': sid or 'main', 'title': cfg.get('title') or '', 'description': cfg.get('description') or ('The main study' if not sid else ''),
                   'n': n, 'done': done or 0, 'built': built, 'active': active, 'stopped': n - (done or 0) - active, 'last': st.last_started(sid), 'median_seconds': st.median_seconds(sid),
                   'invites': [len(invs), sum(1 for i in invs if i['stage']), sum(1 for i in invs if i['stage'] == 'done')],
                   'links': self.open_links(sid), 'nutrition_reveal': bool(cfg.get('nutrition_reveal')), 'nutrition_panel': bool(cfg.get('nutrition_panel'))}
            if own:
                row['researcher_link'] = self.base_url() + '/admin?' + urllib.parse.urlencode({'key': st.study_key(sid)})
            out.append(row)
        sel = None if f['study'] is None and not self.arg('study') else ('all' if f['study'] is None else f['study'] or 'main')
        info = self.study.reports_info({'study': f['study']}) if sel else None
        sig = st.signature({'study': f['study']})
        return {
            'server': 'python', 'scope': scope[0], 'scope_study': (scope[1] or 'main') if scope[0] == 'study' else None,
            'study': sel, 'studies': out, 'idle_minutes': 30,
            'all': {'n': sum(r['n'] for r in out), 'done': sum(r['done'] for r in out), 'built': sum(r['built'] for r in out),
                    'active': sum(r['active'] for r in out), 'stopped': sum(r['stopped'] for r in out),
                                                   'last': max([r['last'] for r in out if r['last']] or [None]),
                                                   'median_seconds': st.median_seconds(None)},
            'global_link': self.base_url() + '/admin?' + urllib.parse.urlencode({'key': st.study_key(ALL_KEY)}) if own else None,
            'reports': {'when': info[0], 'n': info[1], 'check': info[2], 'fresh': True} if info else None,
            'reports_build_on_open': True, 'signature': sig,
            'options': {c: st.distinct(c, f['study']) for c in ('grp', 'source', 'cond')},
            'stages': STAGE_NAMES, 'neuro': NEURO_NAMES, 'storage': None, 'msg': self.arg('msg'),
        }

    def open_links(self, sid):
        """(label, url) of the open links of a study: one for anyone, one per group listed for that study."""
        base = self.base_url() + '/'
        cfg = load_study(sid)
        q = {'study': sid} if sid else {}
        return [('Anyone', base + ('?' + urllib.parse.urlencode(q) if q else ''))] + \
               [('Group %s' % g, base + '?' + urllib.parse.urlencode(dict(q, group=g))) for g in cfg.get('groups') or []]


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def stored_key(data_dir):
    """The researcher password: made once, then kept in the data folder so the researcher link never changes."""
    path = os.path.join(data_dir, '.admin_key')
    try:
        with open(path, encoding='utf-8') as f:
            key = f.read().strip()
        if key:
            return key
    except OSError:
        pass
    os.makedirs(data_dir, exist_ok=True)
    key = secrets.token_urlsafe(9)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(key)
    os.chmod(path, 0o600)
    return key


def public_url(port):
    name, domain = os.environ.get('CODESPACE_NAME'), os.environ.get('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN')
    return 'https://%s-%d.%s' % (name, port, domain) if name and domain else 'http://localhost:%d' % port


def make_port_public(port):
    """In a Codespace, forwarded ports are private (only you can open them); participants need it public."""
    if not os.environ.get('CODESPACE_NAME'):
        return
    time.sleep(3)
    try:
        r = subprocess.run(['gh', 'codespace', 'ports', 'visibility', '%d:public' % port, '-c', os.environ['CODESPACE_NAME']],
                           capture_output=True, text=True, timeout=60)
        ok = r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    print('\n  Port %d is %s.\n' % (port, 'now public: participants can open the link' if ok else
          'still private. Make it public: Ports tab -> right-click port %d -> Port Visibility -> Public' % port), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8000)))
    ap.add_argument('--data', default=os.path.join(HERE, 'data'), help='where sessions are saved (default: server/data)')
    ap.add_argument('--key', default=os.environ.get('PIZZA_ADMIN_KEY'), help='researcher password (default: made once and kept in the data folder)')
    ap.add_argument('--links', action='store_true', help='print the participant and researcher links, then exit')
    a = ap.parse_args()
    if sys.version_info < (3, 10):
        sys.exit('The study server and analysis need Python 3.10 or newer (this is %d.%d).' % sys.version_info[:2])
    if a.links:
        url = public_url(a.port)
        print('\n  Participant link:  %s/\n  Researcher page:   %s/admin?key=%s\n' % (url, url, a.key or stored_key(a.data)))
        return
    key = a.key or stored_key(a.data)
    Handler.study = Study(a.data, key)
    srv = Server(('0.0.0.0', a.port), Handler)
    url = public_url(a.port)
    print('\n  Pizza study is running.\n'
          '  Participant link:  %s/            (add ?group=ASD or ?pid=... as needed)\n'
          '  Researcher page:   %s/admin?key=%s\n'
          '  Data folder:       %s\n'
          '  Stop with Ctrl-C. Sessions already saved stay in the data folder.\n' % (url, url, key, os.path.abspath(a.data)), flush=True)
    if os.environ.get('CODESPACE_NAME'):
        print('  The researcher page lists ready-to-send links. Print these again any time: python3 server/server.py --links\n', flush=True)
    threading.Thread(target=make_port_public, args=(a.port,), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
