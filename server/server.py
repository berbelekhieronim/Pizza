#!/usr/bin/env python3
"""Pizza study server: run the pizza task for real participants without Qualtrics, e.g. from a GitHub Codespace.

    python3 server/server.py            # then share the participant link it prints
    python3 server/server.py --links    # print the links again (e.g. in a new terminal)

Participants open the link, read the intro, consent, and do practice -> build -> ratings. Everything they do is
saved as they go into data/<participant>.json (the same format the demo downloads), so analysis/analyse.py reads it
directly. The researcher page (/admin, password printed at start) lists sessions, builds the reports and downloads
all data as a zip.

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
import threading
import time
import urllib.parse
import zipfile
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                          # the repository root
PID_RE = re.compile(r'^[A-Za-z0-9_-]{4,64}$')
MAX_BODY = 2_000_000
LOCK = threading.Lock()
BUILD_LOCK = threading.Lock()


STUDY_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,39}$')
STUDY_KEYS = ('title', 'intro', 'consent', 'completion_message', 'completion_redirect', 'typical_build', 'about_you', 'conditions', 'groups')
INVITE_CHARS = 'abcdefghjkmnpqrstuvwxyz23456789'     # no 0/o, 1/l/i: easy to read out or type


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


def write_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f)
    os.replace(tmp, path)                             # atomic: a crash never leaves half a file


def read_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class Study:
    def __init__(self, data_dir, key):
        self.data = data_dir
        self.key = key
        os.makedirs(os.path.join(self.data, 'participants'), exist_ok=True)

    def path(self, pid):
        return os.path.join(self.data, 'participants', pid + '.json')

    # ---- invite links: one personal link per participant, tied to a study, group and recruitment source
    def invites(self):
        return read_json(os.path.join(self.data, 'invites.json'), {})

    def create_invites(self, study, group, source, note, count):
        with LOCK:
            inv = self.invites()
            made = []
            for _ in range(count):
                tok = ''.join(secrets.choice(INVITE_CHARS) for _ in range(8))
                while tok in inv or os.path.exists(self.path(tok)):
                    tok = ''.join(secrets.choice(INVITE_CHARS) for _ in range(8))
                inv[tok] = {'study': study, 'group': group[:60], 'source': source[:80], 'note': note[:200],
                            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
                made.append(tok)
            write_json(os.path.join(self.data, 'invites.json'), inv)
        return made

    def resolve(self, invite, study):
        """(study id, invite record or None, error message or None) for a link's ?i= / ?study=."""
        if invite:
            inv = self.invites().get(invite)
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
        cfg = load_study(study)
        with LOCK:
            if inv:
                pid, group, source = invite, inv['group'], inv['source']
            pid = pid if (pid and PID_RE.match(pid)) else 'P' + secrets.token_hex(4)
            rec = read_json(self.path(pid), None)
            if rec is not None and not inv and rec.get('study', '') != study:     # an id from another study: start afresh
                pid = 'P' + secrets.token_hex(4)
                rec = None
            if rec is None:
                conds = cfg.get('conditions') or []
                if not cond and conds:
                    state = read_json(os.path.join(self.data, '_state.json'), {})
                    nxt = state.get(study or 'next', 0)
                    cond = conds[nxt % len(conds)]
                    state[study or 'next'] = nxt + 1
                    write_json(os.path.join(self.data, '_state.json'), state)
                rec = {'pid': pid, 'study': study, 'group': (group or '')[:60], 'source': (source or '')[:80], 'invite': invite if inv else '',
                       'cond': (cond or '')[:60], 'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
                write_json(self.path(pid), rec)
            return rec

    def save(self, pid, fields, stage):
        if not PID_RE.match(pid or ''):
            return False
        with LOCK:
            rec = read_json(self.path(pid), None)
            if rec is None:
                return False
            for k, v in fields.items():
                if isinstance(k, str) and re.match(r'^[a-z_]{2,40}$', k) and isinstance(v, str):
                    rec[k] = v
            rec['stage'] = stage if isinstance(stage, str) else rec.get('stage')
            rec['updated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            write_json(self.path(pid), rec)
        return True

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

    def session_files(self, study=None):
        """Session files, all of them (study None) or one study's ('' = the main study)."""
        folder = os.path.join(self.data, 'participants')
        files = [os.path.join(folder, n) for n in sorted(os.listdir(folder)) if n.endswith('.json')]
        return files if study is None else [f for f in files if read_json(f, {}).get('study', '') == study]

    def reports_dir(self, study=None):
        return os.path.join(self.data, 'reports' if study is None else 'reports-' + (study or 'main'))

    def build_reports(self, force=False, study=None):
        """Runs the analysis on every session (or one study's) into data/reports(-<study>). Skipped when nothing
        changed since the last build. Returns (built: bool, message)."""
        out = self.reports_dir(study)
        files = self.session_files(study)
        if not files:
            return False, 'No sessions yet.'
        stamp = os.path.join(out, '.built')
        newest = max(os.path.getmtime(f) for f in files)
        if not force and os.path.exists(stamp) and os.path.getmtime(stamp) >= newest:
            return False, ''
        with BUILD_LOCK:
            tmp = out + '.new'
            shutil.rmtree(tmp, ignore_errors=True)
            try:
                r = subprocess.run([sys.executable, os.path.join(ROOT, 'analysis', 'analyse.py')] + files + ['--out', tmp],
                                   capture_output=True, text=True, timeout=900)
            except subprocess.TimeoutExpired:
                return False, 'The analysis took longer than 15 minutes and was stopped.'
            if r.returncode != 0 or not os.path.exists(os.path.join(tmp, 'participants.csv')):
                err = (r.stderr or r.stdout).strip()
                if 'No pizza fields found' in err:
                    return False, 'No finished pizzas yet: reports need at least one participant who has built a pizza.'
                return False, 'The analysis failed:\n' + err[-1500:]
            shutil.rmtree(out, ignore_errors=True)
            os.replace(tmp, out)                          # swap in the new reports only when they are complete
            with open(stamp, 'w') as f:
                f.write(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
            return True, r.stdout.strip().split('\n')[-1]

    def reports_info(self, study=None):
        stamp = os.path.join(self.reports_dir(study), '.built')
        try:
            with open(stamp) as f:
                when = f.read().strip()
        except OSError:
            return None
        n = 0
        try:
            with open(os.path.join(self.reports_dir(study), 'participants.csv'), encoding='utf-8') as f:
                n = max(0, sum(1 for _ in f) - 1)
        except OSError:
            pass
        return when, n

    def sessions(self):
        out = []
        folder = os.path.join(self.data, 'participants')
        for name in sorted(os.listdir(folder)):
            if name.endswith('.json'):
                r = read_json(os.path.join(folder, name), {})
                summ = {}
                try:
                    summ = json.loads(r.get('pz_summary') or '{}')
                except ValueError:
                    pass
                try:
                    pieces = len(json.loads(r['pz_final'])) if r.get('pz_final') else None
                except ValueError:
                    pieces = summ.get('nPieces')
                try:
                    neuro = ((json.loads(r.get('pzf_data') or '{}').get('about') or {}).get('neuro')) or []
                except (ValueError, AttributeError):
                    neuro = []
                out.append({'pid': r.get('pid', name[:-5]), 'group': r.get('group', ''), 'cond': r.get('cond', ''),
                            'study': r.get('study', ''), 'source': r.get('source', ''), 'invite': r.get('invite', ''),
                            'started': r.get('started', ''), 'updated': r.get('updated', ''), 'stage': r.get('stage', 'intro'),
                            'pieces': pieces, 'done': r.get('stage') == 'done', 'about': ', '.join(NEURO_NAMES.get(v, v) for v in neuro)})
        return out


R_FILES = ['participants.csv', 'ingredients_long.csv', 'pieces_long.csv', 'removals_long.csv', 'events_long.csv', 'profiles.csv', 'explore.csv',
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
    events_long.csv       one row per logged action
    profiles.csv          one row per participant: standardised profile scores and cluster
    explore.csv           one row per group comparison shown in explore.html
    variables.csv         every column of every table: type, factor levels, unit, description
    methods.html          how every number is counted (open in a browser)
    raw/                  each participant's session exactly as the study saved it (JSON)
"""
NEURO_NAMES = {'autistic': 'Autistic', 'adhd': 'ADHD', 'dys': 'Dyslexic etc.', 'otherND': 'Other ND', 'none': 'None', 'pnts': 'Prefer not to say'}


class Handler(http.server.BaseHTTPRequestHandler):
    study = None                                      # set in main()
    server_version = 'PizzaStudy/1'

    def log_message(self, fmt, *args):                # keep the terminal for the useful lines only
        if not self.path.startswith('/api/save'):
            sys.stderr.write('%s %s\n' % (time.strftime('%H:%M:%S'), fmt % args))

    # ---- helpers
    def send(self, code, body, ctype='text/html; charset=utf-8', headers=None):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
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

    def is_admin(self):
        return secrets.compare_digest(self.query().get('key', [''])[0], self.study.key)

    def denied_page(self):
        return ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Pizza Study Admin</title>'
                '<body style="font:16px system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px"><h1>Researcher page</h1>'
                '<p>This page needs the researcher link, which ends in <code>/admin?key=...</code>. Find it in the codespace terminal, '
                'or print it with <code>python3 server/server.py --links</code>.</p></body>')

    def study_filter(self):
        """?study= on admin pages: None = every study, '' = the main study ('main'), else a study id."""
        v = self.query().get('study', [None])[0]
        return None if v in (None, '', 'all') else '' if v == 'main' else v if STUDY_RE.match(v) else None

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

    # ---- routes
    def do_GET(self):
        route = urllib.parse.urlparse(self.path).path
        if route in ('/', '/index.html'):
            return self.file(os.path.join(HERE, 'participate.html'), 'text/html; charset=utf-8')
        if route in ('/pizza-builder.js', '/preview.js'):
            return self.file(os.path.join(ROOT, route[1:]), 'application/javascript; charset=utf-8')
        if route == '/study.json':
            q = self.query()
            sid, _, _ = self.study.resolve(q.get('i', [''])[0], q.get('study', [''])[0])
            s = load_study(sid)
            return self.send(200, json.dumps({k: s.get(k) for k in ('title', 'intro', 'consent', 'completion_message', 'completion_redirect', 'typical_build', 'about_you')}), 'application/json')
        if route == '/api/start':
            q = self.query()
            g = lambda k: q.get(k, [''])[0]
            rec = self.study.new_session(g('pid') or g('PROLIFIC_PID'), g('group'), g('cond'), g('i'), g('study'), g('source'))
            if 'error' in rec:
                return self.send(200, json.dumps({'error': rec['error']}), 'application/json')
            return self.send(200, json.dumps({'pid': rec['pid'], 'cond': rec.get('cond', ''), 'stage': rec.get('stage', 'intro')}), 'application/json')
        if route.startswith('/admin'):
            if not self.is_admin():
                return self.send(403, self.denied_page())
            sf = self.study_filter()
            tag = '' if sf is None else '-' + (sf or 'main')
            if route == '/admin':
                q = self.query()
                return self.send(200, self.admin_page(q.get('msg', [''])[0], sf))
            if route == '/admin/invites.csv':
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(['invite', 'link', 'study', 'group', 'source', 'note', 'created', 'status', 'started', 'last_saved'])
                base = self.base_url() + '/?i='
                for tok, inv in sorted(self.study.invites().items(), key=lambda kv: kv[1]['created']):
                    if sf is not None and inv['study'] != sf:
                        continue
                    rec = read_json(self.study.path(tok), {})
                    status = 'finished' if rec.get('stage') == 'done' else 'started' if rec else 'not opened'
                    w.writerow([tok, base + tok, inv['study'] or 'main', inv['group'], inv['source'], inv['note'], inv['created'], status,
                                rec.get('started', ''), rec.get('updated', '')])
                return self.send(200, '\ufeff' + buf.getvalue(), 'text/csv; charset=utf-8',
                                 {'Content-Disposition': 'attachment; filename="invite-links%s.csv"' % tag})
            if route == '/admin/r.zip':
                built, msg = self.study.build_reports(study=sf)
                folder = self.study.reports_dir(sf)
                if not os.path.exists(os.path.join(folder, 'variables.csv')):
                    return self.send(200, self.admin_page(msg or 'No finished pizzas yet, so there is nothing to analyse.'))
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                    z.writestr('pizza-data/README.txt', R_README)
                    for name in R_FILES:
                        if os.path.exists(os.path.join(folder, name)):
                            z.write(os.path.join(folder, name), 'pizza-data/' + name)
                    for path in self.study.session_files(sf):
                        z.write(path, 'pizza-data/raw/' + os.path.basename(path))
                return self.send(200, buf.getvalue(), 'application/zip', {'Content-Disposition': 'attachment; filename="pizza-data-R%s-%s.zip"' % (tag, time.strftime('%Y%m%d-%H%M'))})
            if route == '/admin/data.zip':
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                    for path in self.study.session_files(sf):
                        z.write(path, 'participants/' + os.path.basename(path))
                return self.send(200, buf.getvalue(), 'application/zip', {'Content-Disposition': 'attachment; filename="pizza-data%s-%s.zip"' % (tag, time.strftime('%Y%m%d-%H%M'))})
            if route == '/admin/methods':
                return self.send(200, self.with_bar(self.study.methods_page()))
            m = re.match(r'^/admin/reports/([A-Za-z0-9_.-]+)$', route)
            if m and not m.group(1).startswith('.'):
                built, msg = self.study.build_reports(study=sf)  # brings the reports up to date with the newest sessions
                path = os.path.join(self.study.reports_dir(sf), m.group(1))
                if not os.path.exists(path):
                    return self.send(200, self.admin_page(msg or 'That report has not been made yet.', sf))
                if m.group(1).endswith('.html'):
                    with open(path, encoding='utf-8') as f:
                        html = f.read()
                    return self.send(200, self.with_bar(html, sf))
                return self.file(path, 'text/csv; charset=utf-8')
                self.send(404, 'Not found', 'text/plain')

    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        if route == '/api/save':
            body = self.body_json()
            if not isinstance(body, dict) or not isinstance(body.get('fields'), dict):
                return self.send(400, '{"ok":false}', 'application/json')
            ok = self.study.save(body.get('pid'), body['fields'], body.get('stage'))
            return self.send(200 if ok else 404, json.dumps({'ok': ok}), 'application/json')
        if route in ('/admin/reports', '/admin/invites'):
            if not self.is_admin():
                return self.send(403, self.denied_page())
            sf = self.study_filter()
            if route == '/admin/reports':
                built, msg = self.study.build_reports(force=True, study=sf)
            else:
                form = self.body_form()
                sid = form.get('study', '')
                sid = '' if sid == 'main' else sid
                try:
                    count = max(1, min(500, int(form.get('count') or 0)))
                except ValueError:
                    count = 0
                if sid and sid not in studies():
                    msg = 'Unknown study %s: add it to "studies" in server/study.json first.' % sid
                elif not count:
                    msg = 'Say how many links to make (1-500).'
                else:
                    self.study.create_invites(sid, form.get('group', '').strip(), form.get('source', '').strip(), form.get('note', '').strip(), count)
                    msg = 'Made %d personal link%s for %s. Download them with "Invite links (.csv)".' % (count, '' if count == 1 else 's', sid or 'the main study')
                    sf = sid
            # redirect so that reloading the page does not repeat the action
            q = {'key': self.study.key, 'msg': msg or 'Reports are up to date.'}
            if sf is not None:
                q['study'] = sf or 'main'
            return self.send(303, '', headers={'Location': '/admin?' + urllib.parse.urlencode(q)})
        self.send(404, 'Not found', 'text/plain')

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

    def studies_card(self, rows, sf, k):
        inv = self.study.invites()
        ids = [''] + sorted(studies())
        trs, opts = [], []
        for sid in ids:
            cfg = load_study(sid)
            mine = [r for r in rows if r['study'] == sid]
            invs = [t for t, v in inv.items() if v['study'] == sid]
            opened = sum(1 for t in invs if os.path.exists(self.study.path(t)))
            fin = sum(1 for r in mine if r['invite'] and r['done'])
            links = ''.join('<div class="link"><span>%s</span><input readonly value="%s" aria-label="%s"><button type="button" class="copy">Copy</button></div>'
                            % (escape(label), escape(url, quote=True), escape(label, quote=True)) for label, url in self.open_links(sid))
            qs = 'key=%s&study=%s' % (k, urllib.parse.quote(sid or 'main'))
            trs.append('<tr><td><b>%s</b><br><span class="muted">%s</span></td><td>%d</td><td>%d</td><td>%d / %d / %d</td>'
                       '<td style="white-space:normal;min-width:320px">%s</td><td><a href="/admin?%s">Show</a><br><a href="/admin/invites.csv?%s">Invite links (.csv)</a></td></tr>'
                       % (escape(sid or 'main'), escape(cfg.get('description') or cfg.get('title') or ''), len(mine), sum(r['done'] for r in mine),
                          len(invs), opened, fin, links, qs, qs))
            opts.append('<option value="%s"%s>%s</option>' % (escape(sid or 'main'), ' selected' if sf == sid else '', escape(sid or 'main')))
        form = ('<form method="post" action="/admin/invites?key=%s" class="row" style="align-items:end">'
                '<label>Study<br><select name="study">%s</select></label>'
                '<label>Group<br><input name="group" size="8" placeholder="e.g. ASD"></label>'
                '<label>Recruitment source<br><input name="source" size="22" placeholder="e.g. autism charity newsletter"></label>'
                '<label>Note<br><input name="note" size="14" placeholder="optional"></label>'
                '<label>How many<br><input name="count" type="number" min="1" max="500" value="10" style="width:5em"></label>'
                '<button type="submit">Make personal links</button></form>' % (k, ''.join(opts)))
        return ('<div class="card"><h2>Studies and links</h2><table><tr><th>Study</th><th>Sessions</th><th>Finished</th>'
                '<th>Personal links<br><span class="muted">made / opened / finished</span></th><th>Open links</th><th></th></tr>%s</table>'
                '<h2 style="margin-top:14px">Make personal links</h2>%s<p class="muted">A personal link (<code>/?i=…</code>) belongs to one '
                'participant: it records the study, group and recruitment source, and opening it again resumes their session. Download the '
                'links as a spreadsheet to send them out, and to see who has opened or finished. Open links can be posted anywhere; '
                'anyone using one is recorded under that study (and group). Add studies, each with its own intro, consent and completion '
                'text if you like, under <code>"studies"</code> in <code>server/study.json</code>.</p></div>' % (''.join(trs), form))

    def with_bar(self, html, sf=None):
        q = urllib.parse.urlencode(dict({'key': self.study.key}, **({} if sf is None else {'study': sf or 'main'})))
        bar = ('<div style="position:sticky;top:0;z-index:50;background:#2a2421;color:#fff;font:14px system-ui,sans-serif;padding:8px 16px">'
               '<a href="/admin?%s" style="color:#fff">&larr; Researcher page</a>%s</div>' % (q, '' if sf is None else ' · study: <b>%s</b>' % escape(sf or 'main')))
        return re.sub(r'(<body[^>]*>)', lambda mm: mm.group(1) + bar, html, count=1)

    def admin_page(self, message='', sf=None):
        allrows = self.study.sessions()
        rows = allrows if sf is None else [r for r in allrows if r['study'] == sf]
        done = sum(r['done'] for r in rows)
        k = urllib.parse.quote(self.study.key)
        sq = '' if sf is None else '&study=' + urllib.parse.quote(sf or 'main')
        info = self.study.reports_info(sf)
        reports = [('dashboard.html', 'Dashboard'), ('explore.html', 'Explore patterns'), ('profiles.html', 'Profiles and clusters'), ('arrangement.html', 'Symmetry and contact')]
        tables = [('participants.csv', 'participants.csv'), ('ingredients_long.csv', 'ingredients_long.csv'), ('pieces_long.csv', 'pieces_long.csv'),
                  ('removals_long.csv', 'removals_long.csv'),
                  ('profiles.csv', 'profiles.csv'), ('explore.csv', 'explore.csv'), ('events_long.csv', 'events_long.csv')]
        if info:
            status = 'Last built %s UTC from %d pizza%s. Opening a report brings it up to date with any newer sessions.' % (
                escape(info[0].replace('T', ' ')[:16]), info[1], '' if info[1] == 1 else 's')
        else:
            status = 'Not built yet. Opening a report builds it.'
        report_btns = ''.join('<a class="btn" href="/admin/reports/%s?key=%s%s">%s</a>' % (f, k, sq, label) for f, label in reports) + \
            '<a class="btn alt" href="/admin/methods?key=%s">Methods: how each number is counted</a>' % k
        table_links = ' · '.join('<a href="/admin/reports/%s?key=%s%s">%s</a>' % (f, k, sq, label) for f, label in tables)
        chips = ''.join('<a class="chip%s" href="/admin?key=%s%s">%s</a>' % (' on' if sf == sid else '', k, '' if sid is None else '&study=' + urllib.parse.quote(sid or 'main'),
                                                                            escape('All studies' if sid is None else sid or 'main'))
                        for sid in [None, ''] + sorted(set(studies()) | {r['study'] for r in allrows if r['study']}))
        trs = ''.join('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            escape(r['pid']), escape(r['study'] or 'main'), escape(r['group']), escape(r['source']), escape(r['about']), escape(r['cond']), escape(r['stage']),
            '' if r['pieces'] is None else r['pieces'], escape(r['started'].replace('T', ' ')[:16]), escape(r['updated'].replace('T', ' ')[:16])) for r in rows)
        note = ('<pre class="note">%s</pre>' % escape(message)) if message else ''
        scope = 'all studies' if sf is None else 'study <b>%s</b>' % escape(sf or 'main')
        return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pizza Study Admin</title><style>
:root{--bg:#f6f2ed;--fg:#2a2421;--muted:#6e635b;--line:#dcd2c7;--panel:#fff;--accent:#a8361d;--accent-ink:#fff}
@media (prefers-color-scheme: dark){:root{--bg:#1d1916;--fg:#eee6de;--muted:#b0a398;--line:#3a322c;--panel:#26211d;--accent:#e0765b;--accent-ink:#1d1916;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:20px 16px}h1{font-size:1.4rem;margin:0 0 4px}.muted{color:var(--muted)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:12px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%%;font-size:.9rem}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:top}
h2{font-size:1.05rem;margin:0 0 8px}.link{display:flex;gap:8px;align-items:center;margin:4px 0;flex-wrap:wrap}
.link span{min-width:90px;color:var(--muted)}.link input{flex:1;min-width:200px;font:inherit;font-size:.85rem;padding:5px 8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg)}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}label{font-size:.85rem;color:var(--muted)}
input,select{font:inherit;padding:6px 8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg)}
button,.btn{font:inherit;padding:8px 14px;border-radius:9px;border:1px solid var(--accent);background:var(--accent);color:var(--accent-ink);cursor:pointer;text-decoration:none;display:inline-block}
.link button{padding:5px 10px}.btn.alt,button.alt{background:transparent;color:var(--fg);border-color:var(--line)}a{color:var(--accent)}
.chip{display:inline-block;padding:4px 12px;border-radius:999px;border:1px solid var(--line);text-decoration:none;color:var(--fg);margin:0 6px 6px 0}.chip.on{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.note{white-space:pre-wrap;font:13px/1.4 ui-monospace,Menlo,Consolas,monospace;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:8px 0 0}
</style></head><body><div class="wrap"><h1>Pizza study</h1><p class="muted">Showing %s: %d sessions, %d finished. <a href="/admin?key=%s%s">Refresh</a></p>
<div>%s</div>%s
<div class="card"><h2>Reports for %s</h2><div class="row">%s</div><p class="muted" style="margin:4px 0">Tables: %s</p>
<p class="muted" style="margin:4px 0">%s</p>
<div class="row"><form method="post" action="/admin/reports?key=%s%s" style="margin:0"><button class="alt" type="submit">Rebuild now</button></form>
<a class="btn" href="/admin/r.zip?key=%s%s">Download for R (.zip)</a>
<a class="btn alt" href="/admin/data.zip?key=%s%s">Download raw sessions (.zip)</a></div>%s</div>
%s
<div class="card"><h2>Sessions</h2><table><tr><th>Participant</th><th>Study</th><th>Group</th><th>Source</th><th>Says they are</th><th>Condition</th><th>Stage</th><th>Pieces</th><th>Started (UTC)</th><th>Last saved</th></tr>%s</table></div>
</div><script>
document.querySelectorAll('.copy').forEach(function (b) {
  b.onclick = function () {
    var i = b.previousElementSibling; i.select();
    function ok() { b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1500); }
    if (navigator.clipboard) navigator.clipboard.writeText(i.value).then(ok, function () { document.execCommand('copy'); ok(); }); else { document.execCommand('copy'); ok(); }
  };
});
</script></body></html>""" % (scope, len(rows), done, k, sq, chips, note, scope, report_btns, table_links, status, k, sq, k, sq, k, sq, note and '',
                               self.studies_card(allrows, sf, k), trs or '<tr><td colspan="10" class="muted">No sessions yet.</td></tr>')


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
