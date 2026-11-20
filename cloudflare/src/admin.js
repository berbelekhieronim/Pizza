// The researcher page's data on Cloudflare: /admin/api/state, the same shape as Handler.state() in server/server.py.
// The page itself is server/admin.html, shared by both servers.
import { loadStudy, studies, scopeName, SYNTHETIC_CHOICES } from './config.js';
import { nutritionMode } from './settings.js';
import { STATUSES } from './store.js';
import { dbName } from './router.js';

export const ALL_KEY = '*';               // study_keys row of the researcher link for all studies
const STAGE_NAMES = { intro: 'reading the intro', survey: 'questions (before the pizza)', practice: 'practice', build: 'building', typical: 'typical pizza', followup: 'questions', done: 'finished', declined: 'declined consent' };
const NEURO_NAMES = { autistic: 'Autistic', adhd: 'ADHD', dys: 'Dyslexic etc.', otherND: 'Other ND', none: 'Non-spicy', pnts: 'Prefer not to say' };

export function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}

export function deniedPage() {
  return '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Pizza Study Admin</title>'
    + '<body style="font:16px system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px"><h1>Researcher page</h1>'
    + '<p>This page needs a researcher link, which ends in <code>/admin?key=...</code>. Ask the study owner for one: there is a link '
    + 'for all studies and one for each study.</p></body>';
}

export function notBuilt(message) {
  return '<!doctype html><meta charset="utf-8"><body style="font:15px system-ui,sans-serif;color:#6e635b;max-width:640px;margin:48px auto;padding:0 16px">'
    + `<p>${esc(message)}</p></body>`;
}

function openLinks(r, sid) {
  const base = r.base() + '/';
  const q = sid ? { study: sid } : {};
  const enc = (o) => new URLSearchParams(o).toString();
  return [['Anyone', base + (sid ? '?' + enc(q) : '')]].concat((loadStudy(sid).groups || []).map((g) => ['Group ' + g, base + '?' + enc({ ...q, group: g })]));
}

export async function syntheticN(st, sid) {
  // how many synthetic sessions a test study holds: the researcher's choice, else its study.json default (0 = none)
  const cfg = loadStudy(sid);
  if (!sid || !cfg.synthetic) return 0;
  const v = await st.meta('synthetic_n:' + sid);
  return v !== null && /^\d+$/.test(v) ? parseInt(v, 10) : cfg.synthetic;
}

async function buildStatus(st, token, autoReports) {
  // the reports job as the researcher page shows it: running / done / failed with its log, and a pending request
  let status = null;
  try { status = JSON.parse((await st.meta('reports_status')) || 'null'); } catch (e) { status = null; }
  if (status && status.state === 'running' && Date.now() - Date.parse(status.updated) > 30 * 60 * 1000) status.state = 'failed';   // silent for 30 min
  const last = await st.lastChange();            // every database's newest save (router.js)
  const built = await st.meta('reports_built_upto');
  const pending = !!last && (!built || last > built);
  return { status, wanted: await st.meta('reports_wanted'), instant: token, auto: token && autoReports, pending, last_save: last,
    due: last ? new Date(Date.parse(last) + 5 * 60000).toISOString() : null };
}

export async function adminState(r, scope, f) {
  const st = r.store;
  const own = scope[0] === 'owner';
  const ids = scope[0] === 'study' ? [scope[1]] : [''].concat(studies());
  // every study's numbers: one batch per database, however many studies (Cloudflare's free plan: 50 queries per request)
  const counts = await st.overview();
  const keys = own ? await st.keysFor(ids.concat([ALL_KEY])) : {};
  const synN = await st.syntheticChoices();
  const median = (v) => (v.length ? (v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2) : null);
  const out = [];
  for (const sid of ids) {
    const cfg = loadStudy(sid);
    const c = counts[sid] || { n: 0, done: 0, syn: 0, status: Object.fromEntries(STATUSES.map((k) => [k, 0])), last: null, seconds: [], inv: [0, 0, 0] };
    const stt = c.status, syn = c.syn;
    // status: one count per status, adding up to n (store.js STATUS_SQL); the other numbers are taken from it
    const row = {
      id: sid || 'main', title: cfg.title || '', description: cfg.description || (sid ? '' : 'The main study'), n: c.n, done: c.done, status: stt,
      built: stt.analysed, active: stt.active + stt.pending, declined: stt.declined, stopped: c.n - stt.analysed - stt.active - stt.pending - stt.declined,
      last: c.last, median_seconds: median(c.seconds), invites: c.inv,
      links: openLinks(r, sid), nutrition: nutritionMode(cfg), survey_when: cfg.survey_when || 'after', look: cfg.look || 'drawn', conditions: cfg.conditions || [],
      synthetic: sid && cfg.synthetic ? { n: synN[sid] !== undefined ? synN[sid] : cfg.synthetic, stored: syn, choices: SYNTHETIC_CHOICES } : null,
      database: dbName(sid),
    };
    if (own) row.researcher_link = r.base() + '/admin?' + new URLSearchParams({ key: keys[sid] });
    out.push(row);
  }
  const sel = f.study === null && !r.arg('study') ? null : (f.study === null ? 'all' : f.study || 'main');
  let reports = null;
  if (sel) {
    const sigs = await st.signatures();
    const info = await r.builtInfo(scopeName(f));
    // built with older analysis code than the deployed one (deploy.py sets ANALYSIS_CODE): out of date too
    const codeChanged = !!r.env.ANALYSIS_CODE && info && info.code !== r.env.ANALYSIS_CODE;
    if (info) reports = { when: info.when, n: info.n, check: info.check || null, fresh: info.sig === sigs[scopeName(f)] && !codeChanged, code_changed: codeChanged };
  }
  let storage = null;
  if (own) {
    const u = await r.storageInfo();
    const gb = (b) => (b / 1e9).toFixed(b < 1e8 ? 3 : 2) + ' GB';
    storage = `Storage for reports and downloads: ${gb(u.used)} of the ${gb(u.limits.bytes)} cap (Cloudflare R2 is free up to 10 GB). This month `
      + `${u.writes.toLocaleString('en')} of ${u.limits.writes.toLocaleString('en')} writes and ${u.reads.toLocaleString('en')} of ${u.limits.reads.toLocaleString('en')} reads. `
      + `Database ${gb(u.db)} of ${gb(u.limits.db)}; at that size new participants are turned away.`;
    // the databases against Cloudflare's free plan (10 databases, 500 MB each, 5 GB in all)
    const dbs = await st.databases();
    if (dbs.list.length > 1 || dbs.missing.length) {
      storage += ` Databases (free plan: up to 10, 500 MB each, 5 GB in all): ` + dbs.list.map((d) => `${d.name === 'DB' ? 'main' : d.name} ${gb(d.bytes)} (${d.studies.join(', ')})`).join('; ') + '.'
        + (dbs.missing.length ? ` Not deployed yet: ${dbs.missing.join(', ')} (run the cloudflare deploy; until then they take no new participants).` : '');
    }
  }
  const options = await st.options(f.study);
  return {
    server: 'cloudflare', scope: scope[0], scope_study: scope[0] === 'study' ? (scope[1] || 'main') : null,
    study: sel, studies: out, idle_minutes: 30,
    all: { n: out.reduce((a, s) => a + s.n, 0), done: out.reduce((a, s) => a + s.done, 0), built: out.reduce((a, s) => a + s.built, 0),
      active: out.reduce((a, s) => a + s.active, 0), stopped: out.reduce((a, s) => a + s.stopped, 0), declined: out.reduce((a, s) => a + (s.declined || 0), 0),
      status: Object.fromEntries(STATUSES.map((k) => [k, out.reduce((a, s) => a + (s.status[k] || 0), 0)])),
      last: out.map((s) => s.last).filter(Boolean).sort().pop() || null,
      median_seconds: median([].concat(...ids.map((sid) => (counts[sid] || { seconds: [] }).seconds)).sort((a, b) => a - b)) },
    global_link: own ? r.base() + '/admin?' + new URLSearchParams({ key: keys[ALL_KEY] }) : null,
    reports, reports_build_on_open: false, options,
    build: await buildStatus(st, !!((r.env.GITHUB_TOKEN || r.env.PIZZA_GITHUB_TOKEN || r.env.PIZZA_GITHUB_TOKEN_PIZZA) && r.env.GITHUB_REPO), r.env.REPORTS_AUTO === '1'), stages: STAGE_NAMES, neuro: NEURO_NAMES, storage, msg: r.arg('msg'),
  };
}
