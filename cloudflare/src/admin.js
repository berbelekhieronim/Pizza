// The researcher page's data on Cloudflare: /admin/api/state, the same shape as Handler.state() in server/server.py.
// The page itself is server/admin.html, shared by both servers.
import { loadStudy, studies, scopeName } from './config.js';

export const ALL_KEY = '*';               // study_keys row of the researcher link for all studies
const STAGE_NAMES = { intro: 'reading the intro', practice: 'practice', build: 'building', typical: 'typical pizza', followup: 'questions', done: 'finished' };
const NEURO_NAMES = { autistic: 'Autistic', adhd: 'ADHD', dys: 'Dyslexic etc.', otherND: 'Other ND', none: 'None', pnts: 'Prefer not to say' };

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

async function buildStatus(st, token) {
  // the reports job as the researcher page shows it: running / done / failed with its log, and a pending request
  let status = null;
  try { status = JSON.parse((await st.meta('reports_status')) || 'null'); } catch (e) { status = null; }
  if (status && status.state === 'running' && Date.now() - Date.parse(status.updated) > 30 * 60 * 1000) status.state = 'failed';   // silent for 30 min
  const last = (await st.db.prepare('SELECT MAX(updated) AS u FROM sessions').first()).u;
  const built = await st.meta('reports_built_upto');
  const pending = !!last && (!built || last > built);
  return { status, wanted: await st.meta('reports_wanted'), instant: token, pending, last_save: last,
    due: last ? new Date(Date.parse(last) + 5 * 60000).toISOString() : null };
}

export async function adminState(r, scope, f) {
  const st = r.store;
  const own = scope[0] === 'owner';
  const ids = scope[0] === 'study' ? [scope[1]] : [''].concat(studies());
  const counts = await st.countsByStudy();
  const out = [];
  for (const sid of ids) {
    const cfg = loadStudy(sid);
    const invs = await st.invites(sid);
    const [n, done] = counts[sid] || [0, 0];
    const row = {
      id: sid || 'main', title: cfg.title || '', description: cfg.description || (sid ? '' : 'The main study'), n, done,
      last: await st.lastStarted(sid), median_seconds: await st.medianSeconds(sid),
      invites: [invs.length, invs.filter((i) => i.stage).length, invs.filter((i) => i.stage === 'done').length],
      links: openLinks(r, sid), nutrition_reveal: !!cfg.nutrition_reveal, nutrition_panel: !!cfg.nutrition_panel,
    };
    if (own) row.researcher_link = r.base() + '/admin?' + new URLSearchParams({ key: await st.studyKey(sid) });
    out.push(row);
  }
  const sel = f.study === null && !r.arg('study') ? null : (f.study === null ? 'all' : f.study || 'main');
  let reports = null;
  if (sel) {
    const sigs = await st.signatures();
    const info = await r.builtInfo(scopeName(f));
    if (info) reports = { when: info.when, n: info.n, fresh: info.sig === sigs[scopeName(f)] };
  }
  let storage = null;
  if (own) {
    const u = await r.storageInfo();
    const gb = (b) => (b / 1e9).toFixed(b < 1e8 ? 3 : 2) + ' GB';
    storage = `Storage for reports and downloads: ${gb(u.used)} of the ${gb(u.limits.bytes)} cap (Cloudflare R2 is free up to 10 GB). This month `
      + `${u.writes.toLocaleString('en')} of ${u.limits.writes.toLocaleString('en')} writes and ${u.reads.toLocaleString('en')} of ${u.limits.reads.toLocaleString('en')} reads. `
      + `Database ${gb(u.db)} of ${gb(u.limits.db)}; at that size new participants are turned away.`;
  }
  const options = {};
  for (const c of ['grp', 'source', 'cond']) options[c] = await st.distinct(c, f.study);
  return {
    server: 'cloudflare', scope: scope[0], scope_study: scope[0] === 'study' ? (scope[1] || 'main') : null,
    study: sel, studies: out,
    all: { n: out.reduce((a, s) => a + s.n, 0), done: out.reduce((a, s) => a + s.done, 0),
      last: out.map((s) => s.last).filter(Boolean).sort().pop() || null, median_seconds: await st.medianSeconds(null) },
    global_link: own ? r.base() + '/admin?' + new URLSearchParams({ key: await st.studyKey(ALL_KEY) }) : null,
    reports, reports_build_on_open: false, options,
    build: await buildStatus(st, !!(r.env.GITHUB_TOKEN && r.env.GITHUB_REPO)), stages: STAGE_NAMES, neuro: NEURO_NAMES, storage, msg: r.arg('msg'),
  };
}
