#!/usr/bin/env python3
"""Builds and deploys the pizza study to Cloudflare (Worker + D1 database + R2 bucket), as one site.

    python3 cloudflare/deploy.py check     # what the Cloudflare token can do (the first FAIL says what to fix)
    python3 cloudflare/deploy.py deploy    # everything below, idempotent (run by .github/workflows/cloudflare.yml)
    python3 cloudflare/deploy.py build     # cloudflare/public only: the participant page and the task script
    python3 cloudflare/deploy.py url       # print the site's address
    python3 cloudflare/deploy.py live      # check the live site (study links, researcher page)
    python3 cloudflare/deploy.py move all tests   # move sessions to another study (Actions -> move sessions)

deploy needs only CLOUDFLARE_API_TOKEN and PIZZA_ADMIN_KEY (the owner's researcher password). It finds the account
(or takes CLOUDFLARE_ACCOUNT_ID), registers a workers.dev subdomain if the account has none (PIZZA_SUBDOMAIN, default
pizza-<account>), creates the Turnstile bot check for the site's address, the D1 database and the R2 bucket the first
time (in the EU: D1 placed in Eastern Europe, R2 under the EU jurisdiction; PIZZA_EU=0 to leave placement to
Cloudflare), applies the schema migrations, deploys the Worker with server/study.json bundled in, and sets its secrets.
Optional: PIZZA_GITHUB_TOKEN (the site asks GitHub for new reports), PIZZA_SITE_URL (a custom domain).
Standard library only (wrangler, from cloudflare/package.json, does the Cloudflare side).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NAME = 'pizza-study'                     # the Worker and the D1 database
BUCKET = 'pizza-study-files'             # R2: reports, downloads, the Methods page
API = os.environ.get('PIZZA_CF_API', 'https://api.cloudflare.com/client/v4')   # (the tests use a stand-in)
PUBLIC = {'index.html': 'server/participate.html', 'pizza-builder.js': 'pizza-builder.js'}


def build():
    out = os.path.join(HERE, 'public')
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for dest, src in PUBLIC.items():
        shutil.copyfile(os.path.join(ROOT, src), os.path.join(out, dest))
    return out


def wrangler(*args, capture=True, check=True):
    exe = os.path.join(HERE, 'node_modules', '.bin', 'wrangler')
    if not os.path.exists(exe):
        subprocess.run(['npm', 'ci', '--no-audit', '--no-fund'], cwd=HERE, check=True)
    r = subprocess.run([exe] + list(args), cwd=HERE, capture_output=capture, text=True,
                       env=dict(os.environ, WRANGLER_SEND_METRICS='false'))
    if check and r.returncode:
        sys.exit('wrangler %s failed:\n%s%s' % (' '.join(args[:3]), r.stdout or '', r.stderr or ''))
    return r


class CfError(Exception):
    pass


def cf(method, path, body=None, account=True):
    """Cloudflare's API with the token: the result, or CfError with Cloudflare's own message."""
    url = API + ('/accounts/%s' % account_id() if account else '') + path
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Bearer ' + os.environ['CLOUDFLARE_API_TOKEN'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)['result']
    except urllib.error.HTTPError as e:
        try:
            errs = json.load(e).get('errors') or []
        except ValueError:
            errs = []
        raise CfError('%s %s: HTTP %d %s' % (method, path, e.code, '; '.join('%s (%s)' % (x.get('message'), x.get('code')) for x in errs)))
    except urllib.error.URLError as e:
        raise CfError('could not reach Cloudflare (%s)' % e.reason)


def account_id():
    """CLOUDFLARE_ACCOUNT_ID, or the token's only account (so it need not be a secret)."""
    if not os.environ.get('CLOUDFLARE_ACCOUNT_ID'):
        accounts = cf('GET', '/accounts', account=False)
        if len(accounts) != 1:
            sys.exit('The token reaches %d Cloudflare accounts: add the CLOUDFLARE_ACCOUNT_ID secret to choose one.' % len(accounts))
        os.environ['CLOUDFLARE_ACCOUNT_ID'] = accounts[0]['id']     # wrangler reads it too
    return os.environ['CLOUDFLARE_ACCOUNT_ID']


def subdomain(create=False):
    """The account's workers.dev subdomain; made (pizza-<account>) when the account has none yet."""
    try:
        sub = (cf('GET', '/workers/subdomain') or {}).get('subdomain')
    except CfError:
        sub = None
    if not sub and create:
        want = os.environ.get('PIZZA_SUBDOMAIN') or 'pizza-' + account_id()[:8]
        sub = cf('PUT', '/workers/subdomain', {'subdomain': want})['subdomain']
        print('  Registered the workers.dev subdomain %s.' % sub)
    if not sub:
        sys.exit('The account has no workers.dev subdomain yet: run the deploy first.')
    return sub


def site_url(create=False):
    if os.environ.get('PIZZA_SITE_URL'):
        return os.environ['PIZZA_SITE_URL'].rstrip('/')
    return 'https://%s.%s.workers.dev' % (NAME, subdomain(create))


def ensure_turnstile(host):
    """The bot check: a Turnstile widget for the site's hostname, made or updated here. (site key, secret), or
    (None, None) when the token may not manage Turnstile (the study then runs with rate limits only)."""
    try:
        widgets = cf('GET', '/challenges/widgets') or []
        w = next((x for x in widgets if x.get('name') == NAME), None)
        if w is None:
            w = cf('POST', '/challenges/widgets', {'name': NAME, 'domains': [host], 'mode': 'managed'})
            print('  Created the Turnstile bot check for %s.' % host)
        elif host not in (w.get('domains') or []):
            w = cf('PUT', '/challenges/widgets/' + w['sitekey'], {'name': NAME, 'domains': sorted(set(w.get('domains') or []) | {host}), 'mode': w.get('mode') or 'managed'})
            print('  Added %s to the Turnstile bot check.' % host)
        secret = w.get('secret') or cf('GET', '/challenges/widgets/' + w['sitekey']).get('secret')
        return w['sitekey'], secret
    except CfError as e:
        print('::warning::No bot check (Turnstile): %s. Add "Account - Turnstile - Edit" to the token, then deploy again.' % e)
        return None, None


def check():
    """What the token can do, step by step (Actions -> cloudflare shows it): the first failing line says what to fix."""
    ok = True
    steps = [('account', lambda: account_id()), ('workers.dev address', lambda: ((cf('GET', '/workers/subdomain') or {}).get('subdomain') or 'none yet') + ' (made on deploy if none)'),
             ('Workers (Workers Scripts)', lambda: '%d workers' % len(cf('GET', '/workers/scripts') or [])),
             ('D1 database', lambda: '%d databases' % len(cf('GET', '/d1/database') or [])),
             ('R2 storage', lambda: '%d buckets' % len((cf('GET', '/r2/buckets') or {}).get('buckets', []))),
             ('Turnstile (bot check)', lambda: '%d widgets' % len(cf('GET', '/challenges/widgets') or []))]
    for name, fn in steps:
        try:
            print('  ok    %-26s %s' % (name, fn()))
        except (CfError, SystemExit) as e:
            ok = False
            print('  FAIL  %-26s %s' % (name, e))
    return ok


def ensure_database(eu):
    dbs = json.loads(wrangler('d1', 'list', '--json').stdout)
    db = next((d for d in dbs if d.get('name') == NAME), None)
    if db is None:
        wrangler('d1', 'create', NAME, *(['--location', 'eeur'] if eu else []))
        db = next(d for d in json.loads(wrangler('d1', 'list', '--json').stdout) if d.get('name') == NAME)
        print('  Created the D1 database %s.' % NAME)
    return db['uuid']


def ensure_bucket(eu):
    r = wrangler('r2', 'bucket', 'create', BUCKET, *(['--jurisdiction', 'eu'] if eu else []), check=False)
    out = (r.stdout or '') + (r.stderr or '')
    if r.returncode and 'already exists' not in out and 'already own' not in out:
        sys.exit('Could not create the R2 bucket %s. Is R2 enabled for the account (Cloudflare dashboard -> R2)?\n%s' % (BUCKET, out))
    if not r.returncode:
        print('  Created the R2 bucket %s.' % BUCKET)


def move(src, dest):
    """Moves sessions and personal links from one study to another in the live database (src 'all' = every study;
    'main' = the main study). Used for test data. Prints counts only."""
    import re
    ok = lambda x: x in ('main', 'all') or re.match(r'^[a-z0-9][a-z0-9-]{0,39}$', x)
    if not (ok(src) and ok(dest)) or dest == 'all' or src == dest:
        sys.exit('Usage: deploy.py move <from study | main | all> <to study | main>')
    with open(os.path.join(ROOT, 'server', 'study.json'), encoding='utf-8') as f:
        known = set((json.load(f).get('studies') or {}))
    if dest != 'main' and dest not in known:
        sys.exit('Study %s is not in server/study.json -> "studies": add it first.' % dest)
    to = '' if dest == 'main' else dest
    where = '' if src == 'all' else " WHERE study = '%s'" % ('' if src == 'main' else src)
    account_id()
    cfg = json.load(open(os.path.join(HERE, 'wrangler.json'), encoding='utf-8'))
    cfg.pop('$schema', None)
    cfg['d1_databases'][0]['database_id'] = ensure_database(os.environ.get('PIZZA_EU', '1') != '0')
    path = os.path.join(HERE, 'wrangler.deploy.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    def q(sql):
        out = wrangler('d1', 'execute', NAME, '--remote', '--json', '--command', sql, '--config', path).stdout
        return json.loads(out[out.index('['):])
    count = lambda: [q('SELECT COUNT(*) AS n FROM %s%s' % (t, where))[0]['results'][0]['n'] for t in ('sessions', 'invites')]
    n = count()
    q("UPDATE sessions SET study = '%s'%s; UPDATE invites SET study = '%s'%s;" % (to, where, to, where))
    left = count() if src != 'all' else [0, 0]
    print('Moved %d sessions and %d personal links from %s to %s%s.' % (n[0], n[1], src, dest, '' if left == [0, 0] else ' (%d sessions did not move)' % left[0]))


def live():
    """Checks the live site from outside (run after every deploy): pages, each study's link, and the researcher page
    with PIZZA_ADMIN_KEY. Prints one line per check, never the key; returns True when all pass."""
    url, ok = site_url(), True
    with open(os.path.join(ROOT, 'server', 'study.json'), encoding='utf-8') as f:
        ids = sorted(json.load(f).get('studies') or {})

    def get(path, key=None):
        q = path + (('&' if '?' in path else '?') + urllib.parse.urlencode({'key': key}) if key else '')
        try:
            with urllib.request.urlopen(urllib.request.Request(url + q, headers={'User-Agent': 'pizza-study-check/1'}), timeout=30) as r:
                return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')
        except urllib.error.URLError as e:
            return 0, str(e.reason)

    def line(good, what, detail=''):
        nonlocal ok
        ok = ok and good
        print('  %s  %-44s %s' % ('ok  ' if good else 'FAIL', what, detail))

    print('Live site %s' % url)
    code, body = get('/')
    line(code == 200 and 'pizza-builder.js' in body, 'participant page', 'HTTP %d' % code)
    for sid in [''] + ids:
        code, body = get('/api/start?' + urllib.parse.urlencode({'study': sid}) if sid else '/api/start')
        try:
            res = json.loads(body)
        except ValueError:
            res = {'error': 'HTTP %d' % code}
        line('error' not in res, 'study link %s' % ('/?study=' + sid if sid else '/ (main)'),
             res.get('error') or ('bot check first' if res.get('verify') else 'starts'))
    key = os.environ.get('PIZZA_ADMIN_KEY', '')
    code, body = get('/admin', key)
    scode, sbody = get('/admin/api/state', key)
    try:
        scope = json.loads(sbody).get('scope')
    except ValueError:
        scope = None
    line(code == 200 and 'Choose a study' in body and scope == 'owner', 'researcher page with PIZZA_ADMIN_KEY', 'HTTP %d, %s' % (code, scope or 'no access'))
    # characters that change a link's meaning when typed into it ('#' cuts it off, '&' starts a new field, ...)
    unsafe = sorted(set(c for c in key if c in '#&+% ?'))
    if unsafe:
        print('::warning::The researcher password contains %s, which breaks it in a link. In the browser type %s as %s, '
              'or change PIZZA_ADMIN_KEY to letters, digits, - and _ and deploy again.'
              % (' '.join(repr(c) for c in unsafe), ', '.join(repr(c) for c in unsafe), ', '.join(urllib.parse.quote(c, safe='') for c in unsafe)))
        print('  note  password in a link                         type %s as %s' % (' '.join(unsafe), ' '.join(urllib.parse.quote(c, safe='') for c in unsafe)))
    return ok


def deploy():
    for k in ('CLOUDFLARE_API_TOKEN', 'PIZZA_ADMIN_KEY'):
        if not os.environ.get(k):
            sys.exit('%s is not set. See cloudflare/README.md.' % k)
    if len(os.environ['PIZZA_ADMIN_KEY']) < 12:
        sys.exit('PIZZA_ADMIN_KEY should be at least 12 characters (it is the password of the researcher page).')
    eu = os.environ.get('PIZZA_EU', '1') != '0'
    if not check():
        sys.exit('The Cloudflare token cannot do everything the deploy needs (FAIL above). See cloudflare/README.md -> the token.')
    url = site_url(create=True)
    site_key, ts_secret = ensure_turnstile(urllib.parse.urlparse(url).hostname)
    build()
    with open(os.path.join(HERE, 'wrangler.json'), encoding='utf-8') as f:
        cfg = json.load(f)
    cfg.pop('$schema', None)
    cfg['d1_databases'][0]['database_id'] = ensure_database(eu)
    ensure_bucket(eu)
    if eu:
        cfg['r2_buckets'][0]['jurisdiction'] = 'eu'
    cfg['vars'] = {k: v for k, v in {'GITHUB_REPO': os.environ.get('GITHUB_REPOSITORY', ''), 'GITHUB_BRANCH': os.environ.get('GITHUB_REF_NAME', 'main'),
                                     'SITE_URL': os.environ.get('PIZZA_SITE_URL', ''),
                                     'TURNSTILE_SITE_KEY': site_key or ''}.items() if v}
    for k in ('R2_LIMIT_BYTES', 'R2_WRITES_PER_MONTH', 'R2_READS_PER_MONTH', 'D1_LIMIT_BYTES'):   # can only lower the caps
        if os.environ.get(k):
            cfg['vars'][k] = os.environ[k]
    path = os.path.join(HERE, 'wrangler.deploy.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    wrangler('d1', 'migrations', 'apply', NAME, '--remote', '--config', path, capture=False)
    wrangler('deploy', '--config', path, capture=False)
    secrets = {'ADMIN_KEY': os.environ['PIZZA_ADMIN_KEY']}
    if os.environ.get('PIZZA_GITHUB_TOKEN'):
        secrets['GITHUB_TOKEN'] = os.environ['PIZZA_GITHUB_TOKEN']
    if ts_secret:
        secrets['TURNSTILE_SECRET'] = ts_secret
    fd, tmp = tempfile.mkstemp(suffix='.json')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(secrets, f)
        wrangler('secret', 'bulk', tmp, '--config', path)
    finally:
        os.remove(tmp)
    print('\n  The pizza study is live.\n  Participant link:  %s/\n  Researcher page:   %s/admin?key=<PIZZA_ADMIN_KEY>\n' % (url, url))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'build':
        print(build())
    elif cmd == 'deploy':
        deploy()
    elif cmd == 'move' and len(sys.argv) == 4:
        move(sys.argv[2], sys.argv[3])
    elif cmd == 'live':
        sys.exit(0 if live() else 1)
    elif cmd == 'check':
        sys.exit(0 if check() else 1)
    elif cmd == 'url':
        print(site_url())
    else:
        sys.exit(__doc__)
