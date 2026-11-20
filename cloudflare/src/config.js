// The study settings (server/study.json, bundled into the Worker at deploy time) and the names used by every route.
import STUDY from '../../server/study.json';
import { apply } from './settings.js';

export const STUDY_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;
export const STUDY_KEYS = ['title', 'intro', 'consent', 'completion_message', 'completion_redirect', 'typical_build', 'about_you', 'conditions', 'groups',
  'nutrition', 'nutrition_panel', 'nutrition_show', 'nutrition_base', 'nutrition_reveal', 'condition_settings', 'synthetic',
  // a study's own flow: language, consent with yes/no, the questions at the end, the base choices, the end page
  'lang', 'consent_choice', 'decline_message', 'followup', 'sauces', 'sauce', 'cheeses', 'cheese', 'bake_picture', 'show_code', 'completion_title', 'texts', 'survey', 'survey_when',
  'look'];
export const SYNTHETIC_CHOICES = [0, 25, 50, 100, 200, 500];   // synthetic pizzas a test study can hold (study.json "synthetic" = the default)
export const FILTER_KEYS = ['study', 'grp', 'source', 'stage', 'neuro', 'cond', 'q', 'since', 'until', 'pids'];   // pids: a list of ids (the reports' To review links)

// The Settings tab's changes ({'*': global, <study id>: that study's}), read from the database at the start of every
// request (setOverrides), so loadStudy stays synchronous
let OVERRIDES = {};
export function setOverrides(o) { OVERRIDES = o || {}; }
export function overrides(scope) { return OVERRIDES[scope] || {}; }

export function loadStudy(id = '', changes = true) {
  // study.json; with a study id, that study's settings ("studies": {id: {...}}) override the main ones. The Settings
  // tab's changes apply on top of each layer: the global ones on the main settings, the study's on its own.
  const own = id ? ((STUDY.studies || {})[id] || {}) : {};
  let cfg = changes ? apply({ ...STUDY }, overrides('*')) : { ...STUDY };
  for (const [k, v] of Object.entries(own)) if (STUDY_KEYS.includes(k) || k === 'description') cfg[k] = v;
  if (id && changes) cfg = apply(cfg, overrides(id));
  return cfg;
}

export function fileSettings() { return STUDY; }

export function studies() {
  // the ids of the studies in study.json (the main study, id '', is always there)
  return Object.keys(STUDY.studies || {}).filter((k) => STUDY_RE.test(k)).sort();
}

export function scopeName(f) {
  // which set of reports and exports a filter uses: 'all', 'main' or a study id
  return f.study === null || f.study === undefined ? 'all' : (f.study || 'main');
}
