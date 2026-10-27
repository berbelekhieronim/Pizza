"""Synthetic sessions for the test study: made-up participants, flagged everywhere as synthetic (ids SYN-001 ...,
field synthetic = 1), so the reports have enough pizzas to show what they do before real data exists.

The data has KNOWN, built-in differences between groups (the ground truth below). They follow the study's ideas to
test, so the reports should find them: if they do not, the analysis is not working. No result from synthetic data says
anything about real people.

Ground truth (each person's neurotype is drawn first; everything else follows from it, with noise):
- autistic (incl. AuDHD): fewer different toppings (each topping 0.75 x as likely, unusual ones 0.5 x), toppings kept
  apart (spaced layouts), placed in order (mirror or ring layouts 40% vs 15%, grouped by topping 75% vs 45%), more strong
  feelings with sensory reasons and safe foods, picky eating more common;
- ADHD (incl. AuDHD): quicker decisions (0.75 x the time), more changes of mind (16% vs 6% per piece), unusual
  toppings 1.8 x as likely;
- everyone: half are offered the nutrition button; 60% of them reveal it and 45% of those then take a piece off
  (no group difference built in).

    python3 analysis/synthetic.py out_dir [n]      # writes one JSON per session (analyse.py reads them)
"""
import json
import math
import os
import random
import sys

PREFIX = 'SYN-'
TRAY = ['pep', 'ham', 'chk', 'tun', 'anc', 'mus', 'grp', 'oni', 'oli', 'crn', 'pin', 'jal', 'bas', 'shr', 'egg', 'gor', 'nor', 'kim', 'kan', 'fig']
BASE = {'pep': .68, 'ham': .3, 'chk': .25, 'anc': .07, 'mus': .5, 'grp': .35, 'oni': .4, 'oli': .35, 'crn': .2, 'pin': .2, 'jal': .2,
        'bas': .3, 'shr': .1, 'egg': .07, 'gor': .1, 'nor': .03, 'kim': .04, 'tun': .22, 'kan': .03, 'fig': .05}
MEAT, FISH, ANIMAL = {'pep', 'ham', 'chk', 'kan'}, {'anc', 'shr', 'tun'}, {'egg', 'gor'}
UNUSUAL = {'nor', 'kim', 'kan', 'fig', 'anc', 'gor', 'egg'}
NEURO = [(['none'], .45), (['autistic'], .2), (['adhd'], .15), (['autistic', 'adhd'], .12), (['dys'], .05), (['pnts'], .03)]


def spaced(R, k, min_d=.2):
    """k points spread over the pizza, no two closer than min_d where possible (foods kept apart)."""
    pts = []
    for _ in range(k):
        for _ in range(60):
            r, t = .82 * math.sqrt(R.random()), R.random() * 2 * math.pi
            x, y = r * math.cos(t), r * math.sin(t)
            if all(math.hypot(x - a, y - b) >= min_d for a, b in pts):
                break
        pts.append((x, y))
    return pts


def person(R, i):
    neuro = R.choices([n for n, _ in NEURO], [w for _, w in NEURO])[0]
    aut, adhd = 'autistic' in neuro, 'adhd' in neuro
    diet = R.choices(['none', 'vegetarian', 'vegan', 'pescatarian'], [.76, .14, .05, .05])[0]
    # which toppings
    def p(k):
        v = BASE[k] * (0.75 if aut else 1) * ((0.5 if aut else 1) * (1.8 if adhd else 1) if k in UNUSUAL else 1)
        return min(.9, v)
    chosen = [k for k in TRAY if R.random() < p(k)]
    if diet in ('vegetarian', 'vegan'):
        chosen = [k for k in chosen if k not in MEAT | FISH]
    if diet == 'pescatarian':
        chosen = [k for k in chosen if k not in MEAT]
    if diet == 'vegan':
        chosen = [k for k in chosen if k not in ANIMAL]
    if not chosen:
        chosen = ['mus'] if diet != 'none' else ['pep']
    plan = []
    for k in chosen:
        plan += [k] * (R.randint(4, 9) if k == 'pep' else R.randint(1, 3) if k in UNUSUAL else R.randint(2, 6))
    if R.random() > (.75 if aut else .45):          # grouped by topping, or mixed
        R.shuffle(plan)
    # where the pieces go
    layout = R.choices(['spaced', 'mirror', 'ring', 'scatter'], [.35, .25, .15, .25] if aut else [.15, .1, .05, .7])[0]
    n = len(plan)
    if layout == 'mirror':
        half = spaced(R, (n + 1) // 2, .25)
        pts = []
        for x, y in half:
            x = abs(x) + .05
            pts += [(x, y), (-x + R.uniform(-.03, .03), y + R.uniform(-.03, .03))]
        pts = pts[:n]
    elif layout == 'ring':
        pts = [((.3 if j % 2 else .62) * math.cos(2 * math.pi * j / max(1, n) + .2), (.3 if j % 2 else .62) * math.sin(2 * math.pi * j / max(1, n) + .2)) for j in range(n)]
    elif layout == 'spaced':
        pts = spaced(R, n, .22)
    else:
        pts = [(.82 * math.sqrt(R.random()) * math.cos(t), .82 * math.sqrt(R.random()) * math.sin(t)) for t in [R.random() * 6.283 for _ in range(n)]]
    # the log: picks, drops, changes of mind
    speed = .75 if adhd else 1.0
    t, ev, final = 0, [[0, 'start', ' '.join(TRAY)]], []
    t += int(R.lognormvariate(8.0, .4) * speed)
    for j, (k, (x, y)) in enumerate(zip(plan, pts)):
        r = math.hypot(x, y)
        if r > .98:
            x, y = x * .98 / r, y * .98 / r
        x, y = round(x, 3), round(y, 3)
        if R.random() < (.16 if adhd else .06):     # a change of mind: a piece added, then taken back
            jj, other = 1000 + j, R.choice(TRAY)
            t += int(R.lognormvariate(6.9, .5) * speed); ev.append([t, 'pick', other, jj, 'm'])
            t += 600; ev.append([t, 'add', other, jj, round(R.uniform(-.6, .6), 3), round(R.uniform(-.6, .6), 3), 600, 0, 1, None])
            t += int(R.lognormvariate(7.5, .6) * speed)
            ev.append([t, 'remove', other, jj, .99, .99, 500, None, None, None] if R.random() < .6 else [t, 'undo', 'add', jj, other])
        t += int(R.lognormvariate(6.9, .55) * speed); ev.append([t, 'pick', k, j + 1, 'm'])
        drag = int(R.lognormvariate(6.2, .3))
        t += drag; ev.append([t, 'add', k, j + 1, x, y, drag, 0, 1, None])
        final.append([j + 1, k, x, y, R.randrange(360), round(R.uniform(.9, 1.1), 2), R.randrange(3), j + 1, 1])
    sauce = R.choices(['tomato', 'white', 'bbq', 'none'], [.82, .06, .09, .03])[0]
    cheese = 'none' if diet == 'vegan' else R.choices(['light', 'normal', 'extra', 'none'], [.2, .6, .17, .03])[0]
    if diet == 'vegan' and sauce == 'white':
        sauce = 'tomato'
    summ = {'finished': True, 'cond': 'synthetic', 'sauce': sauce, 'cheese': cheese, 'tray': TRAY, 'hiddenMs': 0, 'pointer': 'mouse', 'v': 'synthetic'}
    # the nutrition button for half of them
    if i % 2 == 0 and final:
        t_done = t + 1500
        shows = 0
        adds = [m for m, e in enumerate(ev) if e[1] == 'add']
        if R.random() < .6 and adds:
            at = R.choice(adds[len(adds) // 3:] or adds)
            ev.insert(at + 1, [ev[at][0] + 1, 'nshow', None, None, sauce, cheese]); shows = 1
            if R.random() < .45 and len(final) > 1:
                f = final.pop(); t_done += 900; ev.append([t_done, 'remove', f[1], f[0], .99, .99, 500, None, None, None])
        t_done += 1500; ev += [[t_done, 'done'], [t_done, 'nmodal', None, None, sauce, cheese]]
        t_done += 1100; ev += [[t_done, 'bake'], [t_done, 'finish']]
        summ['reveal'] = {'shown': shows, 'tFirst': next((e[0] for e in ev if e[1] == 'nshow'), None), 'doneSeen': 1, 'changedMind': 0, 'base': True}
    else:
        t += R.randint(1500, 6000); ev += [[t, 'done'], [t + 900, 'finish']]
    # follow-up: strong feelings (more, and more sensory, for autistic people), "About you"
    strong = R.sample(TRAY, R.choice([1, 2, 2, 3, 4] if aut else [0, 0, 1, 1, 2]))
    items = {}
    for k in strong:
        on = k in chosen
        items[k] = {'feel': R.choice(['love', 'like'] if on else ['dislike', 'cant']),
                    'about': R.sample(['texture', 'smell', 'taste', 'look', 'touching'], R.randint(2, 4) if aut else R.randint(1, 2)),
                    'safe': R.choice(['yes', 'yes', 'sometimes'] if aut and on else ['no', 'sometimes', 'no']),
                    'sameway': R.choice(['yes', 'sometimes', 'no'] if aut else ['no', 'no', 'sometimes']),
                    'crave': R.choice(['often', 'sometimes', 'never'] if on else ['never']), 'placed': plan.count(k)}
    dx = {c: R.choice(['formal', 'formal', 'self', 'waiting']) for c in neuro if c in ('autistic', 'adhd')}
    eating = [e for e in ('picky', 'arfid', 'allergy') if R.random() < {'picky': .45 if aut else .12, 'arfid': .06, 'allergy': .1}[e]] or ['none']
    about = {'neuro': neuro, 'dx': dx, 'eating': eating,
             'picky': max(1, min(7, round(R.gauss(3 + 1.5 * ('picky' in eating) + (1 if aut else 0), 1.2)))),
             'sensoryfood': max(1, min(7, round(R.gauss(3 + (1.5 if aut else 0) + .3 * len(strong), 1.3)))),
             'age': R.choice(['18-24', '25-34', '25-34', '35-44', '45-54', '55-64']), 'gender': R.choice(['woman', 'man', 'woman', 'man', 'nonbinary'])}
    fol = {'style': 'strong', 'strong': strong, 'none': not strong, 'items': items, 'about': about,
           'diet': [diet] if diet != 'none' else ['none'], 'health': ['none'], 'freq': '1-3m', 'pizza': {}, 'finished': True}
    return {'pz_final': json.dumps(final), 'pz_events': json.dumps(ev), 'pz_summary': json.dumps(summ), 'pzf_data': json.dumps(fol),
            'synthetic': '1', 'consent': 'synthetic'}, neuro, t


def sessions(n=100, study='tests', seed=2026):
    """n synthetic sessions as the study server stores them: session columns plus fields. The same n and seed always
    give the same sessions, so inserting them again changes nothing."""
    R = random.Random(seed)
    out = []
    for i in range(n):
        fields, neuro, ms = person(R, i)
        day = 1 + i % 27
        started = '2026-10-%02dT%02d:%02d:00Z' % (day, 9 + i % 10, (i * 7) % 60)
        out.append({'pid': '%s%03d' % (PREFIX, i + 1), 'study': study, 'grp': 'synthetic', 'source': 'synthetic', 'invite': '', 'cond': 'synthetic',
                    'stage': 'done', 'started': started, 'updated': started, 'finished': started, 'seconds': round(ms / 1000 + 120, 1), 'restarts': 0,
                    'consent': 'synthetic', 'n_pieces': len(json.loads(fields['pz_final'])), 'neuro': ' '.join(neuro), 'fields': fields})
    return out


def is_synthetic(pid):
    return str(pid or '').startswith(PREFIX)


if __name__ == '__main__':
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for s in sessions(int(sys.argv[2]) if len(sys.argv) > 2 else 100):
        d = dict(s['fields'], group=s['grp'], study=s['study'], stage=s['stage'])
        json.dump(d, open(os.path.join(out, s['pid'] + '.json'), 'w'))
