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
to add the "typical participant" build.
Standard library only.
"""
import argparse
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


def load_study():
    try:
        with open(os.path.join(HERE, 'study.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


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

    def new_session(self, pid, group, cond):
        """Start (or resume) a participant: assigns a condition in turn when study.json lists any."""
        study = load_study()
        with LOCK:
            pid = pid if (pid and PID_RE.match(pid)) else 'P' + secrets.token_hex(4)
            rec = read_json(self.path(pid), None)
            if rec is None:
                conds = study.get('conditions') or []
                if not cond and conds:
                    state = read_json(os.path.join(self.data, '_state.json'), {'next': 0})
                    cond = conds[state['next'] % len(conds)]
                    state['next'] += 1
                    write_json(os.path.join(self.data, '_state.json'), state)
                rec = {'pid': pid, 'group': (group or '')[:60], 'cond': (cond or '')[:60], 'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
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
                out.append({'pid': r.get('pid', name[:-5]), 'group': r.get('group', ''), 'cond': r.get('cond', ''),
                            'started': r.get('started', ''), 'updated': r.get('updated', ''), 'stage': r.get('stage', 'intro'),
                            'pieces': summ.get('nPieces'), 'done': r.get('stage') == 'done'})
        return out


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
        q = self.query()
        if q.get('key', [''])[0] == self.study.key:
            return True
        cookies = dict(c.strip().split('=', 1) for c in (self.headers.get('Cookie') or '').split(';') if '=' in c)
        return secrets.compare_digest(cookies.get('pzkey', ''), self.study.key)

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
            s = load_study()
            return self.send(200, json.dumps({k: s.get(k) for k in ('title', 'intro', 'consent', 'completion_message', 'completion_redirect', 'typical_build')}), 'application/json')
        if route == '/api/start':
            q = self.query()
            rec = self.study.new_session(q.get('pid', [''])[0] or q.get('PROLIFIC_PID', [''])[0], q.get('group', [''])[0], q.get('cond', [''])[0])
            return self.send(200, json.dumps({'pid': rec['pid'], 'cond': rec.get('cond', ''), 'stage': rec.get('stage', 'intro')}), 'application/json')
        if route.startswith('/admin'):
            if not self.is_admin():
                return self.send(403, '<p>Add <code>?key=</code> with the password printed in the terminal.</p>')
            cookie = {'Set-Cookie': 'pzkey=%s; Path=/admin; HttpOnly; SameSite=Strict; Secure' % self.study.key}
            if route == '/admin':
                return self.send(200, self.admin_page(), headers=cookie)
            if route == '/admin/data.zip':
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                    folder = os.path.join(self.study.data, 'participants')
                    for name in sorted(os.listdir(folder)):
                        if name.endswith('.json'):
                            z.write(os.path.join(folder, name), 'participants/' + name)
                return self.send(200, buf.getvalue(), 'application/zip', {'Content-Disposition': 'attachment; filename="pizza-data-%s.zip"' % time.strftime('%Y%m%d-%H%M')})
            m = re.match(r'^/admin/reports/([A-Za-z0-9_.-]+)$', route)
            if m and not m.group(1).startswith('.'):
                ctype = 'text/html; charset=utf-8' if m.group(1).endswith('.html') else 'text/csv; charset=utf-8'
                return self.file(os.path.join(self.study.data, 'reports', m.group(1)), ctype)
        self.send(404, 'Not found', 'text/plain')

    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        if route == '/api/save':
            body = self.body_json()
            if not isinstance(body, dict) or not isinstance(body.get('fields'), dict):
                return self.send(400, '{"ok":false}', 'application/json')
            ok = self.study.save(body.get('pid'), body['fields'], body.get('stage'))
            return self.send(200 if ok else 404, json.dumps({'ok': ok}), 'application/json')
        if route == '/admin/reports' and self.is_admin():
            out = os.path.join(self.study.data, 'reports')
            files = [os.path.join(self.study.data, 'participants', n) for n in sorted(os.listdir(os.path.join(self.study.data, 'participants'))) if n.endswith('.json')]
            if not files:
                return self.send(200, self.admin_page('No sessions yet.'))
            shutil.rmtree(out, ignore_errors=True)
            r = subprocess.run([sys.executable, os.path.join(ROOT, 'analysis', 'analyse.py')] + files + ['--group', 'group', '--out', out],
                               capture_output=True, text=True, timeout=600)
            msg = (r.stdout + r.stderr).strip()[-600:]
            return self.send(200, self.admin_page(msg or 'Reports built.'))
        self.send(404, 'Not found', 'text/plain')

    def base_url(self):
        if os.environ.get('CODESPACE_NAME'):             # the codespace's public address, whatever the proxy sends
            return public_url(self.server.server_address[1])
        host = self.headers.get('X-Forwarded-Host') or self.headers.get('Host') or 'localhost'
        proto = self.headers.get('X-Forwarded-Proto') or ('https' if host.endswith('.app.github.dev') else 'http')
        return '%s://%s' % (proto, host)

    def links_card(self):
        base = self.base_url() + '/'
        groups = load_study().get('groups') or []
        items = [('Participant link', base)] + [('Group %s' % g, base + '?' + urllib.parse.urlencode({'group': g})) for g in groups]
        rows = ''.join('<div class="link"><span>%s</span><input readonly value="%s" aria-label="%s"><button type="button" class="copy">Copy</button></div>'
                       % (escape(label), escape(url, quote=True), escape(label, quote=True)) for label, url in items)
        return ('<div class="card"><h2>Links to send</h2>%s<p class="muted">The link stays the same every time you start this server in this '
                'codespace. It only works while the server is running and the port is public. To use your own IDs, add <code>&amp;pid=...</code> '
                '(or Prolific\'s <code>PROLIFIC_PID</code>). Add groups in <code>server/study.json</code> to get a link for each.</p></div>' % rows)

    def admin_page(self, message=''):
        rows = self.study.sessions()
        done = sum(r['done'] for r in rows)
        reports = os.path.join(self.study.data, 'reports')
        have = os.path.exists(os.path.join(reports, 'dashboard.html'))
        trs = ''.join('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            escape(r['pid']), escape(r['group']), escape(r['cond']), escape(r['stage']), '' if r['pieces'] is None else r['pieces'],
            escape(r['started'].replace('T', ' ')[:16]), escape(r['updated'].replace('T', ' ')[:16])) for r in rows)
        links = (' · '.join('<a href="/admin/reports/%s">%s</a>' % (f, label) for f, label in
                            [('dashboard.html', 'Dashboard'), ('profiles.html', 'Profiles and clusters'), ('arrangement.html', 'Symmetry and contact'),
                             ('participants.csv', 'participants.csv'), ('ingredients_long.csv', 'ingredients_long.csv'), ('profiles.csv', 'profiles.csv')])
                 if have else 'Not built yet.')
        return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pizza Study Admin</title><style>
:root{--bg:#f6f2ed;--fg:#2a2421;--muted:#6e635b;--line:#dcd2c7;--panel:#fff;--accent:#a8361d}
@media (prefers-color-scheme: dark){:root{--bg:#1d1916;--fg:#eee6de;--muted:#b0a398;--line:#3a322c;--panel:#26211d;--accent:#e0765b;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:20px 16px}h1{font-size:1.4rem;margin:0 0 4px}.muted{color:var(--muted)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:12px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%%;font-size:.9rem}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
h2{font-size:1.05rem;margin:0 0 8px}.link{display:flex;gap:8px;align-items:center;margin:6px 0;flex-wrap:wrap}
.link span{min-width:130px;color:var(--muted)}.link input{flex:1;min-width:220px;font:inherit;font-size:.9rem;padding:7px 9px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg)}
button,.btn{font:inherit;padding:8px 14px;border-radius:9px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer;text-decoration:none;display:inline-block}
.btn.alt{background:transparent;color:var(--fg);border-color:var(--line)}a{color:var(--accent)}pre{white-space:pre-wrap;font-size:.8rem}
</style></head><body><div class="wrap"><h1>Pizza study</h1><p class="muted">%d sessions, %d finished. Reload to refresh.</p>
%s
<div class="card"><form method="post" action="/admin/reports" style="display:inline"><button>Build reports from all sessions</button></form>
<a class="btn alt" href="/admin/data.zip">Download all data (.zip)</a><p>Reports: %s</p>%s</div>
<div class="card"><table><tr><th>Participant</th><th>Group</th><th>Condition</th><th>Stage</th><th>Pieces</th><th>Started (UTC)</th><th>Last saved</th></tr>%s</table></div>
</div><script>
document.querySelectorAll('.copy').forEach(function (b) {
  b.onclick = function () {
    var i = b.previousElementSibling; i.select();
    function ok() { b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1500); }
    if (navigator.clipboard) navigator.clipboard.writeText(i.value).then(ok, function () { document.execCommand('copy'); ok(); }); else { document.execCommand('copy'); ok(); }
  };
});
</script></body></html>""" % (len(rows), done, self.links_card(), links, ('<pre>%s</pre>' % escape(message)) if message else '', trs or '<tr><td colspan="7" class="muted">No sessions yet.</td></tr>')


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
