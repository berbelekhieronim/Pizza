// The pizza study on Cloudflare: one Worker serves the participant page, saving, and the researcher page, at one
// address. The same behaviour as server/server.py (the Python study server), with these differences:
// - sessions live in D1 (env.DB, the schema of server/store.py);
// - the reports, the R download, the raw sessions and the database copy are built by a GitHub Actions job
//   (.github/workflows/reports.yml -> tools/cloud_sync.py) and kept in R2 (env.FILES), one set per study and one for
//   all studies; this Worker serves them and asks GitHub for a rebuild when sessions finish (or on "Rebuild now").
// Static files (index.html = server/participate.html, pizza-builder.js) are in ./public (env.ASSETS).
import { Store, STAGES, randomToken } from './store.js';
import { adminPage, deniedPage, withBar } from './admin.js';
import { STUDY_RE, STUDY_KEYS, FILTER_KEYS, loadStudy, studies, scopeName } from './config.js';

const PID_RE = /^[A-Za-z0-9_-]{4,64}$/;
const MAX_BODY = 2_000_000;
const DISPATCH_EVERY = 10 * 60 * 1000;          // ask GitHub for new reports at most every 10 minutes

function headers(ctype, extra = {}) {
  return { 'Content-Type': ctype, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
    'X-Robots-Tag': 'noindex, nofollow', ...extra };
}
const ROBOTS = 'User-agent: *\nDisallow: /\n';     // nothing here is for search engines

async function limited(limiter, key) {
  // Cloudflare's rate limiting (wrangler.json -> ratelimits); true when this key went over its limit
  if (!limiter || !key) return false;
  try { return !(await limiter.limit({ key })).success; } catch (e) { return false; }
}

async function turnstileOk(env, token, ip) {
  // Cloudflare Turnstile: the participant page's invisible "are you a person" check
  if (!token) return false;
  try {
    const r = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
      method: 'POST', body: new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: token, remoteip: ip || '' }),
    });
    return r.ok && (await r.json()).success === true;
  } catch (e) {
    return false;
  }
}
const html = (body, code = 200) => new Response(body, { status: code, headers: headers('text/html; charset=utf-8') });
const json = (obj, code = 200) => new Response(JSON.stringify(obj), { status: code, headers: headers('application/json') });
const text = (body, code = 200) => new Response(body, { status: code, headers: headers('text/plain; charset=utf-8') });

function sameKey(a, b) {
  // constant-time comparison of two keys
  if (typeof a !== 'string' || typeof b !== 'string' || !b) return false;
  const x = new TextEncoder().encode(a), y = new TextEncoder().encode(b);
  let d = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) d |= (x[i] || 0) ^ (y[i] || 0);
  return d === 0;
}

function stamp() {
  return new Date().toISOString().slice(0, 16).replace(/[-:]/g, '').replace('T', '-');
}

export function filterSlug(f) {
  return f.study === null || f.study === undefined ? '' : (f.study || 'main');
}

function csvCell(v) {
  const s = v === null || v === undefined ? '' : String(v);
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
const csvRow = (cells) => cells.map(csvCell).join(',') + '\r\n';

class Request_ {
  constructor(request, env, ctx) {
    this.req = request;
    this.env = env;
    this.ctx = ctx;
    this.url = new URL(request.url);
    this.store = new Store(env.DB);
  }

  arg(k, d = '') {
    const v = this.url.searchParams.get(k);
    return v === null ? d : v;
  }

  ip() {
    return this.req.headers.get('CF-Connecting-IP') || '';
  }

  base() {
    return this.env.SITE_URL || this.url.origin;
  }

  async scope() {
    const key = this.arg('key');
    if (!key) return null;
    if (sameKey(key, this.env.ADMIN_KEY)) return ['owner', null];
    const sid = await this.store.studyForKey(key);
    return sid === null ? null : ['study', sid];
  }

  filters(scope) {
    const f = {};
    for (const k of FILTER_KEYS) f[k] = this.arg(k).trim().slice(0, 80);
    if (scope[0] === 'study') f.study = scope[1];
    else if (f.study === '' || f.study === 'all' || !(f.study === 'main' || STUDY_RE.test(f.study))) f.study = null;
    else f.study = f.study === 'main' ? '' : f.study;
    if (!STAGES.includes(f.stage)) f.stage = '';
    for (const k of ['since', 'until']) if (!/^\d{4}-\d\d-\d\d$/.test(f[k])) f[k] = '';
    return f;
  }

  qs(f, extra = {}, owner = true) {
    const d = new URLSearchParams({ key: this.arg('key') });
    for (const k of FILTER_KEYS) {
      const v = f[k];
      if (k === 'study') { if (v !== null && v !== undefined && owner) d.set('study', v || 'main'); } else if (v) d.set(k, v);
    }
    for (const [k, v] of Object.entries(extra)) if (v !== null && v !== undefined && v !== '') d.set(k, String(v));
    return d.toString();
  }

  download(body, ctype, name) {
    return new Response(body, { headers: headers(ctype, { 'Content-Disposition': `attachment; filename="${name}"` }) });
  }

  resolve(invite, study) {
    return (async () => {
      if (invite) {
        const inv = await this.store.invite(invite);
        return inv ? [inv.study, inv, null] : ['', null, 'This personal link is not valid. Please check that you copied all of it.'];
      }
      if (study && !studies().includes(study)) return ['', null, 'This study link is not valid. Please check that you copied all of it.'];
      return [study || '', null, null];
    })();
  }

  async start() {
    const g = (k) => this.arg(k);
    let [study, inv, err] = await this.resolve(g('i'), g('study'));
    if (err) return json({ error: err });
    let pid = g('pid') || g('PROLIFIC_PID'), group = g('group'), source = g('source'), cond = g('cond');
    if (inv) [pid, group, source] = [g('i'), inv.grp, inv.source];
    pid = pid && PID_RE.test(pid) ? pid : 'P' + randomToken(4, '0123456789abcdef') + randomToken(4, '0123456789abcdef');
    let rec = await this.store.get(pid);
    if (rec && !inv && (rec.study || '') !== study) {           // an id from another study: start afresh
      pid = 'P' + randomToken(8, '0123456789abcdef');
      rec = null;
    }
    if (!rec && !inv && this.env.TURNSTILE_SECRET && this.env.TURNSTILE_SITE_KEY && !(await turnstileOk(this.env, g('ts'), this.ip()))) {
      return json({ verify: this.env.TURNSTILE_SITE_KEY });        // a new session needs the person check first
    }
    if (!rec) {
      const conds = loadStudy(study).conditions || [];
      if (!cond && conds.length) cond = await this.store.nextCondition(study, conds);
      await this.store.create(pid, study, group || '', source || '', inv ? g('i') : '', cond || '');
      rec = await this.store.get(pid);
    }
    return json({ pid: rec.pid, cond: rec.cond || '', stage: rec.stage || 'intro', counts: rec.pz_counts || '', restarts: String(rec.restarts || 0) });
  }

  async save() {
    const n = parseInt(this.req.headers.get('Content-Length') || '0', 10);
    if (n > MAX_BODY) return json({ ok: false }, 400);
    let body;
    try { body = JSON.parse(await this.req.text()); } catch (e) { body = null; }
    if (!body || typeof body !== 'object' || !body.fields || typeof body.fields !== 'object') return json({ ok: false }, 400);
    if (!PID_RE.test(body.pid || '')) return json({ ok: false }, 404);
    if (await limited(this.env.SAVE_LIMIT, body.pid)) return json({ ok: false }, 429);   // a session saves about once a second at most
    const res = await this.store.save(body.pid, body.fields, body.stage);
    if (res.finishedNow) this.ctx.waitUntil(this.requestReports(false));
    return json({ ok: res.ok }, res.ok ? 200 : 404);
  }

  async requestReports(force) {
    // asks GitHub to run the reports job (needs the GITHUB_TOKEN secret); at most every 10 minutes unless forced
    if (!this.env.GITHUB_TOKEN || !this.env.GITHUB_REPO) return 'Reports are rebuilt by the GitHub job every few hours. To rebuild on request, give the Worker a GitHub token (see cloudflare/README.md).';
    const last = parseInt((await this.store.meta('reports_requested')) || '0', 10);
    if (!force && Date.now() - last < DISPATCH_EVERY) return '';
    await this.store.setMeta('reports_requested', String(Date.now()));
    const r = await fetch(`https://api.github.com/repos/${this.env.GITHUB_REPO}/actions/workflows/reports.yml/dispatches`, {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + this.env.GITHUB_TOKEN, Accept: 'application/vnd.github+json', 'User-Agent': 'pizza-study-worker',
        'Content-Type': 'application/json' },
      body: JSON.stringify({ ref: this.env.GITHUB_BRANCH || 'main', inputs: force ? { force: 'true' } : {} }),
    });
    return r.ok ? 'Rebuilding the reports: they are ready in a few minutes (reload this page).' : `GitHub refused the rebuild (${r.status}). Check the Worker's GitHub token.`;
  }

  async builtInfo(scope) {
    const o = await this.env.FILES.get(`reports/${scope}/.built`);
    if (!o) return null;
    try { return JSON.parse(await o.text()); } catch (e) { return null; }
  }

  async fileFromR2(key, name, ctype, f, scope, missing) {
    const o = await this.env.FILES.get(key);
    if (!o) return html(await adminPage(this, scope, f, missing));
    return this.download(o.body, ctype, name);
  }

  async admin() {
    const route = this.url.pathname;
    const scope = await this.scope();
    if (!scope) return html(deniedPage(), 403);
    const owner = scope[0] === 'owner';
    if (this.req.method === 'PUT' || route === '/admin/signatures' || route.startsWith('/admin/export') || route.startsWith('/admin/files/')) {
      if (!owner) return text('Not found', 404);
      return this.machine(route);
    }
    const f = this.filters(scope);
    const sc = scopeName(f);
    const st = this.store;
    if (this.req.method === 'POST') return this.post(route, scope, f);
    if (route === '/admin') return html(await adminPage(this, scope, f, this.arg('msg')));
    if (route === '/admin/sessions.csv') {
      const { rows } = await st.query(f, this.arg('sort', 'started'), this.arg('dir', 'desc') !== 'asc', 1e9);
      const cols = ['pid', 'study', 'grp', 'source', 'invite', 'cond', 'stage', 'started', 'updated', 'finished', 'seconds', 'restarts', 'consent', 'n_pieces', 'neuro'];
      let out = csvRow(cols.map((c) => (c === 'grp' ? 'group' : c)));
      for (const r of rows) out += csvRow(cols.map((c) => (c === 'study' && !r[c] ? 'main' : r[c] === null ? 'NA' : r[c])));
      return this.download(out, 'text/csv; charset=utf-8', `sessions-${filterSlug(f) || 'all'}-${stamp()}.csv`);
    }
    if (route === '/admin/invites.csv') {
      let out = '﻿' + csvRow(['invite', 'link', 'study', 'group', 'source', 'note', 'created', 'status', 'started', 'last_saved']);
      for (const inv of await st.invites(f.study)) {
        const status = inv.stage === 'done' ? 'finished' : inv.stage ? 'started' : 'not opened';
        out += csvRow([inv.token, this.base() + '/?i=' + inv.token, inv.study || 'main', inv.grp, inv.source, inv.note, inv.created, status, inv.started || '', inv.updated || '']);
      }
      return this.download(out, 'text/csv; charset=utf-8', `invite-links-${filterSlug(f) || 'all'}-${stamp()}.csv`);
    }
    const missing = 'Not built yet. The GitHub job builds the reports and downloads a few minutes after sessions finish (or press "Rebuild now").';
    if (route === '/admin/r.zip') return this.fileFromR2(`exports/${sc}/pizza-data-R.zip`, `pizza-data-R-${sc}-${stamp()}.zip`, 'application/zip', f, scope, missing);
    if (route === '/admin/data.zip') return this.fileFromR2(`exports/${sc}/sessions.zip`, `pizza-sessions-${sc}-${stamp()}.zip`, 'application/zip', f, scope, missing);
    if (route === '/admin/database.sqlite') return this.fileFromR2(`exports/${sc}/study.sqlite`, `pizza-study-${sc}-${stamp()}.sqlite`, 'application/vnd.sqlite3', f, scope, missing);
    if (route === '/admin/methods') {
      const o = await this.env.FILES.get('methods.html');
      return html(o ? withBar(this, await o.text(), f, scope) : await adminPage(this, scope, f, missing));
    }
    const m = route.match(/^\/admin\/reports\/([A-Za-z0-9_-][A-Za-z0-9_.-]*)$/);
    if (m) {
      const o = await this.env.FILES.get(`reports/${sc}/${m[1]}`);
      if (!o) return html(await adminPage(this, scope, f, missing));
      if (m[1].endsWith('.html')) return html(withBar(this, await o.text(), f, scope));
      return new Response(o.body, { headers: headers('text/csv; charset=utf-8') });
    }
    return text('Not found', 404);
  }

  async post(route, scope, f) {
    let msg = '';
    const form = route === '/admin/reports' ? {} : Object.fromEntries(new URLSearchParams((await this.req.text()).slice(0, 10000)));
    if (route === '/admin/reports') {
      msg = await this.requestReports(true);
    } else if (route === '/admin/invites') {
      let sid = form.study === 'main' ? '' : (form.study || '');
      if (scope[0] === 'study') sid = scope[1];               // a study's researchers make links for their study only
      const count = Math.max(0, Math.min(500, parseInt(form.count || '0', 10) || 0));
      if (sid && !studies().includes(sid)) msg = `Unknown study ${sid}: add it to "studies" in server/study.json first.`;
      else if (!count) msg = 'Say how many links to make (1-500).';
      else {
        await this.store.createInvites(sid, (form.group || '').trim(), (form.source || '').trim(), (form.note || '').trim(), count);
        msg = `Made ${count} personal link${count === 1 ? '' : 's'} for ${sid || 'the main study'}. Download them with "Personal links (.csv)".`;
      }
    } else if (route === '/admin/study-key' && scope[0] === 'owner') {
      const sid = form.study === 'main' ? '' : (form.study || '');
      await this.store.resetStudyKey(sid);
      msg = `Made a new researcher link for ${sid || 'the main study'}: the old one no longer works.`;
    } else {
      return text('Not found', 404);
    }
    // redirect so that reloading the page does not repeat the action
    return new Response('', { status: 303, headers: headers('text/plain', { Location: '/admin?' + this.qs(f, { msg }, scope[0] === 'owner') }) });
  }

  async machine(route) {
    // owner-only routes for the reports job (tools/cloud_sync.py): what changed, the data, and storing the results
    if (route === '/admin/signatures') {
      return json({ signatures: await this.store.signatures(), studies: studies() });
    }
    if (route === '/admin/export') {
      const limit = Math.max(1, Math.min(200, parseInt(this.arg('limit', '25'), 10) || 25));
      return json(await this.store.exportPage(this.arg('after'), limit));
    }
    if (route === '/admin/export/tables') {
      return json({ invites: await this.store.table('invites'), meta: await this.store.table('meta') });
    }
    const m = route.match(/^\/admin\/files\/((?:reports|exports)\/[a-z0-9-]{1,40}\/[A-Za-z0-9_.-]{1,80}|methods\.html|state\.json)$/);
    if (!m) return text('Not found', 404);
    if (this.req.method === 'PUT') {
      await this.env.FILES.put(m[1], this.req.body);
      return json({ ok: true });
    }
    const o = await this.env.FILES.get(m[1]);
    return o ? new Response(o.body, { headers: headers('application/octet-stream') }) : text('Not found', 404);
  }

  async route() {
    const p = this.url.pathname;
    if (p === '/study.json') {
      const [sid] = await this.resolve(this.arg('i'), this.arg('study'));
      const s = loadStudy(sid);
      return json(Object.fromEntries(STUDY_KEYS.filter((k) => k !== 'conditions' && k !== 'groups').map((k) => [k, s[k] === undefined ? null : s[k]])));
    }
    if (p === '/robots.txt') return new Response(ROBOTS, { headers: headers('text/plain; charset=utf-8', { 'Cache-Control': 'public, max-age=86400' }) });
    if (p === '/api/start') {
      if (await limited(this.env.START_LIMIT, this.ip())) return json({ error: 'Too many new sessions from this connection. Please wait a minute and reload the page.' }, 429);
      return this.start();
    }
    if (p === '/api/save' && this.req.method === 'POST') return this.save();
    if (p === '/admin' || p.startsWith('/admin/')) {
      if (await limited(this.env.ADMIN_LIMIT, this.ip())) return text('Too many requests: wait a minute.', 429);
      return this.admin();
    }
    if (p.startsWith('/api/')) return text('Not found', 404);
    const res = await this.env.ASSETS.fetch(this.req);    // index.html (the participant page), pizza-builder.js, ...
    const out = new Response(res.body, res);
    out.headers.set('X-Robots-Tag', 'noindex, nofollow');
    return out;
  }
}

export default {
  async fetch(request, env, ctx) {
    return new Request_(request, env, ctx).route();
  },
};

