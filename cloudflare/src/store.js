// The study's database on Cloudflare D1: the same tables and queries as server/store.py (SQLite), so a copy of it
// reads exactly like server/data/study.db. D1 has no BEGIN/COMMIT: a write that must be atomic is one batch().

export const SORTABLE = ['pid', 'study', 'grp', 'source', 'neuro', 'cond', 'stage', 'n_pieces', 'started', 'seconds', 'restarts'];
export const STAGES = ['intro', 'practice', 'build', 'typical', 'followup', 'done'];
const FIELD_RE = /^[a-z_]{2,40}$/;
const INVITE_CHARS = 'abcdefghjkmnpqrstuvwxyz23456789';     // no 0/o, 1/l/i: easy to read out or type

export function now() {
  return new Date().toISOString().slice(0, 19) + 'Z';
}

function isoSeconds(a, b) {
  const t0 = Date.parse((a || '').slice(0, 19) + 'Z'), t1 = Date.parse((b || '').slice(0, 19) + 'Z');
  return Number.isFinite(t0) && Number.isFinite(t1) ? (t1 - t0) / 1000 : null;
}

export function randomToken(n, chars) {
  const bytes = crypto.getRandomValues(new Uint8Array(n));
  if (chars) return Array.from(bytes, (b) => chars[b % chars.length]).join('');
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function summaryColumns(fields) {
  // pieces on the pizza, self-described neurotype, consent, restarts (as summary_columns in store.py)
  const out = {};
  if ('pz_final' in fields) {
    try { out.n_pieces = JSON.parse(fields.pz_final).length; } catch (e) { /* not a list */ }
  }
  if ('pzf_data' in fields) {
    try { out.neuro = ((((JSON.parse(fields.pzf_data) || {}).about) || {}).neuro || []).join(' '); } catch (e) { /* no answers */ }
  }
  if ('consent' in fields) out.consent = fields.consent;
  if ('restarts' in fields && /^-?\d+$/.test(fields.restarts)) out.restarts = parseInt(fields.restarts, 10);
  return out;
}

export class Store {
  constructor(db) {
    this.db = db;
  }

  async get(pid) {
    const row = await this.db.prepare('SELECT * FROM sessions WHERE pid = ?').bind(pid).first();
    if (!row) return null;
    const rec = { ...row, group: row.grp };
    delete rec.grp;
    const { results } = await this.db.prepare('SELECT name, value FROM fields WHERE pid = ?').bind(pid).all();
    for (const f of results) rec[f.name] = f.value;
    return rec;
  }

  async create(pid, study, grp, source, invite, cond) {
    const t = now();
    await this.db.prepare('INSERT OR IGNORE INTO sessions (pid, study, grp, source, invite, cond, started, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)')
      .bind(pid, study, grp.slice(0, 60), source.slice(0, 80), invite, cond.slice(0, 60), t, t).run();
  }

  async nextCondition(study, conds) {
    // conditions assigned in turn, per study: one atomic statement
    const row = await this.db.prepare("INSERT INTO meta (k, v) VALUES (?, '1') ON CONFLICT(k) DO UPDATE SET v = CAST(v AS INTEGER) + 1 RETURNING v")
      .bind('cond_next:' + study).first();
    return conds[(parseInt(row.v, 10) - 1) % conds.length];
  }

  async save(pid, fields, stage) {
    // merges fields into a session (names like pz_final, string values) and records where they are; returns
    // {ok, finishedNow}
    const clean = Object.fromEntries(Object.entries(fields).filter(([k, v]) => FIELD_RE.test(k) && typeof v === 'string'));
    const row = await this.db.prepare('SELECT started, finished, stage FROM sessions WHERE pid = ?').bind(pid).first();
    if (!row) return { ok: false };
    const t = now();
    const st = STAGES.includes(stage) ? stage : row.stage;
    const finished = row.finished || (st === 'done' ? t : null);
    const cols = { ...summaryColumns(clean), stage: st, updated: t, finished, seconds: isoSeconds(row.started, finished || t) };
    const upsert = this.db.prepare('INSERT INTO fields (pid, name, value, updated) VALUES (?, ?, ?, ?) '
      + 'ON CONFLICT(pid, name) DO UPDATE SET value = excluded.value, updated = excluded.updated WHERE value != excluded.value');   // unchanged fields cost no write
    await this.db.batch([
      ...Object.entries(clean).map(([k, v]) => upsert.bind(pid, k, v, t)),
      this.db.prepare(`UPDATE sessions SET ${Object.keys(cols).map((k) => k + ' = ?').join(', ')} WHERE pid = ?`).bind(...Object.values(cols), pid),
    ]);
    return { ok: true, finishedNow: !row.finished && st === 'done' };
  }

  // ---- the researcher page
  static where(f) {
    // study (null = all, '' = main), grp, source, stage, cond, neuro (contains), q (pid contains), since / until
    const sql = [], args = [];
    if (f.study !== null && f.study !== undefined) { sql.push('study = ?'); args.push(f.study); }
    for (const col of ['grp', 'source', 'stage', 'cond']) if (f[col]) { sql.push(col + ' = ?'); args.push(f[col]); }
    if (f.neuro) { sql.push("(' ' || neuro || ' ') LIKE ?"); args.push(`% ${f.neuro} %`); }
    if (f.q) { sql.push('pid LIKE ?'); args.push(`%${f.q}%`); }
    if (f.since) { sql.push('started >= ?'); args.push(f.since); }
    if (f.until) { sql.push('started < ?'); args.push(f.until + 'T99'); }
    return [sql.length ? ' WHERE ' + sql.join(' AND ') : '', args];
  }

  async query(f, sort = 'started', desc = true, limit = 100, offset = 0) {
    const [w, a] = Store.where(f);
    sort = SORTABLE.includes(sort) ? sort : 'started';
    const [total, rows] = await this.db.batch([
      this.db.prepare(`SELECT COUNT(*) AS n, SUM(stage = 'done') AS done FROM sessions${w}`).bind(...a),
      this.db.prepare(`SELECT * FROM sessions${w} ORDER BY ${sort} ${desc ? 'DESC' : 'ASC'}, pid LIMIT ? OFFSET ?`).bind(...a, limit, offset),
    ]);
    return { rows: rows.results, total: total.results[0].n, done: total.results[0].done || 0 };
  }

  async distinct(col, study = null) {
    const [w, a] = Store.where({ study });
    const { results } = await this.db.prepare(`SELECT DISTINCT ${col} AS v FROM sessions${w} ORDER BY 1`).bind(...a).all();
    return results.map((r) => r.v).filter((v) => v !== '' && v !== null);
  }

  async countsByStudy() {
    const { results } = await this.db.prepare("SELECT study, COUNT(*) AS n, SUM(stage = 'done') AS done FROM sessions GROUP BY study").all();
    return Object.fromEntries(results.map((r) => [r.study, [r.n, r.done || 0]]));
  }

  async signatures() {
    // count|newest update, for everything ('all'), the main study ('main') and each study: the reports are rebuilt
    // when one changes
    const { results } = await this.db.prepare('SELECT study, COUNT(*) AS n, MAX(updated) AS u FROM sessions GROUP BY study').all();
    const out = {};
    let n = 0, u = '';
    for (const r of results) {
      out[r.study || 'main'] = `${r.n}|${r.u || ''}`;
      n += r.n;
      if ((r.u || '') > u) u = r.u;
    }
    out.all = `${n}|${u}`;
    return out;
  }

  async exportPage(after, limit) {
    // sessions with every field, by pid, for the reports job (tools/cloud_sync.py)
    const { results: sessions } = await this.db.prepare('SELECT * FROM sessions WHERE pid > ? ORDER BY pid LIMIT ?').bind(after, limit).all();
    if (!sessions.length) return { sessions, fields: [] };
    const { results: fields } = await this.db.prepare('SELECT pid, name, value, updated FROM fields WHERE pid > ? AND pid <= ? ORDER BY pid')
      .bind(after, sessions[sessions.length - 1].pid).all();
    return { sessions, fields };
  }

  async table(name) {
    const { results } = await this.db.prepare(`SELECT * FROM ${name}`).all();   // name is one of a fixed list
    return results;
  }

  // ---- invites
  async createInvites(study, grp, source, note, count) {
    const made = [];
    const t = now();
    while (made.length < count) {
      const batch = Array.from({ length: Math.min(50, count - made.length) }, () => randomToken(8, INVITE_CHARS));
      const res = await this.db.batch(batch.map((tok) => this.db.prepare(
        'INSERT INTO invites SELECT ?1, ?2, ?3, ?4, ?5, ?6 WHERE NOT EXISTS (SELECT 1 FROM invites WHERE token = ?1) AND NOT EXISTS (SELECT 1 FROM sessions WHERE pid = ?1)')
        .bind(tok, study, grp.slice(0, 60), source.slice(0, 80), note.slice(0, 200), t)));
      batch.forEach((tok, i) => { if (res[i].meta.changes) made.push(tok); });
    }
    return made;
  }

  async invite(token) {
    return await this.db.prepare('SELECT * FROM invites WHERE token = ?').bind(token).first();
  }

  async invites(study = null) {
    const q = 'SELECT i.*, s.stage, s.started, s.updated FROM invites i LEFT JOIN sessions s ON s.pid = i.token';
    const stmt = study !== null ? this.db.prepare(q + ' WHERE i.study = ? ORDER BY i.created, i.token').bind(study)
      : this.db.prepare(q + ' ORDER BY i.created, i.token');
    return (await stmt.all()).results;
  }

  // ---- per-study researcher keys
  async studyKey(study) {
    const have = await this.db.prepare('SELECT key FROM study_keys WHERE study = ?').bind(study).first();
    if (have) return have.key;
    await this.db.prepare('INSERT OR IGNORE INTO study_keys VALUES (?, ?, ?)').bind(study, randomToken(12), now()).run();
    return (await this.db.prepare('SELECT key FROM study_keys WHERE study = ?').bind(study).first()).key;
  }

  async studyKeys(studies) {
    const out = {};
    for (const s of studies) out[s] = await this.studyKey(s);
    return out;
  }

  async resetStudyKey(study) {
    await this.db.prepare('DELETE FROM study_keys WHERE study = ?').bind(study).run();
    return this.studyKey(study);
  }

  async studyForKey(key) {
    const r = await this.db.prepare('SELECT study FROM study_keys WHERE key = ?').bind(key).first();
    return r ? r.study : null;
  }

  async meta(k) {
    const r = await this.db.prepare('SELECT v FROM meta WHERE k = ?').bind(k).first();
    return r ? r.v : null;
  }

  async setMeta(k, v) {
    await this.db.prepare('INSERT OR REPLACE INTO meta VALUES (?, ?)').bind(k, v).run();
  }
}

// ---- R2 accounting: storage and monthly operations stay under the free tier (see limits() in worker.js)
export async function storageUsed(db) {
  const r = await db.prepare('SELECT COALESCE(SUM(size), 0) AS used, COUNT(*) AS n FROM files').first();
  return { used: r.used, n: r.n };
}

export async function fileSizes(db) {
  const { results } = await db.prepare('SELECT key, size FROM files').all();
  return Object.fromEntries(results.map((r) => [r.key, r.size]));
}

export async function countOp(db, kind) {
  // one more R2 operation this month (kind: 'writes' or 'reads'); returns the month's count
  const k = `r2_${kind}:${new Date().toISOString().slice(0, 7)}`;
  const row = await db.prepare("INSERT INTO meta (k, v) VALUES (?, '1') ON CONFLICT(k) DO UPDATE SET v = CAST(v AS INTEGER) + 1 RETURNING v").bind(k).first();
  return parseInt(row.v, 10);
}

export async function opsThisMonth(db) {
  const m = new Date().toISOString().slice(0, 7);
  const { results } = await db.prepare('SELECT k, v FROM meta WHERE k IN (?, ?)').bind('r2_writes:' + m, 'r2_reads:' + m).all();
  const get = (k) => parseInt((results.find((r) => r.k === k) || { v: '0' }).v, 10);
  return { writes: get('r2_writes:' + m), reads: get('r2_reads:' + m) };
}
