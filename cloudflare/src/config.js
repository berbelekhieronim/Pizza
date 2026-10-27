// The study settings (server/study.json, bundled into the Worker at deploy time) and the names used by every route.
import STUDY from '../../server/study.json';

export const STUDY_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;
export const STUDY_KEYS = ['title', 'intro', 'consent', 'completion_message', 'completion_redirect', 'typical_build', 'about_you', 'conditions', 'groups',
  'nutrition_panel', 'nutrition_show', 'nutrition_base', 'nutrition_reveal', 'condition_settings', 'synthetic'];
export const SYNTHETIC_CHOICES = [0, 25, 50, 100, 200, 500];   // synthetic pizzas a test study can hold (study.json "synthetic" = the default)
export const FILTER_KEYS = ['study', 'grp', 'source', 'stage', 'neuro', 'cond', 'q', 'since', 'until'];

export function loadStudy(id = '') {
  // study.json; with a study id, that study's settings ("studies": {id: {...}}) override the main ones
  const own = id ? ((STUDY.studies || {})[id] || {}) : {};
  const cfg = { ...STUDY };
  for (const [k, v] of Object.entries(own)) if (STUDY_KEYS.includes(k) || k === 'description') cfg[k] = v;
  return cfg;
}

export function studies() {
  // the ids of the studies in study.json (the main study, id '', is always there)
  return Object.keys(STUDY.studies || {}).filter((k) => STUDY_RE.test(k)).sort();
}

export function scopeName(f) {
  // which set of reports and exports a filter uses: 'all', 'main' or a study id
  return f.study === null || f.study === undefined ? 'all' : (f.study || 'main');
}
