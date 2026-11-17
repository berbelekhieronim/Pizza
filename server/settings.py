"""The study settings a researcher changes on the researcher page (Settings tab), as overrides of server/study.json.

Layers, later ones win: study.json's main settings (every study's defaults), the global changes made on the Settings
tab, the study's own settings in study.json, the study's changes on the Settings tab. A between-subjects study lists
its conditions; each condition can set its own nutrition table and questions (condition_settings), assigned in turn
at the start of a session. cloudflare/src/settings.js is the same checker for the Worker (keep them in step).
"""
import re

EDITABLE = ('nutrition', 'survey_when', 'followup', 'survey', 'conditions', 'condition_settings')
COND_KEYS = ('nutrition', 'survey_when', 'followup', 'survey')
CHOICES = {'nutrition': ('visible', 'hidden', 'none'), 'survey_when': ('before', 'after'), 'followup': ('strong', 'ratings', 'metryczka')}
BUILTIN_QUESTIONS = ('age', 'autism', 'adhd', 'gender', 'trans', 'diet')     # their wording comes from the task's texts
QUESTION_KEYS = ('id', 'type', 'text', 'options', 'other', 'min', 'max', 'required', 'placeholder', 'explore')
EXPLORE_KEYS = ('title', 'why', 'measures', 'direction', 'answer')
COND_RE = re.compile(r'^[A-Za-z0-9_-]{1,20}$')


def _wording(v):
    if isinstance(v, str):
        return len(v) <= 600
    return isinstance(v, dict) and bool(v) and all(k in ('pl', 'en') and isinstance(t, str) and len(t) <= 600 for k, t in v.items())


def survey_problems(survey):
    """What is wrong with a list of questions; [] = all well (tools/texts.py checks study.json with the same rules)."""
    if not isinstance(survey, list) or not survey:
        return ['the questions must be a list with at least one question']
    if len(survey) > 30:
        return ['at most 30 questions']
    out, seen = [], set()
    for i, q in enumerate(survey, 1):
        qid = q.get('id') if isinstance(q, dict) else None
        if not isinstance(qid, str) or not re.match(r'^[a-z][a-z0-9_]{0,30}$', qid):
            out.append('question %d: "id" must be lower-case letters, digits or _ (it names the data column q_<id>)' % i)
            continue
        if any(k not in QUESTION_KEYS for k in q):
            out.append('%s: unknown key (use %s)' % (qid, ', '.join(QUESTION_KEYS)))
        if qid in seen:
            out.append('%s: the id is used twice' % qid)
        seen.add(qid)
        kind = q.get('type')
        if kind not in ('number', 'single', 'multi', 'text'):
            out.append('%s: "type" must be number, single, multi or text' % qid)
        if q.get('text') is not None and not _wording(q['text']):
            out.append('%s: "text" must be the wording, or {"pl": ..., "en": ...}' % qid)
        if qid not in BUILTIN_QUESTIONS and not q.get('text'):
            out.append('%s: needs its wording ("text")' % qid)
        opts = q.get('options')
        if opts is not None and (not isinstance(opts, list) or any(not (isinstance(o, list) and len(o) == 2 and _wording(o[1])) for o in opts)):
            out.append('%s: "options" must be [[code, label], ...]' % qid)
            continue
        if kind in ('single', 'multi') and qid not in BUILTIN_QUESTIONS and not opts:
            out.append('%s: needs "options": [[code, label], ...]' % qid)
        codes = [str(o[0]) for o in opts or []]
        if any(not re.match(r'^[a-z0-9_]{1,30}$', c) for c in codes):
            out.append('%s: answer codes must be lower-case letters, digits or _' % qid)
        if len(set(codes)) != len(codes):
            out.append('%s: an answer code is used twice' % qid)
        if q.get('other') and codes and q['other'] not in codes:
            out.append('%s: "other" must be one of its answer codes' % qid)
        for k in ('min', 'max'):
            if q.get(k) is not None and (isinstance(q[k], bool) or not isinstance(q[k], (int, float))):
                out.append('%s: "%s" must be a number' % (qid, k))
        if kind == 'number' and isinstance(q.get('min'), (int, float)) and isinstance(q.get('max'), (int, float)) and q['min'] > q['max']:
            out.append('%s: min is above max' % qid)
        if q.get('required') is not None and not isinstance(q['required'], bool):
            out.append('%s: "required" must be true or false' % qid)
        ex = q.get('explore')
        if ex is not None:
            ok = (isinstance(ex, dict) and all(k in EXPLORE_KEYS for k in ex) and isinstance(ex.get('measures'), list) and 1 <= len(ex['measures']) <= 8
                  and all(isinstance(m, str) and re.match(r'^[a-z][a-z0-9_]{0,40}$', m) for m in ex['measures'])
                  and ex.get('direction', 'either') in ('higher', 'lower', 'either')
                  and all(isinstance(ex.get(k, ''), str) and len(ex.get(k, '')) <= 300 for k in ('title', 'why', 'answer')))
            if not ok:
                out.append('%s: "explore" must be {"measures": [up to 8 column names], "direction": "higher" / "lower" / "either", '
                           '"answer": an answer code (optional), "title", "why" (optional)}' % qid)
            elif ex.get('answer') and codes and ex['answer'] not in codes:
                out.append('%s: "explore" answer must be one of its answer codes' % qid)
    return out


def problems(ov, conditions=None):
    """What is wrong with a set of overrides ({key: value}; null = back to the inherited value); [] = all well.
    conditions: the conditions in force (to check condition_settings against) when ov does not set them."""
    if not isinstance(ov, dict):
        return ['the settings must be an object']
    out = []
    for k, v in ov.items():
        if k not in EDITABLE:
            out.append('%s: not a setting that can be changed here' % k)
        elif v is None:
            continue
        elif k in CHOICES and v not in CHOICES[k]:
            out.append('%s: must be one of %s' % (k, ', '.join(CHOICES[k])))
        elif k == 'survey':
            out += ['questions: ' + p for p in survey_problems(v)]
        elif k == 'conditions':
            if not isinstance(v, list) or len(v) > 8 or any(not isinstance(c, str) or not COND_RE.match(c) for c in v) or len(set(v)) != len(v):
                out.append('conditions: up to 8 different names of letters, digits, - or _ (at most 20 characters)')
    cs = ov.get('condition_settings')
    if cs is not None and 'condition_settings' in ov:
        conds = ov['conditions'] if isinstance(ov.get('conditions'), list) else (conditions or [])
        if not isinstance(cs, dict):
            out.append('condition_settings: must be {condition: {setting: value}}')
        else:
            for c, sub in cs.items():
                if c not in conds:
                    out.append('condition_settings: %s is not one of the conditions' % c)
                elif not isinstance(sub, dict) or any(x not in COND_KEYS for x in sub):
                    out.append('condition_settings.%s: only %s' % (c, ', '.join(COND_KEYS)))
                else:
                    out += ["condition %s: %s" % (c, p) for p in problems(sub)]
    return out


def apply(cfg, ov):
    """cfg with the overrides applied (a key set to null is left as inherited)."""
    if not ov:
        return cfg
    out = dict(cfg)
    for k, v in ov.items():
        if k in EDITABLE and v is not None:
            out[k] = v
    return out


def nutrition_mode(cfg):
    """visible, hidden or none: the "nutrition" setting, or what the earlier keys (nutrition_panel, nutrition_reveal) meant."""
    if cfg.get('nutrition') in CHOICES['nutrition']:
        return cfg['nutrition']
    if cfg.get('nutrition_reveal'):
        return 'hidden'
    return 'visible' if cfg.get('nutrition_panel') else 'none'
