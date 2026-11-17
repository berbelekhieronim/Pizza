// The study settings a researcher changes on the researcher page (Settings tab), as overrides of server/study.json.
// The same checker as server/settings.py (keep them in step). Layers, later ones win: study.json's main settings, the
// global changes, the study's own settings in study.json, the study's changes. Each condition of a between-subjects
// study can set its own nutrition table and questions (condition_settings).
export const EDITABLE = ['nutrition', 'survey_when', 'followup', 'survey', 'conditions', 'condition_settings'];
export const COND_KEYS = ['nutrition', 'survey_when', 'followup', 'survey'];
export const CHOICES = { nutrition: ['visible', 'hidden', 'none'], survey_when: ['before', 'after'], followup: ['strong', 'ratings', 'metryczka'] };
const BUILTIN_QUESTIONS = ['age', 'autism', 'adhd', 'gender', 'trans', 'diet'];
const QUESTION_KEYS = ['id', 'type', 'text', 'options', 'other', 'min', 'max', 'required', 'placeholder', 'explore'];
const EXPLORE_KEYS = ['title', 'why', 'measures', 'direction', 'answer'];
const COND_RE = /^[A-Za-z0-9_-]{1,20}$/;
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

function wording(v) {
  if (typeof v === 'string') return v.length <= 600;
  return isObj(v) && Object.keys(v).length > 0 && Object.entries(v).every(([k, t]) => (k === 'pl' || k === 'en') && typeof t === 'string' && t.length <= 600);
}

export function surveyProblems(survey) {
  if (!Array.isArray(survey) || !survey.length) return ['the questions must be a list with at least one question'];
  if (survey.length > 30) return ['at most 30 questions'];
  const out = [], seen = new Set();
  survey.forEach((q, i) => {
    const qid = isObj(q) ? q.id : null;
    if (typeof qid !== 'string' || !/^[a-z][a-z0-9_]{0,30}$/.test(qid)) { out.push(`question ${i + 1}: "id" must be lower-case letters, digits or _ (it names the data column q_<id>)`); return; }
    if (Object.keys(q).some((k) => !QUESTION_KEYS.includes(k))) out.push(`${qid}: unknown key (use ${QUESTION_KEYS.join(', ')})`);
    if (seen.has(qid)) out.push(`${qid}: the id is used twice`);
    seen.add(qid);
    const kind = q.type;
    if (!['number', 'single', 'multi', 'text'].includes(kind)) out.push(`${qid}: "type" must be number, single, multi or text`);
    if (q.text != null && !wording(q.text)) out.push(`${qid}: "text" must be the wording, or {"pl": ..., "en": ...}`);
    if (!BUILTIN_QUESTIONS.includes(qid) && !q.text) out.push(`${qid}: needs its wording ("text")`);
    const opts = q.options;
    if (opts != null && (!Array.isArray(opts) || opts.some((o) => !(Array.isArray(o) && o.length === 2 && wording(o[1]))))) { out.push(`${qid}: "options" must be [[code, label], ...]`); return; }
    if ((kind === 'single' || kind === 'multi') && !BUILTIN_QUESTIONS.includes(qid) && !(opts && opts.length)) out.push(`${qid}: needs "options": [[code, label], ...]`);
    const codes = (opts || []).map((o) => String(o[0]));
    if (codes.some((c) => !/^[a-z0-9_]{1,30}$/.test(c))) out.push(`${qid}: answer codes must be lower-case letters, digits or _`);
    if (new Set(codes).size !== codes.length) out.push(`${qid}: an answer code is used twice`);
    if (q.other && codes.length && !codes.includes(q.other)) out.push(`${qid}: "other" must be one of its answer codes`);
    for (const k of ['min', 'max']) if (q[k] != null && !isNum(q[k])) out.push(`${qid}: "${k}" must be a number`);
    if (kind === 'number' && isNum(q.min) && isNum(q.max) && q.min > q.max) out.push(`${qid}: min is above max`);
    if (q.required != null && typeof q.required !== 'boolean') out.push(`${qid}: "required" must be true or false`);
    const ex = q.explore;
    if (ex != null) {
      const str = (k) => ex[k] === undefined || (typeof ex[k] === 'string' && ex[k].length <= 300);
      const ok = isObj(ex) && Object.keys(ex).every((k) => EXPLORE_KEYS.includes(k)) && Array.isArray(ex.measures) && ex.measures.length >= 1 && ex.measures.length <= 8
        && ex.measures.every((m) => typeof m === 'string' && /^[a-z][a-z0-9_]{0,40}$/.test(m))
        && ['higher', 'lower', 'either'].includes(ex.direction === undefined ? 'either' : ex.direction) && str('title') && str('why') && str('answer');
      if (!ok) out.push(`${qid}: "explore" must be {"measures": [up to 8 column names], "direction": "higher" / "lower" / "either", "answer": an answer code (optional), "title", "why" (optional)}`);
      else if (ex.answer && codes.length && !codes.includes(ex.answer)) out.push(`${qid}: "explore" answer must be one of its answer codes`);
    }
  });
  return out;
}

export function problems(ov, conditions = []) {
  if (!isObj(ov)) return ['the settings must be an object'];
  let out = [];
  for (const [k, v] of Object.entries(ov)) {
    if (!EDITABLE.includes(k)) out.push(`${k}: not a setting that can be changed here`);
    else if (v === null) continue;
    else if (CHOICES[k] && !CHOICES[k].includes(v)) out.push(`${k}: must be one of ${CHOICES[k].join(', ')}`);
    else if (k === 'survey') out = out.concat(surveyProblems(v).map((p) => 'questions: ' + p));
    else if (k === 'conditions' && (!Array.isArray(v) || v.length > 8 || v.some((c) => typeof c !== 'string' || !COND_RE.test(c)) || new Set(v).size !== v.length)) {
      out.push('conditions: up to 8 different names of letters, digits, - or _ (at most 20 characters)');
    }
  }
  const cs = ov.condition_settings;
  if (cs != null) {
    const conds = Array.isArray(ov.conditions) ? ov.conditions : (conditions || []);
    if (!isObj(cs)) out.push('condition_settings: must be {condition: {setting: value}}');
    else for (const [c, sub] of Object.entries(cs)) {
      if (!conds.includes(c)) out.push(`condition_settings: ${c} is not one of the conditions`);
      else if (!isObj(sub) || Object.keys(sub).some((x) => !COND_KEYS.includes(x))) out.push(`condition_settings.${c}: only ${COND_KEYS.join(', ')}`);
      else out = out.concat(problems(sub).map((p) => `condition ${c}: ${p}`));
    }
  }
  return out;
}

export function apply(cfg, ov) {
  if (!ov) return cfg;
  const out = { ...cfg };
  for (const [k, v] of Object.entries(ov)) if (EDITABLE.includes(k) && v !== null && v !== undefined) out[k] = v;
  return out;
}

export function nutritionMode(cfg) {
  if (CHOICES.nutrition.includes(cfg.nutrition)) return cfg.nutrition;
  if (cfg.nutrition_reveal) return 'hidden';
  return cfg.nutrition_panel ? 'visible' : 'none';
}
