// One D1 database per project, inside Cloudflare's free plan (10 databases, 500 MB each, 5 GB in all; 50 queries per
// Worker invocation, a batch counting as one: developers.cloudflare.com/d1/platform/limits).
//
// The main database (binding DB) is the control database: settings, the history of their changes, researcher keys, the
// R2 accounting, the condition counters, and where each session and personal link of a project with its own database
// lives ('home:<pid>', 'inv:<token>' in meta). It also keeps every study that has no database of its own, as before:
// the pilot stays there, untouched. A study gets its own database with "database": "DB_<NAME>" in server/study.json
// (deploy.py creates the D1 database and its binding); its new sessions and links go there.
//
// Router has the methods of Store that the routes use, so a route asks the router and the router picks the database:
// by the study when it is known, by the session's or link's home otherwise, and over every database for "all studies".
import { Store, STATUSES, SYN_SQL, idleCutoff, now, randomToken } from './store.js';
import { studies, fileSettings } from './config.js';

export const DB_RE = /^DB_[A-Z0-9_]{1,30}$/;
let EXTRA = {};                       // study -> database from the STUDY_DATABASES var (tests); study.json wins
export function setDatabases(env) {
  try { EXTRA = env && env.STUDY_DATABASES ? JSON.parse(env.STUDY_DATABASES) : {}; } catch (e) { EXTRA = {}; }
}
// the binding name of a study's database: 'DB' (the main one) unless the study has its own
export function dbName(sid) {
  if (!sid) return 'DB';                // the main study always lives in the main database
  const d = ((fileSettings().studies || {})[sid] || {}).database || EXTRA[sid];
  return typeof d === 'string' && DB_RE.test(d) ? d : 'DB';
}

// D1 with a query counter: every first/all/run/raw is one query, a batch is one (as the free plan counts them)
function counted(db, c) {
  const raw = new WeakMap();
  const wrap = (s) => {
    const p = new Proxy(s, {
      get(t, k) {
        const v = t[k];
        if (k === 'bind') return (...a) => wrap(v.apply(t, a));
        if (k === 'first' || k === 'all' || k === 'run' || k === 'raw') return (...a) => { c.n++; return v.apply(t, a); };
        return typeof v === 'function' ? v.bind(t) : v;
      },
    });
    raw.set(p, s);
    return p;
  };
  return {
    prepare: (q) => wrap(db.prepare(q)),
    batch: (stmts) => { c.n++; return db.batch(stmts.map((s) => raw.get(s) || s)); },
    exec: (q) => { c.n++; return db.exec(q); },
  };
}

export class Router {
  constructor(env) {
    this.env = env;
    this.count = { n: 0 };
    setDatabases(env);
    this.control = new Store(counted(env.DB, this.count));
    this.db = this.control.db;             // the control database (meta, keys, files)
    this.stores = { DB: this.control };
  }

  // ---- which database
  named(name) {
    if (name === 'DB') return this.control;
    if (!this.env[name]) return null;     // configured but not deployed yet: nothing is stored anywhere else
    return this.stores[name] || (this.stores[name] = new Store(counted(this.env[name], this.count)));
  }
  of(sid) { return this.named(dbName(sid)); }
  separate() { return studies().some((s) => dbName(s) !== 'DB'); }
  // every database in use, the main one first: [{name, store, studies}]
  all() {
    const by = { DB: [''] };
    for (const s of studies()) (by[dbName(s)] = by[dbName(s)] || []).push(s);
    return Object.entries(by).map(([name, ss]) => ({ name, store: this.named(name), studies: ss })).filter((x) => x.store);
  }
  async home(pid) {
    // the database holding this session: the main one, unless it was started in a project with its own
    if (!this.separate()) return this.control;
    const sid = await this.control.meta('home:' + pid);
    return (sid !== null && this.of(sid)) || this.control;
  }
  async size(sid) {
    // the size in bytes of the database a study saves to (every D1 result reports it)
    const st = this.of(sid);
    if (!st) return 0;
    const r = await st.db.prepare('SELECT 1').run();
    return (r.meta && r.meta.size_after) || 0;
  }

  // ---- the control database's own data
  meta(k) { return this.control.meta(k); }
  setMeta(k, v) { return this.control.setMeta(k, v); }
  settingsAll() { return this.control.settingsAll(); }
  studyKey(s) { return this.control.studyKey(s); }
  studyKeys(s) { return this.control.studyKeys(s); }
  resetStudyKey(s) { return this.control.resetStudyKey(s); }
  studyForKey(k) { return this.control.studyForKey(k); }
  nextCondition(study, conds) { return this.control.nextCondition(study, conds); }

  // ---- sessions
  async get(pid) { return (await this.home(pid)).get(pid); }
  async create(pid, study, grp, source, invite, cond) {
    const st = this.of(study);
    if (st !== this.control) await this.control.setMeta('home:' + pid, study);
    return st.create(pid, study, grp, source, invite, cond);
  }
  async save(pid, fields, stage) { return (await this.home(pid)).save(pid, fields, stage); }
  async setInclusion(pid, value, study = null) { return (await this.home(pid)).setInclusion(pid, value, study); }
  async syncSynthetic(study, add, keep, version) {
    const r = await this.of(study).syncSynthetic(study, add, keep, version);
    if (version && this.of(study) !== this.control) await this.control.setMeta('synthetic_version:' + study, String(version));
    return r;
  }

  async query(f, sort = 'started', desc = true, limit = 100, offset = 0, grouped = false, thumbs = false) {
    if (f.study !== null && f.study !== undefined) return this.of(f.study).query(f, sort, desc, limit, offset, grouped, thumbs);
    const dbs = this.all();
    if (dbs.length === 1) return this.control.query(f, sort, desc, limit, offset, grouped, thumbs);
    // every study: each database's first offset + limit rows, merged in the same order, then the page
    const parts = await Promise.all(dbs.map((d) => d.store.query(f, sort, desc, offset + limit, 0, grouped, thumbs)));
    const rows = [].concat(...parts.map((p) => p.rows));
    const key = ['started', 'pid', 'study', 'grp', 'source', 'neuro', 'cond', 'stage', 'n_pieces', 'updated', 'seconds', 'restarts'].includes(sort) ? sort : 'started';
    const cmp = (a, b) => {
      if (grouped && a.listgroup !== b.listgroup) return a.listgroup - b.listgroup;
      const x = a[key], y = b[key];
      if (x !== y) {
        if (x === null || x === undefined) return desc ? 1 : -1;
        if (y === null || y === undefined) return desc ? -1 : 1;
        return (x < y ? -1 : 1) * (desc ? -1 : 1);
      }
      return a.pid < b.pid ? -1 : a.pid > b.pid ? 1 : 0;
    };
    rows.sort(cmp);
    const sum = (k) => parts.reduce((a, p) => a + (p[k] || 0), 0);
    return { rows: rows.slice(offset, offset + limit), total: sum('total'), done: sum('done'), folded: sum('folded') };
  }

  async distinct(col, study = null) {
    if (study !== null) return this.of(study).distinct(col, study);
    const all = await Promise.all(this.all().map((d) => d.store.distinct(col, null)));
    return [...new Set([].concat(...all))].sort();
  }

  async countsByStudy() {
    const out = {};
    for (const d of this.all()) Object.assign(out, await d.store.countsByStudy());
    return out;
  }

  async signatures() {
    if (this.all().length === 1) return this.control.signatures();
    const out = {};
    let n = 0, u = '';
    for (const d of this.all()) {
      const s = await d.store.signatures();
      for (const [k, v] of Object.entries(s)) {
        if (k === 'all') { const [c, t] = v.split('|'); n += +c; if ((t || '') > u) u = t; } else out[k] = v;
      }
    }
    // a new choice of synthetic sessions (kept in the control database) counts as an update too
    const { results } = await this.control.db.prepare("SELECT k, v FROM meta WHERE k LIKE 'synthetic_at:%'").all();
    for (const r of results) {
      const sid = r.k.slice(13) || 'main';
      if (out[sid] !== undefined && r.v > out[sid].split('|')[1]) out[sid] = out[sid].split('|')[0] + '|' + r.v;
      if (r.v > u) u = r.v;
    }
    out.all = `${n}|${u}`;
    return out;
  }

  async exportPage(after, limit) {
    // every database's next sessions after this pid, merged by pid (ids are unique across the databases)
    const dbs = this.all();
    if (dbs.length === 1) return this.control.exportPage(after, limit);
    const parts = await Promise.all(dbs.map((d) => d.store.exportPage(after, limit)));
    const sessions = [].concat(...parts.map((p) => p.sessions)).sort((a, b) => (a.pid < b.pid ? -1 : 1)).slice(0, limit);
    const keep = new Set(sessions.map((s) => s.pid));
    return { sessions, fields: [].concat(...parts.map((p) => p.fields)).filter((x) => keep.has(x.pid)).sort((a, b) => (a.pid < b.pid ? -1 : a.pid > b.pid ? 1 : 0)) };
  }

  async table(name) {
    if (name !== 'invites' || this.all().length === 1) return this.control.table(name);
    return [].concat(...(await Promise.all(this.all().map((d) => d.store.table(name)))));
  }

  // ---- personal links
  async createInvites(study, grp, source, note, count) {
    const st = this.of(study);
    const made = await st.createInvites(study, grp, source, note, count);
    if (st !== this.control && made.length) {
      const ins = this.control.db.prepare('INSERT OR REPLACE INTO meta VALUES (?, ?)');
      for (let i = 0; i < made.length; i += 100) await this.control.db.batch(made.slice(i, i + 100).map((t) => ins.bind('inv:' + t, study)));
    }
    return made;
  }
  async invite(token) {
    const inv = await this.control.invite(token);
    if (inv || !this.separate()) return inv;
    const sid = await this.control.meta('inv:' + token);
    return sid !== null && this.of(sid) ? this.of(sid).invite(token) : null;
  }
  async invites(study = null) {
    if (study !== null) return this.of(study).invites(study);
    return [].concat(...(await Promise.all(this.all().map((d) => d.store.invites(null)))));
  }

  // ---- the researcher page's overview: every study's numbers in one batch per database (a few queries in all,
  // however many studies there are: the free plan allows 50 per request)
  async overview() {
    const out = {};
    const blank = () => ({ n: 0, done: 0, syn: 0, status: Object.fromEntries(STATUSES.map((k) => [k, 0])), last: null, seconds: [], inv: [0, 0, 0] });
    for (const d of this.all()) {
      Object.assign(out, await d.store.overview(blank));
    }
    return out;
  }
  async keysFor(list) {
    // the researcher keys of these studies (and '*'), making the missing ones: two or three queries in all
    const db = this.control.db;
    const read = async () => Object.fromEntries((await db.prepare('SELECT study, key FROM study_keys').all()).results.map((r) => [r.study, r.key]));
    let have = await read();
    const miss = list.filter((s) => have[s] === undefined);
    if (miss.length) {
      const ins = db.prepare('INSERT OR IGNORE INTO study_keys VALUES (?, ?, ?)');
      await db.batch(miss.map((s) => ins.bind(s, randomToken(12), now())));
      have = await read();
    }
    return have;
  }
  async syntheticChoices() {
    // {study: n} chosen on the researcher page (meta synthetic_n:<study>, one query)
    const { results } = await this.control.db.prepare("SELECT k, v FROM meta WHERE k LIKE 'synthetic_n:%'").all();
    return Object.fromEntries(results.filter((r) => /^\d+$/.test(r.v)).map((r) => [r.k.slice(12), parseInt(r.v, 10)]));
  }
  async options(study) {
    // the Sessions tab's filter choices (groups, sources, conditions): one batch per database
    const dbs = study !== null && study !== undefined ? [this.of(study)] : this.all().map((d) => d.store);
    const out = { grp: new Set(), source: new Set(), cond: new Set() };
    for (const st of dbs) {
      const got = await st.distinctAll(study);
      for (const k of Object.keys(out)) got[k].forEach((v) => out[k].add(v));
    }
    return Object.fromEntries(Object.entries(out).map(([k, v]) => [k, [...v].sort()]));
  }
  async lastChange() {
    // the newest save or inclusion choice anywhere, or a new synthetic choice: the reports are out of date after it
    let last = null;
    for (const d of this.all()) {
      const t = await d.store.lastChange(d.store === this.control);
      if (t && (!last || t > last)) last = t;
    }
    return last;
  }
  // where the databases stand against the free plan: [{name, studies, bytes}] (one tiny query each)
  async databases() {
    const out = [];
    for (const d of this.all()) {
      const r = await d.store.db.prepare('SELECT 1').run();
      out.push({ name: d.name, studies: d.studies.map((s) => s || 'main'), bytes: (r.meta && r.meta.size_after) || 0 });
    }
    // studies configured with a database that is not deployed yet, and sessions of such studies left in the main one
    const missing = studies().filter((s) => dbName(s) !== 'DB' && !this.env[dbName(s)]);
    return { list: out, missing };
  }
}

export { SYN_SQL, idleCutoff, now };
