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
from store import Store, SORTABLE, STAGES  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                          # the repository root
PID_RE = re.compile(r'^[A-Za-z0-9_-]{4,64}$')
MAX_BODY = 2_000_000
LOCK = threading.Lock()
BUILD_LOCK = threading.Lock()


STUDY_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,39}$')
STUDY_KEYS = ('title', 'intro', 'consent', 'completion_message', 'completion_redirect', 'typical_build', 'about_you', 'conditions', 'groups',
              'nutrition_panel', 'nutrition_show', 'nutrition_base', 'condition_settings')


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
        n = 0
        try:
            with open(os.path.join(self.reports_dir(f), 'participants.csv'), encoding='utf-8') as fh:
                n = max(0, sum(1 for _ in fh) - 1)
        except OSError:
            pass
        return when, n


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
           'variables.csv', 'load_pizza.R', 'methods.html']
R_README = """Pizza study data, ready for R
=============================

In R (no packages needed):

    setwd("pizza-data")                  # this folder
    source("load_pizza.R")
    pz <- load_pizza(".")                # a list of data frames, read with the right types and factor levels
    people <- pizza_wide(pz)             # one row per participant: own pizza (+ typical pizza) + profile scores
    pizza_describe("mirror_score", pz)   # what a column means

Tables (UTF-8 CSV, missing values = NA, yes/no = 1/0, times in ms, positions in pizza radii):
    participants.csv      one row per pizza (pid + build: pz = own pizza, pzt = typical-participant pizza)
    ingredients_long.csv  one row per participant x build x topping on the tray
    pieces_long.csv       one row per piece on a finished pizza
    removals_long.csv     one row per piece taken off the pizza: which topping, how, when (changes of mind)
    adjustments_long.csv  one row per piece moved or resized after placing: what it did (symmetry, grouping, spacing, ...)
    events_long.csv       one row per logged action
    profiles.csv          one row per participant: standardised profile scores and cluster
    explore.csv           one row per group comparison shown in explore.html
    variables.csv         every column of every table: type, factor levels, unit, description
    methods.html          how every number is counted (open in a browser)
    raw/                  each participant's session exactly as the study saved it (JSON)
"""
NEURO_NAMES = {'autistic': 'Autistic', 'adhd': 'ADHD', 'dys': 'Dyslexic etc.', 'otherND': 'Other ND', 'none': 'None', 'pnts': 'Prefer not to say'}


STAGE_NAMES = {'intro': 'reading the intro', 'practice': 'practice', 'build': 'building', 'typical': 'typical pizza', 'followup': 'questions', 'done': 'finished'}
COLUMNS = [('pid', 'Participant'), ('study', 'Study'), ('grp', 'Group'), ('source', 'Source'), ('neuro', 'Says they are'), ('cond', 'Condition'),
           ('stage', 'Where'), ('n_pieces', 'Pieces'), ('started', 'Started (UTC)'), ('seconds', 'Time taken'), ('restarts', 'Restarts')]
PAGE = 100


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
        """Who is asking: ('owner', None) with the server's key, ('study', id) with a study's researcher key, else None."""
        key = self.arg('key')
        if key and secrets.compare_digest(key, self.study.key):
            return ('owner', None)
        sid = self.study.store.study_for_key(key) if key else None
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
        if f['stage'] not in STAGES:
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
                if v is not None and self.scope()[0] == 'owner':
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
        if route == '/admin':
            return self.send(200, self.admin_page(scope, f, self.arg('msg')))
        if route == '/admin/sessions.csv':                 # the session list as shown (filtered, sorted), quick: no analysis
            rows, _, _ = st.query(f, self.arg('sort', 'started'), self.arg('dir', 'desc') != 'asc', limit=10 ** 9)
            buf = io.StringIO()
            w = csv.writer(buf)
            cols = ['pid', 'study', 'grp', 'source', 'invite', 'cond', 'stage', 'started', 'updated', 'finished', 'seconds', 'restarts', 'consent', 'n_pieces', 'neuro']
            w.writerow(['group' if c == 'grp' else c for c in cols])
            for r in rows:
                w.writerow(['main' if c == 'study' and not r[c] else ('NA' if r[c] is None else r[c]) for c in cols])
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
                return self.send(200, self.admin_page(scope, f, msg or 'No finished pizzas among these sessions, so there is nothing to analyse.'))
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
            return self.send(200, self.with_bar(self.study.methods_page(), f))
        m = re.match(r'^/admin/reports/([A-Za-z0-9_.-]+)$', route)
        if m and not m.group(1).startswith('.'):
            built, msg = self.study.build_reports(f)       # brings the reports up to date with the newest matching sessions
            path = os.path.join(self.study.reports_dir(f), m.group(1))
            if not os.path.exists(path):
                return self.send(200, self.admin_page(scope, f, msg or 'That report has not been made yet.'))
            if m.group(1).endswith('.html'):
                with open(path, encoding='utf-8') as fh:
                    return self.send(200, self.with_bar(fh.read(), f))
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
            sid = '' if sid == 'main' else sid
            self.study.store.reset_study_key(sid)
            msg = 'Made a new researcher link for %s: the old one no longer works.' % (sid or 'the main study')
        else:
            return self.send(404, 'Not found', 'text/plain')
        # redirect so that reloading the page does not repeat the action
        return self.send(303, '', headers={'Location': '/admin?' + self.qs(f, msg=msg)})

    def base_url(self):
        if os.environ.get('CODESPACE_NAME'):             # the codespace's public address, whatever the proxy sends
            return public_url(self.server.server_address[1])
        host = self.headers.get('X-Forwarded-Host') or self.headers.get('Host') or 'localhost'
        proto = self.headers.get('X-Forwarded-Proto') or ('https' if host.endswith('.app.github.dev') else 'http')
        return '%s://%s' % (proto, host)

    def open_links(self, sid):
        """(label, url) of the open links of a study: one for anyone, one per group listed for that study."""
        base = self.base_url() + '/'
        cfg = load_study(sid)
        q = {'study': sid} if sid else {}
        return [('Anyone', base + ('?' + urllib.parse.urlencode(q) if q else ''))] + \
               [('Group %s' % g, base + '?' + urllib.parse.urlencode(dict(q, group=g))) for g in cfg.get('groups') or []]

    def link_rows(self, items):
        return ''.join('<span class="ll">%s</span><input readonly value="%s" aria-label="%s"><button type="button" class="copy alt">Copy</button>'
                       % (escape(label), escape(url, quote=True), escape(label, quote=True)) for label, url in items)

    def studies_card(self, scope, f):
        st = self.study.store
        ids = [scope[1]] if scope[0] == 'study' else [''] + sorted(studies())
        counts = st.counts_by_study()
        trs, opts = [], []
        for sid in ids:
            cfg = load_study(sid)
            invs = st.invites(sid)
            opened = sum(1 for i in invs if i['stage'])
            fin = sum(1 for i in invs if i['stage'] == 'done')
            n, done = counts.get(sid, (0, 0))
            items = self.open_links(sid)
            if scope[0] == 'owner':                         # the researcher link that sees this study only
                items.append(('Researcher link (this study only)', self.base_url() + '/admin?' + urllib.parse.urlencode({'key': st.study_key(sid)})))
            reset = ('<form method="post" action="/admin/study-key?%s" onsubmit="return confirm(\'Make a new researcher link for this study? The old one will stop working.\')">'
                     '<input type="hidden" name="study" value="%s"><button class="alt small" type="submit">New researcher link</button></form>'
                     % (self.qs(f), escape(sid or 'main'))) if scope[0] == 'owner' else ''
            show = self.qs(dict(f, study=sid)) if scope[0] == 'owner' else self.qs(f)
            trs.append('<tr class="st"><td><b>%s</b><br><span class="muted">%s</span></td><td>%d</td><td>%d</td><td>%d / %d / %d</td>'
                       '<td><a href="/admin?%s">Show only this study</a><br><a href="/admin/invites.csv?%s">Personal links (.csv)</a>%s</td></tr>'
                       '<tr class="links"><td colspan="5"><div class="lgrid">%s</div></td></tr>'
                       % (escape(sid or 'main'), escape(cfg.get('description') or cfg.get('title') or ''), n, done or 0, len(invs), opened, fin,
                          show, self.qs({'study': sid}) if scope[0] == 'owner' else self.qs(f), reset, self.link_rows(items)))
            opts.append('<option value="%s"%s>%s</option>' % (escape(sid or 'main'), ' selected' if f['study'] == sid else '', escape(sid or 'main')))
        form = ('<form method="post" action="/admin/invites?%s" class="row" style="align-items:end">'
                '<label>Study<br><select name="study">%s</select></label>'
                '<label>Group<br><input name="group" size="8" placeholder="e.g. ASD"></label>'
                '<label>Recruitment source<br><input name="source" size="22" placeholder="e.g. autism charity newsletter"></label>'
                '<label>Note<br><input name="note" size="14" placeholder="optional"></label>'
                '<label>How many<br><input name="count" type="number" min="1" max="500" value="10" style="width:5em"></label>'
                '<button type="submit">Make personal links</button></form>' % (self.qs(f), ''.join(opts)))
        return ('<div class="card"><h2>%s</h2><table class="studies"><tr><th>Study</th><th>Sessions</th><th>Finished</th>'
                '<th>Personal links<br><span class="muted">made / opened / finished</span></th><th></th></tr>%s</table>'
                '<h2 style="margin-top:14px">Make personal links</h2>%s<p class="muted">One link per participant: it records study, group '
                'and source, and resumes their session if opened again. The .csv lists the links and who has opened or finished. Open links '
                '(above) can be posted anywhere.%s</p></div>'
                % ('Studies and links' if scope[0] == 'owner' else 'Links', ''.join(trs), form,
                   ' Studies are set up in <code>server/study.json</code> → <code>"studies"</code>; give each study\'s researchers its own '
                   'researcher link: it sees, analyses and exports that study only.' if scope[0] == 'owner' else ''))

    def with_bar(self, html, f):
        bar = ('<div style="position:sticky;top:0;z-index:50;background:#2a2421;color:#fff;font:14px system-ui,sans-serif;padding:8px 16px">'
               '<a href="/admin?%s" style="color:#fff">&larr; Researcher page</a>%s</div>' % (self.qs(f), escape(self.describe(f)) and ' · ' + escape(self.describe(f))))
        return re.sub(r'(<body[^>]*>)', lambda mm: mm.group(1) + bar, html, count=1)

    @staticmethod
    def describe(f):
        parts = []
        if f.get('study') is not None:
            parts.append('study %s' % (f['study'] or 'main'))
        names = {'grp': 'group', 'source': 'source', 'stage': 'where', 'neuro': 'says they are', 'cond': 'condition', 'q': 'id contains', 'since': 'from', 'until': 'to'}
        parts += ['%s %s' % (names[k], STAGE_NAMES.get(f[k], f[k]) if k == 'stage' else f[k]) for k in names if f.get(k)]
        return ', '.join(parts)

    def filter_form(self, scope, f, sort, desc):
        st = self.study.store
        def sel(name, label, values, cur, names=None):
            opts = '<option value="">any</option>' + ''.join('<option value="%s"%s>%s</option>' % (escape(v, quote=True), ' selected' if v == cur else '',
                                                                                                     escape((names or {}).get(v, v))) for v in values)
            return '<label>%s<br><select name="%s">%s</select></label>' % (label, name, opts)
        study_sel = ''
        if scope[0] == 'owner':
            cur = 'all' if f['study'] is None else (f['study'] or 'main')
            vals = [('all', 'all studies'), ('main', 'main')] + [(s_, s_) for s_ in sorted(set(studies()) | set(x for x in st.distinct('study') if x))]
            study_sel = '<label>Study<br><select name="study">%s</select></label>' % ''.join(
                '<option value="%s"%s>%s</option>' % (escape(v), ' selected' if v == cur else '', escape(l)) for v, l in vals)
        scope_study = f['study'] if scope[0] == 'study' else None
        return ('<form method="get" action="/admin" class="filters"><input type="hidden" name="key" value="%s">'
                '<input type="hidden" name="sort" value="%s"><input type="hidden" name="dir" value="%s">%s%s%s%s%s%s'
                '<label>Started from<br><input type="date" name="since" value="%s"></label><label>to<br><input type="date" name="until" value="%s"></label>'
                '<label>Participant id<br><input name="q" size="10" value="%s"></label>'
                '<button type="submit">Show</button><a class="btn alt" href="/admin?%s">Clear</a></form>'
                % (escape(self.arg('key'), quote=True), escape(sort), 'desc' if desc else 'asc', study_sel,
                   sel('grp', 'Group', st.distinct('grp', scope_study), f['grp']), sel('source', 'Source', st.distinct('source', scope_study), f['source']),
                   sel('stage', 'Where', list(STAGES), f['stage'], STAGE_NAMES), sel('neuro', 'Says they are', list(NEURO_NAMES), f['neuro'], NEURO_NAMES),
                   sel('cond', 'Condition', st.distinct('cond', scope_study), f['cond']),
                   escape(f['since'], quote=True), escape(f['until'], quote=True), escape(f['q'], quote=True), self.qs({'study': f['study']} if scope[0] == 'study' else {})))

    def admin_page(self, scope, f, message=''):
        st = self.study.store
        sort = self.arg('sort', 'started')
        sort = sort if sort in SORTABLE else 'started'
        desc = self.arg('dir', 'desc') != 'asc'
        try:
            page = max(1, int(self.arg('page', '1')))
        except ValueError:
            page = 1
        rows, total, done = st.query(f, sort, desc, PAGE, (page - 1) * PAGE)
        q = self.qs(f)
        info = self.study.reports_info(f)
        reports = [('dashboard.html', 'Dashboard'), ('explore.html', 'Explore patterns'), ('profiles.html', 'Profiles and clusters'), ('arrangement.html', 'Symmetry and contact')]
        tables = ['participants.csv', 'ingredients_long.csv', 'pieces_long.csv', 'removals_long.csv', 'adjustments_long.csv', 'profiles.csv', 'explore.csv', 'events_long.csv']
        status = ('Last built %s UTC from %d pizza%s. Opening a report brings it up to date with any newer sessions.' % (
            escape(info[0].replace('T', ' ')[:16]), info[1], '' if info[1] == 1 else 's')) if info else 'Not built yet for these sessions. Opening a report builds it.'
        report_btns = ''.join('<a class="btn" href="/admin/reports/%s?%s">%s</a>' % (fn, q, label) for fn, label in reports) + \
            '<a class="btn alt" href="/admin/methods?%s">Methods: how each number is counted</a>' % q
        table_links = ' · '.join('<a href="/admin/reports/%s?%s">%s</a>' % (t, q, t) for t in tables)
        def th(col, label):
            arrow = (' ▼' if desc else ' ▲') if col == sort else ''
            return '<th><a class="sort" href="/admin?%s">%s%s</a></th>' % (self.qs(f, sort=col, dir='asc' if col == sort and desc else 'desc'), label, arrow)
        def cell(r, c):
            v = r[c]
            if c == 'study':
                return escape(v or 'main')
            if c == 'stage':
                return escape(STAGE_NAMES.get(v, v))
            if c == 'neuro':
                return escape(', '.join(NEURO_NAMES.get(x, x) for x in (v or '').split()))
            if c == 'started':
                return escape((v or '').replace('T', ' ')[:16])
            if c == 'seconds':
                return '' if v is None else '%.1f min' % (v / 60)
            return '' if v in (None, '') else escape(str(v))
        trs = ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % cell(r, c) for c, _ in COLUMNS) for r in rows)
        pages = max(1, (total + PAGE - 1) // PAGE)
        pager = ''
        if pages > 1:
            pager = '<div class="row">%s<span class="muted">page %d of %d</span>%s</div>' % (
                '<a class="btn alt" href="/admin?%s">&larr; newer</a>' % self.qs(f, sort=sort, dir='desc' if desc else 'asc', page=page - 1) if page > 1 else '',
                page, pages, '<a class="btn alt" href="/admin?%s">older &rarr;</a>' % self.qs(f, sort=sort, dir='desc' if desc else 'asc', page=page + 1) if page < pages else '')
        exports = ('<div class="row"><a class="btn" href="/admin/r.zip?%s">Download for R (.zip)</a>'
                   '<a class="btn alt" href="/admin/sessions.csv?%s">Session list (.csv)</a>'
                   '<a class="btn alt" href="/admin/data.zip?%s">Raw sessions (.zip)</a>'
                   '<a class="btn alt" href="/admin/database.sqlite?%s">Database (.sqlite)</a></div>'
                   % (q, self.qs(f, sort=sort, dir='desc' if desc else 'asc'), q, q))
        note = ('<pre class="note">%s</pre>' % escape(message)) if message else ''
        who = 'Owner: all studies' if scope[0] == 'owner' else 'Researcher page for study <b>%s</b>' % escape(scope[1] or 'main')
        flt = self.describe(f)
        return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pizza Study Admin</title><style>
:root{--bg:#f6f2ed;--fg:#2a2421;--muted:#6e635b;--line:#dcd2c7;--panel:#fff;--accent:#a8361d;--accent-ink:#fff}
@media (prefers-color-scheme: dark){:root{--bg:#1d1916;--fg:#eee6de;--muted:#b0a398;--line:#3a322c;--panel:#26211d;--accent:#e0765b;--accent-ink:#1d1916;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px}h1{font-size:1.4rem;margin:0 0 4px}.muted{color:var(--muted)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:12px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%%;font-size:.9rem}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:top}
th a.sort{color:var(--fg);text-decoration:none}th a.sort:hover{text-decoration:underline}
h2{font-size:1.05rem;margin:0 0 8px}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}label{font-size:.85rem;color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;gap:8px 10px;align-items:end}
input,select{font:inherit;padding:6px 8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg)}
button,.btn{font:inherit;padding:8px 14px;border-radius:9px;border:1px solid var(--accent);background:var(--accent);color:var(--accent-ink);cursor:pointer;text-decoration:none;display:inline-block}
.btn.alt,button.alt{background:transparent;color:var(--fg);border-color:var(--line)}a{color:var(--accent)}button.small{padding:3px 10px;font-size:.85rem;margin-top:4px}
.studies tr.st td{border-bottom:0;padding-bottom:2px}.studies tr.links td{padding-top:2px}
.lgrid{display:grid;grid-template-columns:max-content minmax(0,1fr) max-content;gap:4px 8px;align-items:center;max-width:900px}
.lgrid .ll{color:var(--muted);font-size:.85rem}.lgrid input{width:100%%;box-sizing:border-box;font-size:.85rem;padding:5px 8px}.lgrid button{padding:4px 12px}
.note{white-space:pre-wrap;font:13px/1.4 ui-monospace,Menlo,Consolas,monospace;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:8px 0 0}
</style></head><body><div class="wrap"><h1>Pizza study</h1><p class="muted">%s</p>%s
<div class="card"><h2>Sessions</h2>%s
<p style="margin:10px 0 4px"><b>%d session%s match</b>, %d finished%s.</p>%s
<table><tr>%s</tr>%s</table>%s</div>
<div class="card"><h2>Reports for these sessions</h2><div class="row">%s</div><p class="muted" style="margin:4px 0">Tables: %s</p>
<p class="muted" style="margin:4px 0">%s</p>
<form method="post" action="/admin/reports?%s" style="margin:0"><button class="alt" type="submit">Rebuild now</button></form></div>
%s
</div><script>
document.querySelectorAll('.copy').forEach(function (b) {
  b.onclick = function () {
    var i = b.previousElementSibling; i.select();
    function ok() { b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1500); }
    if (navigator.clipboard) navigator.clipboard.writeText(i.value).then(ok, function () { document.execCommand('copy'); ok(); }); else { document.execCommand('copy'); ok(); }
  };
});
</script></body></html>""" % (who, note, self.filter_form(scope, f, sort, desc), total, '' if total == 1 else 's', done, (' (%s)' % escape(flt)) if flt else '',
                               exports, ''.join(th(c, l) for c, l in COLUMNS), trs or '<tr><td colspan="%d" class="muted">No sessions match.</td></tr>' % len(COLUMNS),
                               pager, report_btns, table_links, status, q, self.studies_card(scope, f))


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
