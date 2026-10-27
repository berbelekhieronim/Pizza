#!/usr/bin/env python3
"""Builds and deploys the pizza study to Cloudflare (Worker + D1 database + R2 bucket), as one site.

    python3 cloudflare/deploy.py build     # cloudflare/public: the participant page and the task script
    python3 cloudflare/deploy.py deploy    # everything below, idempotent (run by .github/workflows/cloudflare.yml)
    python3 cloudflare/deploy.py url       # print the site's address

deploy needs CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID and PIZZA_ADMIN_KEY (the owner's researcher password) in the
environment, and optionally PIZZA_GITHUB_TOKEN (lets the Worker ask GitHub for new reports), PIZZA_TURNSTILE_SITE_KEY
and PIZZA_TURNSTILE_SECRET (the bot check on new sessions), GITHUB_REPOSITORY and PIZZA_SITE_URL (a custom domain). It creates the database and the bucket the first time (in the EU: D1 placed in
Eastern Europe, R2 under the EU jurisdiction; PIZZA_EU=0 to leave placement to Cloudflare), applies the schema
migrations, deploys the Worker with server/study.json bundled in, and sets the Worker's secrets.
Standard library only (wrangler, from cloudflare/package.json, does the Cloudflare side).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NAME = 'pizza-study'                     # the Worker and the D1 database
BUCKET = 'pizza-study-files'             # R2: reports, downloads, the Methods page
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


def cf_api(path):
    req = urllib.request.Request('https://api.cloudflare.com/client/v4/accounts/%s%s' % (os.environ['CLOUDFLARE_ACCOUNT_ID'], path),
                                 headers={'Authorization': 'Bearer ' + os.environ['CLOUDFLARE_API_TOKEN']})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)['result']


def site_url():
    if os.environ.get('PIZZA_SITE_URL'):
        return os.environ['PIZZA_SITE_URL'].rstrip('/')
    sub = cf_api('/workers/subdomain')['subdomain']
    return 'https://%s.%s.workers.dev' % (NAME, sub)


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


def deploy():
    for k in ('CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID', 'PIZZA_ADMIN_KEY'):
        if not os.environ.get(k):
            sys.exit('%s is not set. See cloudflare/README.md.' % k)
    if len(os.environ['PIZZA_ADMIN_KEY']) < 12:
        sys.exit('PIZZA_ADMIN_KEY should be at least 12 characters (it is the password of the researcher page).')
    eu = os.environ.get('PIZZA_EU', '1') != '0'
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
                                     'TURNSTILE_SITE_KEY': os.environ.get('PIZZA_TURNSTILE_SITE_KEY', '')}.items() if v}
    path = os.path.join(HERE, 'wrangler.deploy.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    wrangler('d1', 'migrations', 'apply', NAME, '--remote', '--config', path, capture=False)
    wrangler('deploy', '--config', path, capture=False)
    secrets = {'ADMIN_KEY': os.environ['PIZZA_ADMIN_KEY']}
    if os.environ.get('PIZZA_GITHUB_TOKEN'):
        secrets['GITHUB_TOKEN'] = os.environ['PIZZA_GITHUB_TOKEN']
    if os.environ.get('PIZZA_TURNSTILE_SECRET'):
        secrets['TURNSTILE_SECRET'] = os.environ['PIZZA_TURNSTILE_SECRET']
    fd, tmp = tempfile.mkstemp(suffix='.json')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(secrets, f)
        wrangler('secret', 'bulk', tmp, '--config', path)
    finally:
        os.remove(tmp)
    url = site_url()
    print('\n  The pizza study is live.\n  Participant link:  %s/\n  Researcher page:   %s/admin?key=<PIZZA_ADMIN_KEY>\n' % (url, url))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'build':
        print(build())
    elif cmd == 'deploy':
        deploy()
    elif cmd == 'url':
        print(site_url())
    else:
        sys.exit(__doc__)
