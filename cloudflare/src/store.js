// The study's database on Cloudflare D1: the same tables and queries as server/store.py (SQLite), so a copy of it
// reads exactly like server/data/study.db. D1 has no BEGIN/COMMIT: a write that must be atomic is one batch().

export const SORTABLE = ['pid', 'study', 'grp', 'source', 'neuro', 'cond', 'stage', 'n_pieces', 'started', 'updated', 'seconds', 'restarts'];
// survey: the study's questions asked before the pizza (survey_when = before); followup: after it (as store.py)
export const STAGES = ['intro', 'survey', 'practice', 'build', 'typical', 'followup', 'done', 'declined'];   // declined: said no to the consent
export const ACTIVITY = ['active', 'stopped'];     // extra "where" filter values, from the time of the last save
export const ANALYSIS = ['included', 'pending', 'left_out', 'flagged', 'synthetic', 'real', 'analysed', 'in_progress', 'excluded', 'abandoned', 'no_pizza'];  // ... from whether the session's pizza is analysed, needs a look, or is synthetic
const SYN_SQL = "pid LIKE 'SYN-%'";               // synthetic sessions of a test study (analysis/synthetic.py), as in store.py
// The researcher's choice for a session (field 'inclusion', never taken from a participant's save), as in store.py
export const INCLUSION_VALUES = ['include', 'exclude', 'auto'];
const INCL_SQL = "COALESCE((SELECT NULLIF(value, 'auto') FROM fields WHERE fields.pid = sessions.pid AND name = 'inclusion'), '')";
// saved by the participant page: browser, system, time zone, trouble saving or in the page (as store.py CLIENT_SQL)
export const CLIENT_FIELDS = ['browser', 'os', 'tz', 'browser_flags', 'translated', 'save_fails', 'client_errors'];
const CLIENT_SQL = CLIENT_FIELDS.map((k) => `(SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = '${k}') AS ${k}`).join(', ');
// The automatic rule (as store.py and analysis/analyse.py): the own pizza is analysed when it was finished (its summary
// is not "finished": false; not the stage, which a tab closed while baking or saves out of order can leave at "build"),
// unless the browser was driven by a program; the researcher's choice overrides both
export const AUTO_EXCLUDE_FLAGS = ['automated'];
const SUMMARY = "COALESCE((SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = 'pz_summary'), '')";
// finished: the summary says so, or the session got past the build (a pizza whose last saves were lost still counts; store.py)
const FINISHED_SQL = `(stage IN ('typical', 'followup', 'done') OR (${SUMMARY} NOT LIKE '%"finished":false%' AND ${SUMMARY} NOT LIKE '%"finished": false%'))`;
const FLAGS = "(' ' || COALESCE((SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = 'browser_flags'), '') || ' ')";
const FLAGGED_OUT_SQL = '(' + AUTO_EXCLUDE_FLAGS.map((f) => `${FLAGS} LIKE '% ${f} %'`).join(' OR ') + ')';
const AUTO_IN_SQL = `(n_pieces IS NOT NULL AND ${FINISHED_SQL} AND NOT ${FLAGGED_OUT_SQL})`;
// an unfinished pizza is pending while its session saved within ABANDON_HOURS, then abandoned (left out); as store.py
export const ABANDON_HOURS = 24;
const PENDING_SQL = `(${INCL_SQL} = '' AND n_pieces IS NOT NULL AND NOT ${FINISHED_SQL} AND NOT ${FLAGGED_OUT_SQL} `
  + `AND stage NOT IN ('done', 'declined') AND updated >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-${ABANDON_HOURS} hours'))`;
const LEFT_OUT_SQL = `(${INCL_SQL} = 'exclude' OR (${INCL_SQL} = '' AND n_pieces IS NOT NULL AND NOT ${AUTO_IN_SQL} AND NOT ${PENDING_SQL}))`;
const INCLUDED_SQL = `(${INCL_SQL} = 'include' OR (${INCL_SQL} = '' AND ${AUTO_IN_SQL}))`;
// every session's one status (as store.py STATUS_SQL; one ? = idleCutoff()): the tiles count them, the Sessions tab
// groups and labels by them
export const STATUSES = ['analysed', 'active', 'pending', 'excluded', 'excluded_auto', 'abandoned', 'no_pizza', 'declined'];
const STATUS_SQL = `(CASE WHEN stage = 'declined' THEN 'declined' `
  + `WHEN n_pieces IS NULL THEN (CASE WHEN stage != 'done' AND updated >= ? THEN 'active' ELSE 'no_pizza' END) `
  + `WHEN ${INCLUDED_SQL} THEN 'analysed' WHEN ${INCL_SQL} = 'exclude' THEN 'excluded' `
  + `WHEN ${PENDING_SQL} THEN 'pending' WHEN ${FLAGGED_OUT_SQL} THEN 'excluded_auto' ELSE 'abandoned' END)`;
// the Sessions tab's groups: 0 in the reports, 1 in progress (active or pending), 2 the rest (folded); one ?
const LIST_GROUP_SQL = `(CASE ${STATUS_SQL} WHEN 'analysed' THEN 0 WHEN 'active' THEN 1 WHEN 'pending' THEN 1 ELSE 2 END)`;
// browser trouble worth a look before analysing (docs/BROWSERS.md): the "needs a look" filter, as store.py REVIEW_SQL
export const REVIEW_FLAGS = ['translated', 'coarse-timer', 'forced-colors', 'automated'];   // small-window: information only from 0.18.1
// page errors other than Chrome's harmless "ResizeObserver loop" notice (store.py REAL_ERRORS_SQL)
const REAL_ERRORS_SQL = `(LENGTH(value) - LENGTH(REPLACE(value, '"]', ''))) / 2 > (LENGTH(value) - LENGTH(REPLACE(value, 'ResizeObserver loop', ''))) / 19`;
const REVIEW_SQL = '(' + REVIEW_FLAGS.map((f) => `${FLAGS} LIKE '% ${f} %'`).join(' OR ')
  + ` OR EXISTS (SELECT 1 FROM fields WHERE fields.pid = sessions.pid AND name = 'client_errors' AND ${REAL_ERRORS_SQL}))`;
const STAGE_RANK = { intro: 0, survey: 1, practice: 2, build: 3, typical: 4, followup: 5, done: 6, declined: 6 };
export function laterStage(old, stage) {
  // a save never moves a session back to an earlier part (saves can arrive out of order); done and declined are final
  // (as store.py later_stage)
  if (!STAGES.includes(stage)) return old;
  if (!(old in STAGE_RANK)) return stage;
  return STAGE_RANK[stage] > STAGE_RANK[old] ? stage : old;
}
// what the analysis does with a session: included / left_out / no_pizza (shown on the Sessions tab and in sessions.csv)
const ANALYSIS_SQL = `CASE WHEN n_pieces IS NULL THEN 'no_pizza' WHEN ${INCLUDED_SQL} THEN 'included' WHEN ${PENDING_SQL} THEN 'pending' ELSE 'left_out' END`;
export const IDLE_MINUTES = 30;                    // an unfinished session with no save for this long counts as stopped
const idleCutoff = () => new Date(Date.now() - IDLE_MINUTES * 60000).toISOString().slice(0, 19) + 'Z';
const FIELD_RE = /^[a-z_]{2,40}$/;

// true when save_seq a ("<page load>:<n>") is older than the stored b from the same page load (store.py stale_save)
export function staleSave(a, b) {
  const x = String(a || '').split(':'), y = String(b || '').split(':');
  return x.length === 2 && y.length === 2 && x[0] === y[0] && /^\d+$/.test(x[1]) && /^\d+$/.test(y[1]) && +x[1] < +y[1];
}
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
    const clean = Object.fromEntries(Object.entries(fields).filter(([k, v]) => FIELD_RE.test(k) && k !== 'inclusion' && typeof v === 'string'));
    const row = await this.db.prepare('SELECT started, finished, stage FROM sessions WHERE pid = ?').bind(pid).first();
    if (!row) return { ok: false };
    // a save older than one already stored from the same page (they can arrive out of order) changes nothing
    // (store.py stale_save; save_seq = "<page load id>:<count>" from participate.html)
    if (clean.save_seq) {
      const old = await this.db.prepare("SELECT value FROM fields WHERE pid = ? AND name = 'save_seq'").bind(pid).first();
      if (staleSave(clean.save_seq, old ? old.value : null)) for (const k of Object.keys(clean)) delete clean[k];
    }
    const t = now();
    const st = laterStage(row.stage, stage);
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
    if (f.stage === 'active') { sql.push("stage NOT IN ('done', 'declined') AND updated >= ?"); args.push(idleCutoff()); }
    if (f.stage === 'stopped') { sql.push("stage NOT IN ('done', 'declined') AND (updated IS NULL OR updated < ?)"); args.push(idleCutoff()); }   // a refusal is counted on its own (stage declined)
    if (f.stage === 'included') sql.push(INCLUDED_SQL);
    if (f.stage === 'left_out') sql.push(LEFT_OUT_SQL);
    if (f.stage === 'flagged') sql.push(REVIEW_SQL);
    if (f.stage === 'pending') sql.push(PENDING_SQL);
    if (['analysed', 'in_progress', 'excluded', 'abandoned', 'no_pizza'].includes(f.stage)) {     // by status (the tiles)
      const want = { in_progress: ['active', 'pending'], excluded: ['excluded', 'excluded_auto'] }[f.stage] || [f.stage];
      sql.push(`${STATUS_SQL} IN (${want.map(() => '?').join(', ')})`); args.push(idleCutoff(), ...want);
    }
    if (f.stage === 'synthetic') sql.push(SYN_SQL);
    if (f.stage === 'real') sql.push('NOT ' + SYN_SQL);
    for (const col of ['grp', 'source', 'stage', 'cond']) if (f[col] && !(col === 'stage' && (ACTIVITY.includes(f[col]) || ANALYSIS.includes(f[col])))) { sql.push(col + ' = ?'); args.push(f[col]); }
    if (f.neuro === 'audhd') sql.push("(' ' || neuro || ' ') LIKE '% autistic %' AND (' ' || neuro || ' ') LIKE '% adhd %'");     // AuDHD: autistic and ADHD (store.py)
    else if (f.neuro) { sql.push("(' ' || neuro || ' ') LIKE ?"); args.push(`% ${f.neuro} %`); }
    if (f.q) { sql.push('pid LIKE ?'); args.push(`%${f.q}%`); }
    const ids = String(f.pids || '').split(/[\s,]+/).filter(Boolean).slice(0, 90);   // D1 takes at most 100 values a query
    if (ids.length) { sql.push(`pid IN (${ids.map(() => '?').join(', ')})`); args.push(...ids); }
    if (f.since) { sql.push('started >= ?'); args.push(f.since); }
    if (f.until) { sql.push('started < ?'); args.push(f.until + 'T99'); }
    return [sql.length ? ' WHERE ' + sql.join(' AND ') : '', args];
  }

  async query(f, sort = 'started', desc = true, limit = 100, offset = 0, grouped = false, thumbs = false) {
    // grouped (the Sessions tab): analysed first, then in progress now, then the rest (listgroup 0 / 1 / 2; as store.py)
    const [w, a] = Store.where(f);
    sort = SORTABLE.includes(sort) ? sort : 'started';
    const cut = idleCutoff();
    const [total, rows] = await this.db.batch([
      this.db.prepare(`SELECT COUNT(*) AS n, SUM(stage = 'done') AS done, SUM(${LIST_GROUP_SQL} = 2) AS folded FROM sessions${w}`).bind(cut, ...a),
      this.db.prepare(`SELECT *, ${INCL_SQL} AS inclusion, ${ANALYSIS_SQL} AS analysis, ${AUTO_IN_SQL} AS auto_in, ${FINISHED_SQL} AS pz_finished, ${LIST_GROUP_SQL} AS listgroup, `
        + `${STATUS_SQL} AS status, ${CLIENT_SQL}`
        + (thumbs ? ", (SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = 'pz_final') AS pz_final_pic, "
          + "(SELECT value FROM fields WHERE fields.pid = sessions.pid AND name = 'pz_summary') AS pz_summary_pic" : '')
        + ` FROM sessions${w} ORDER BY ${grouped ? 'listgroup, ' : ''}${sort} ${desc ? 'DESC' : 'ASC'}, pid LIMIT ? OFFSET ?`).bind(cut, cut, ...a, limit, offset),
    ]);
    return { rows: rows.results, total: total.results[0].n, done: total.results[0].done || 0, folded: total.results[0].folded || 0 };
  }

  async setInclusion(pid, value, study = null) {
    // the researcher's choice for a session: 'include', 'exclude' or 'auto'; study: only a session of this study (a
    // study researcher's scope). False when there is no such session.
    const row = await this.db.prepare('SELECT study FROM sessions WHERE pid = ?').bind(pid).first();
    if (!row || (study !== null && row.study !== study) || !INCLUSION_VALUES.includes(value)) return false;
    await this.db.prepare('INSERT INTO fields (pid, name, value, updated) VALUES (?, ?, ?, ?) '
      + 'ON CONFLICT(pid, name) DO UPDATE SET value = excluded.value, updated = excluded.updated').bind(pid, 'inclusion', value, now()).run();
    return true;
  }

  async distinct(col, study = null) {
    const [w, a] = Store.where({ study });
    const { results } = await this.db.prepare(`SELECT DISTINCT ${col} AS v FROM sessions${w} ORDER BY 1`).bind(...a).all();
    return results.map((r) => r.v).filter((v) => v !== '' && v !== null);
  }

  async lastStarted(study) {
    const [w, a] = Store.where({ study });
    return (await this.db.prepare(`SELECT MAX(started) AS t FROM sessions${w} ${w ? 'AND' : 'WHERE'} NOT ${SYN_SQL}`).bind(...a).first()).t;   // real sessions
  }

  async medianSeconds(study) {
    // median time taken by the finished sessions of a study (null = all)
    const [w, a] = Store.where({ study, stage: 'done' });
    const v = (await this.db.prepare(`SELECT seconds FROM sessions${w} AND seconds IS NOT NULL AND NOT ${SYN_SQL} ORDER BY seconds`).bind(...a).all()).results.map((x) => x.seconds);
    if (!v.length) return null;
    return v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2;
  }

  async countsByStudy() {
    // {study: {n, done, syn, status: {status: count}}}: the real sessions' statuses add up to n (as store.py)
    const empty = () => ({ n: 0, done: 0, syn: 0, status: Object.fromEntries(STATUSES.map((k) => [k, 0])) });
    const [byStatus, syn] = await this.db.batch([
      this.db.prepare(`SELECT study, ${STATUS_SQL} AS status, COUNT(*) AS n, SUM(stage = 'done') AS done FROM sessions WHERE NOT ${SYN_SQL} GROUP BY study, status`).bind(idleCutoff()),
      this.db.prepare(`SELECT study, COUNT(*) AS n FROM sessions WHERE ${SYN_SQL} GROUP BY study`),
    ]);
    const out = {};
    for (const r of byStatus.results) {
      const c = (out[r.study] = out[r.study] || empty());
      c.n += r.n; c.done += r.done || 0; c.status[r.status] = r.n;
    }
    for (const r of syn.results) (out[r.study] = out[r.study] || empty()).syn = r.n;
    return out;
  }

  async syncSynthetic(study, add, keep, version) {
    // the reports job (tools/cloud_sync.py) makes a test study hold exactly SYN-001 … SYN-keep: it sends the missing
    // ones (generated by analysis/synthetic.py) and this removes those above keep
    const cols = ['pid', 'study', 'grp', 'source', 'invite', 'cond', 'stage', 'started', 'updated', 'finished', 'seconds', 'restarts', 'consent', 'n_pieces', 'neuro'];
    const ins = this.db.prepare(`INSERT OR IGNORE INTO sessions (${cols.join(', ')}) VALUES (${cols.map(() => '?').join(', ')})`);
    const fld = this.db.prepare('INSERT OR REPLACE INTO fields (pid, name, value, updated) VALUES (?, ?, ?, ?)');
    const stmts = [];
    for (const x of add) {
      if (!/^SYN-\d{3,4}$/.test(x.pid || '')) continue;      // only synthetic ids, only into this study
      stmts.push(ins.bind(...cols.map((c) => (c === 'study' ? study : x[c] === undefined ? null : x[c]))));
      for (const [k, v] of Object.entries(x.fields || {})) if (FIELD_RE.test(k) && typeof v === 'string') stmts.push(fld.bind(x.pid, k, v, x.updated || now()));
    }
    const above = `study = ? AND ${SYN_SQL} AND CAST(substr(pid, 5) AS INTEGER) > ?`;
    stmts.push(this.db.prepare(`DELETE FROM fields WHERE pid IN (SELECT pid FROM sessions WHERE ${above})`).bind(study, keep));
    stmts.push(this.db.prepare(`DELETE FROM sessions WHERE ${above}`).bind(study, keep));
    if (version) stmts.push(this.db.prepare('INSERT OR REPLACE INTO meta VALUES (?, ?)').bind('synthetic_version:' + study, String(version)));
    await this.db.batch(stmts);
    return (await this.db.prepare(`SELECT COUNT(*) AS n FROM sessions WHERE study = ? AND ${SYN_SQL}`).bind(study).first()).n;
  }

  async signatures() {
    // count|newest update, for everything ('all'), the main study ('main') and each study: the reports are rebuilt
    // when one changes
    // (a researcher's inclusion choice on the Sessions tab counts as an update, as in store.py)
    const { results } = await this.db.prepare('SELECT s.study AS study, COUNT(*) AS n, MAX(MAX(s.updated), COALESCE(MAX(f.updated), \'\')) AS u FROM sessions s '
      + "LEFT JOIN fields f ON f.pid = s.pid AND f.name = 'inclusion' GROUP BY s.study").all();
    const out = {};
    let n = 0, u = '';
    for (const r of results) {
      out[r.study || 'main'] = `${r.n}|${r.u || ''}`;
      n += r.n;
      if ((r.u || '') > u) u = r.u;
    }
    // a new choice of how many synthetic sessions a test study holds counts as an update too (until the job syncs them)
    const { results: syn } = await this.db.prepare("SELECT k, v FROM meta WHERE k LIKE 'synthetic_at:%'").all();
    for (const r of syn) {
      const sid = r.k.slice(13) || 'main';
      if (out[sid] !== undefined && r.v > out[sid].split('|')[1]) out[sid] = out[sid].split('|')[0] + '|' + r.v;
      if (r.v > u) u = r.v;
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

  async settingsAll() {
    // the Settings tab's changes: {'*': {...}, <study id>: {...}} (meta keys settings:<scope>)
    const { results } = await this.db.prepare("SELECT k, v FROM meta WHERE k LIKE 'settings:%'").all();
    const out = {};
    for (const r of results || []) { try { const v = JSON.parse(r.v); if (v && typeof v === 'object' && !Array.isArray(v)) out[r.k.slice(9)] = v; } catch (e) { /* skip a broken value */ } }
    return out;
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
