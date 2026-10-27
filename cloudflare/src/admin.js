// The researcher page on Cloudflare: the same page as server/server.py's admin_page (session browser, reports,
// exports, studies and links), except that reports and downloads come per study from the GitHub reports job.
import { SORTABLE, STAGES } from './store.js';
import { loadStudy, studies, scopeName } from './config.js';

const STAGE_NAMES = { intro: 'reading the intro', practice: 'practice', build: 'building', typical: 'typical pizza', followup: 'questions', done: 'finished' };
const NEURO_NAMES = { autistic: 'Autistic', adhd: 'ADHD', dys: 'Dyslexic etc.', otherND: 'Other ND', none: 'None', pnts: 'Prefer not to say' };
const COLUMNS = [['pid', 'Participant'], ['study', 'Study'], ['grp', 'Group'], ['source', 'Source'], ['neuro', 'Says they are'], ['cond', 'Condition'],
  ['stage', 'Where'], ['n_pieces', 'Pieces'], ['started', 'Started (UTC)'], ['seconds', 'Time taken'], ['restarts', 'Restarts']];
const PAGE = 100;
const REPORTS = [['dashboard.html', 'Dashboard'], ['explore.html', 'Explore patterns'], ['profiles.html', 'Profiles and clusters'], ['arrangement.html', 'Symmetry and contact']];
const TABLES = ['participants.csv', 'ingredients_long.csv', 'pieces_long.csv', 'removals_long.csv', 'adjustments_long.csv', 'profiles.csv', 'explore.csv', 'events_long.csv'];

export function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}

export function describe(f) {
  const parts = [];
  if (f.study !== null && f.study !== undefined) parts.push('study ' + (f.study || 'main'));
  const names = { grp: 'group', source: 'source', stage: 'where', neuro: 'says they are', cond: 'condition', q: 'id contains', since: 'from', until: 'to' };
  for (const k of Object.keys(names)) if (f[k]) parts.push(names[k] + ' ' + (k === 'stage' ? STAGE_NAMES[f[k]] || f[k] : f[k]));
  return parts.join(', ');
}

export function deniedPage() {
  return '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Pizza Study Admin</title>'
    + '<body style="font:16px system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px"><h1>Researcher page</h1>'
    + '<p>This page needs a researcher link, which ends in <code>/admin?key=...</code>. The study owner has theirs (it is the '
    + '<code>PIZZA_ADMIN_KEY</code> secret of the GitHub repository) and can give each study\'s researchers a link for that study.</p></body>';
}

export function withBar(r, page, f, scope) {
  const d = describe(f);
  const bar = '<div style="position:sticky;top:0;z-index:50;background:#2a2421;color:#fff;font:14px system-ui,sans-serif;padding:8px 16px">'
    + `<a href="/admin?${esc(r.qs(f, {}, scope[0] === 'owner'))}" style="color:#fff">&larr; Researcher page</a>${d ? ' · ' + esc(d) : ''}</div>`;
  return page.replace(/(<body[^>]*>)/, (m) => m + bar);
}

function openLinks(r, sid) {
  const base = r.base() + '/';
  const cfg = loadStudy(sid);
  const q = sid ? { study: sid } : {};
  const enc = (o) => new URLSearchParams(o).toString();
  return [['Anyone', base + (sid ? '?' + enc(q) : '')]].concat((cfg.groups || []).map((g) => ['Group ' + g, base + '?' + enc({ ...q, group: g })]));
}

function linkRows(items) {
  return items.map(([label, url]) => `<span class="ll">${esc(label)}</span><input readonly value="${esc(url)}" aria-label="${esc(label)}">`
    + '<button type="button" class="copy alt">Copy</button>').join('');
}

async function studiesCard(r, scope, f) {
  const st = r.store;
  const owner = scope[0] === 'owner';
  const ids = owner ? [''].concat(studies()) : [scope[1]];
  const counts = await st.countsByStudy();
  const keys = owner ? await st.studyKeys(ids) : {};
  const trs = [], opts = [];
  for (const sid of ids) {
    const cfg = loadStudy(sid);
    const invs = await st.invites(sid);
    const opened = invs.filter((i) => i.stage).length, fin = invs.filter((i) => i.stage === 'done').length;
    const [n, done] = counts[sid] || [0, 0];
    const items = openLinks(r, sid);
    if (owner) items.push(['Researcher link (this study only)', r.base() + '/admin?' + new URLSearchParams({ key: keys[sid] })]);
    const reset = owner ? `<form method="post" action="/admin/study-key?${esc(r.qs(f))}" onsubmit="return confirm('Make a new researcher link for this study? The old one will stop working.')">`
      + `<input type="hidden" name="study" value="${esc(sid || 'main')}"><button class="alt small" type="submit">New researcher link</button></form>` : '';
    const show = owner ? r.qs({ ...f, study: sid }) : r.qs(f, {}, false);
    trs.push(`<tr class="st"><td><b>${esc(sid || 'main')}</b><br><span class="muted">${esc(cfg.description || cfg.title || '')}</span></td><td>${n}</td><td>${done}</td>`
      + `<td>${invs.length} / ${opened} / ${fin}</td><td><a href="/admin?${esc(show)}">Show only this study</a><br>`
      + `<a href="/admin/invites.csv?${esc(owner ? r.qs({ study: sid }) : r.qs(f, {}, false))}">Personal links (.csv)</a>${reset}</td></tr>`
      + `<tr class="links"><td colspan="5"><div class="lgrid">${linkRows(items)}</div></td></tr>`);
    opts.push(`<option value="${esc(sid || 'main')}"${f.study === sid ? ' selected' : ''}>${esc(sid || 'main')}</option>`);
  }
  const form = `<form method="post" action="/admin/invites?${esc(r.qs(f, {}, owner))}" class="row" style="align-items:end">`
    + `<label>Study<br><select name="study">${opts.join('')}</select></label>`
    + '<label>Group<br><input name="group" size="8" placeholder="e.g. ASD"></label>'
    + '<label>Recruitment source<br><input name="source" size="22" placeholder="e.g. autism charity newsletter"></label>'
    + '<label>Note<br><input name="note" size="14" placeholder="optional"></label>'
    + '<label>How many<br><input name="count" type="number" min="1" max="500" value="10" style="width:5em"></label>'
    + '<button type="submit">Make personal links</button></form>';
  return `<div class="card"><h2>${owner ? 'Studies and links' : 'Links'}</h2><table class="studies"><tr><th>Study</th><th>Sessions</th><th>Finished</th>`
    + '<th>Personal links<br><span class="muted">made / opened / finished</span></th><th></th></tr>' + trs.join('') + '</table>'
    + '<h2 style="margin-top:14px">Make personal links</h2>' + form + '<p class="muted">One link per participant: it records study, group '
    + 'and source, and resumes their session if opened again. The .csv lists the links and who has opened or finished. Open links '
    + '(above) can be posted anywhere.'
    + (owner ? ' Studies are set up in <code>server/study.json</code> → <code>"studies"</code> (deployed on every push); give each study\'s researchers its own '
      + 'researcher link: it sees, analyses and exports that study only.' : '') + '</p></div>';
}

async function filterForm(r, scope, f, sort, desc) {
  const st = r.store;
  const owner = scope[0] === 'owner';
  const sel = (name, label, values, cur, names = {}) => `<label>${label}<br><select name="${name}"><option value="">any</option>`
    + values.map((v) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(names[v] || v)}</option>`).join('') + '</select></label>';
  let studySel = '';
  if (owner) {
    const cur = f.study === null ? 'all' : (f.study || 'main');
    const ids = [...new Set(studies().concat((await st.distinct('study')).filter(Boolean)))].sort();
    const vals = [['all', 'all studies'], ['main', 'main']].concat(ids.map((s) => [s, s]));
    studySel = '<label>Study<br><select name="study">' + vals.map(([v, l]) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(l)}</option>`).join('') + '</select></label>';
  }
  const ss = owner ? null : f.study;
  return `<form method="get" action="/admin" class="filters"><input type="hidden" name="key" value="${esc(r.arg('key'))}">`
    + `<input type="hidden" name="sort" value="${esc(sort)}"><input type="hidden" name="dir" value="${desc ? 'desc' : 'asc'}">${studySel}`
    + sel('grp', 'Group', await st.distinct('grp', ss), f.grp) + sel('source', 'Source', await st.distinct('source', ss), f.source)
    + sel('stage', 'Where', STAGES, f.stage, STAGE_NAMES) + sel('neuro', 'Says they are', Object.keys(NEURO_NAMES), f.neuro, NEURO_NAMES)
    + sel('cond', 'Condition', await st.distinct('cond', ss), f.cond)
    + `<label>Started from<br><input type="date" name="since" value="${esc(f.since)}"></label><label>to<br><input type="date" name="until" value="${esc(f.until)}"></label>`
    + `<label>Participant id<br><input name="q" size="10" value="${esc(f.q)}"></label>`
    + `<button type="submit">Show</button><a class="btn alt" href="/admin?${esc(r.qs({}, {}, owner))}">Clear</a></form>`;
}

export async function adminPage(r, scope, f, message = '') {
  const st = r.store;
  const owner = scope[0] === 'owner';
  let sort = r.arg('sort', 'started');
  sort = SORTABLE.includes(sort) ? sort : 'started';
  const desc = r.arg('dir', 'desc') !== 'asc';
  const page = Math.max(1, parseInt(r.arg('page', '1'), 10) || 1);
  const { rows, total, done } = await st.query(f, sort, desc, PAGE, (page - 1) * PAGE);
  const q = esc(r.qs(f, {}, owner));
  const sc = scopeName(f);
  const info = await r.builtInfo(sc);
  const sigs = await st.signatures();
  const scopeLabel = sc === 'all' ? 'all studies' : 'study ' + sc;
  const others = describe({ ...f, study: null });
  let status = info ? `Last built ${esc((info.when || '').replace('T', ' ').slice(0, 16))} UTC from ${info.n} pizza${info.n === 1 ? '' : 's'}`
    + (info.sig !== sigs[sc] ? '; newer sessions have arrived since, and the reports are rebuilt a few minutes after a session finishes.' : ', up to date.')
    : 'Not built yet for these sessions: the GitHub job builds them a few minutes after the first session finishes.';
  status = `Reports and downloads cover ${esc(scopeLabel)}${others ? ' (the other filters apply to the session list and its .csv)' : ''}. ` + status;
  const reportBtns = REPORTS.map(([fn, label]) => `<a class="btn" href="/admin/reports/${fn}?${q}">${label}</a>`).join('')
    + `<a class="btn alt" href="/admin/methods?${q}">Methods: how each number is counted</a>`;
  const tableLinks = TABLES.map((t) => `<a href="/admin/reports/${t}?${q}">${t}</a>`).join(' · ');
  const th = (col, label) => `<th><a class="sort" href="/admin?${esc(r.qs(f, { sort: col, dir: col === sort && desc ? 'asc' : 'desc' }, owner))}">${label}${col === sort ? (desc ? ' ▼' : ' ▲') : ''}</a></th>`;
  const cell = (row, c) => {
    const v = row[c];
    if (c === 'study') return esc(v || 'main');
    if (c === 'stage') return esc(STAGE_NAMES[v] || v);
    if (c === 'neuro') return esc((v || '').split(' ').filter(Boolean).map((x) => NEURO_NAMES[x] || x).join(', '));
    if (c === 'started') return esc((v || '').replace('T', ' ').slice(0, 16));
    if (c === 'seconds') return v === null || v === undefined ? '' : (v / 60).toFixed(1) + ' min';
    return v === null || v === undefined || v === '' ? '' : esc(v);
  };
  const trs = rows.map((row) => '<tr>' + COLUMNS.map(([c]) => `<td>${cell(row, c)}</td>`).join('') + '</tr>').join('');
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const dir = desc ? 'desc' : 'asc';
  const pager = pages > 1 ? '<div class="row">'
    + (page > 1 ? `<a class="btn alt" href="/admin?${esc(r.qs(f, { sort, dir, page: page - 1 }, owner))}">&larr; newer</a>` : '')
    + `<span class="muted">page ${page} of ${pages}</span>`
    + (page < pages ? `<a class="btn alt" href="/admin?${esc(r.qs(f, { sort, dir, page: page + 1 }, owner))}">older &rarr;</a>` : '') + '</div>' : '';
  const exports = `<div class="row"><a class="btn" href="/admin/r.zip?${q}">Download for R (.zip)</a>`
    + `<a class="btn alt" href="/admin/sessions.csv?${esc(r.qs(f, { sort, dir }, owner))}">Session list (.csv)</a>`
    + `<a class="btn alt" href="/admin/data.zip?${q}">Raw sessions (.zip)</a>`
    + `<a class="btn alt" href="/admin/database.sqlite?${q}">Database (.sqlite)</a></div>`;
  const note = message ? `<pre class="note">${esc(message)}</pre>` : '';
  const who = owner ? 'Owner: all studies' : `Researcher page for study <b>${esc(scope[1] || 'main')}</b>`;
  const flt = describe(f);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pizza Study Admin</title><style>
:root{--bg:#f6f2ed;--fg:#2a2421;--muted:#6e635b;--line:#dcd2c7;--panel:#fff;--accent:#a8361d;--accent-ink:#fff}
@media (prefers-color-scheme: dark){:root{--bg:#1d1916;--fg:#eee6de;--muted:#b0a398;--line:#3a322c;--panel:#26211d;--accent:#e0765b;--accent-ink:#1d1916;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px}h1{font-size:1.4rem;margin:0 0 4px}.muted{color:var(--muted)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:12px 0;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:top}
th a.sort{color:var(--fg);text-decoration:none}th a.sort:hover{text-decoration:underline}
h2{font-size:1.05rem;margin:0 0 8px}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}label{font-size:.85rem;color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;gap:8px 10px;align-items:end}
input,select{font:inherit;padding:6px 8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg)}
button,.btn{font:inherit;padding:8px 14px;border-radius:9px;border:1px solid var(--accent);background:var(--accent);color:var(--accent-ink);cursor:pointer;text-decoration:none;display:inline-block}
.btn.alt,button.alt{background:transparent;color:var(--fg);border-color:var(--line)}a{color:var(--accent)}button.small{padding:3px 10px;font-size:.85rem;margin-top:4px}
.studies tr.st td{border-bottom:0;padding-bottom:2px}.studies tr.links td{padding-top:2px}
.lgrid{display:grid;grid-template-columns:max-content minmax(0,1fr) max-content;gap:4px 8px;align-items:center;max-width:900px}
.lgrid .ll{color:var(--muted);font-size:.85rem}.lgrid input{width:100%;box-sizing:border-box;font-size:.85rem;padding:5px 8px}.lgrid button{padding:4px 12px}
.note{white-space:pre-wrap;font:13px/1.4 ui-monospace,Menlo,Consolas,monospace;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:8px 0 0}
</style></head><body><div class="wrap"><h1>Pizza study</h1><p class="muted">${who}</p>${note}
<div class="card"><h2>Sessions</h2>${await filterForm(r, scope, f, sort, desc)}
<p style="margin:10px 0 4px"><b>${total} session${total === 1 ? '' : 's'} match</b>, ${done} finished${flt ? ` (${esc(flt)})` : ''}.</p>${exports}
<table><tr>${COLUMNS.map(([c, l]) => th(c, l)).join('')}</tr>${trs || `<tr><td colspan="${COLUMNS.length}" class="muted">No sessions match.</td></tr>`}</table>${pager}</div>
<div class="card"><h2>Reports for these sessions</h2><div class="row">${reportBtns}</div><p class="muted" style="margin:4px 0">Tables: ${tableLinks}</p>
<p class="muted" style="margin:4px 0">${status}</p>
<form method="post" action="/admin/reports?${q}" style="margin:0"><button class="alt" type="submit">Rebuild now</button></form></div>
${await studiesCard(r, scope, f)}
</div><script>
document.querySelectorAll('.copy').forEach(function (b) {
  b.onclick = function () {
    var i = b.previousElementSibling; i.select();
    function ok() { b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1500); }
    if (navigator.clipboard) navigator.clipboard.writeText(i.value).then(ok, function () { document.execCommand('copy'); ok(); }); else { document.execCommand('copy'); ok(); }
  };
});
</script></body></html>`;
}
