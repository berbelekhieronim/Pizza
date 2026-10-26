"""Simulated participants, for previewing the reports before real data exists. The data is made up: the groups are
labelled 'Group A/B (simulated)' and no result from it means anything.

    python3 simulate.py <out_dir> <seed> <n> <styles>
    python3 simulate.py sample 5 60 AB      # 60 participants alternating between the two simulated styles
    python3 simulate.py reference 9 200 B   # 200 pizzas to serve as a reference distribution

Writes one demo-format JSON file per participant, which analysis/analyse.py reads directly.
"""
import os
import json, math, random, sys
R = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 5)
TRAY = ['pep', 'ham', 'chk', 'anc', 'mus', 'grp', 'oni', 'oli', 'crn', 'pin', 'jal', 'bas', 'shr', 'egg', 'gor', 'nor', 'kim', 'par']
BASE = {'pep': .68, 'ham': .3, 'chk': .25, 'anc': .07, 'mus': .5, 'grp': .35, 'oni': .4, 'oli': .35, 'crn': .2, 'pin': .2, 'jal': .2,
        'bas': .3, 'shr': .1, 'egg': .07, 'gor': .1, 'nor': .03, 'kim': .04, 'par': .04}
MEAT, FISH, ANIMAL = {'pep', 'ham', 'chk'}, {'anc', 'shr'}, {'egg', 'gor'}
UNUSUAL = {'nor', 'kim', 'par'}
def person(style, pid):
    diet = R.choices(['none', 'vegetarian', 'vegan', 'pescatarian'], [.76, .14, .05, .05])[0]
    boost = 3.2 if style == 'A' and R.random() < .6 else 1.0
    chosen = [k for k in TRAY if R.random() < min(.9, BASE[k] * (boost if k in UNUSUAL | {'anc', 'gor', 'egg'} else 1))]
    if diet in ('vegetarian', 'vegan'): chosen = [k for k in chosen if k not in MEAT | FISH]
    if diet == 'pescatarian': chosen = [k for k in chosen if k not in MEAT]
    if diet == 'vegan': chosen = [k for k in chosen if k not in ANIMAL]
    if R.random() < .03: chosen = []                     # a plain pizza now and then
    if not chosen and R.random() < .8: chosen = ['mus'] if diet != 'none' else ['pep']
    if R.random() < .03 and diet == 'vegetarian': chosen.append('ham')   # someone breaking their own stated diet
    plan = []
    for k in chosen:
        n = R.randint(4, 10) if k == 'pep' else R.randint(1, 3) if k in UNUSUAL else R.randint(2, 7)
        plan += [k] * n
    if R.random() < (.25 if style == 'A' else .55): R.shuffle(plan)   # alternating vs grouped by topping
    arrangement = R.choices(['scatter', 'mirror', 'ring'], [.5, .3, .2] if style == 'A' else [.85, .1, .05])[0]
    pts = []
    if arrangement == 'ring':
        k = len(plan)
        for i in range(k):
            r = .3 if i % 2 else .62
            t = 2 * math.pi * i / max(1, k) + .2
            pts.append((r * math.cos(t), r * math.sin(t)))
    elif arrangement == 'mirror':
        half = [(R.uniform(.05, .8), R.uniform(-.8, .8)) for _ in range((len(plan) + 1) // 2)]
        for x, y in half: pts += [(x, y), (-x + R.uniform(-.03, .03), y + R.uniform(-.03, .03))]
        pts = pts[:len(plan)]
    else:
        for _ in plan:
            r, t = .82 * math.sqrt(R.random()), R.random() * 6.283
            pts.append((r * math.cos(t), r * math.sin(t)))
    grower = R.random() < .25
    slow = 1.35 if style == 'A' else 1.0
    t, ev, final = 0, [[0, 'start', ' '.join(TRAY)]], []
    t += int(R.lognormvariate(8.0, .4) * slow)
    for i, (k, (x, y)) in enumerate(zip(plan, pts)):
        r = math.hypot(x, y)
        if r > .9: x, y = x * .9 / r, y * .9 / r
        x, y = round(x, 3), round(y, 3)
        t += int(R.lognormvariate(6.9, .55) * slow); ev.append([t, 'pick', k, i + 1, 'm'])
        drag = int(R.lognormvariate(6.2, .3)); g = round(R.uniform(1.3, 2.3), 2) if grower and R.random() < .3 else 1
        if g > 1: drag += int((g - 1) / .8 * 1000) + 500
        t += drag; ev.append([t, 'add', k, i + 1, x, y, drag, 0, g])
        final.append([i + 1, k, x, y, R.randrange(360), round(R.uniform(.9, 1.1), 2), R.randrange(3), i + 1, g])
    t += R.randint(1500, 6000); ev.append([t, 'done']); ev.append([t + 900, 'finish'])
    cheese = 'none' if diet == 'vegan' else R.choices(['light', 'normal', 'extra', 'none'], [.2, .6, .17, .03])[0]
    sauce = R.choices(['tomato', 'white', 'bbq', 'none'], [.82, .06, .09, .03])[0]
    if diet == 'vegan' and sauce == 'white': sauce = 'tomato'
    summ = {'finished': True, 'cond': 'simulated', 'sauce': sauce, 'cheese': cheese, 'tray': TRAY, 'hiddenMs': 0}
    fol = {'diet': [diet] if diet != 'none' else ['none'], 'health': ['none'], 'freq': '1-3m', 'items': {}, 'pizza': {}}
    return {'pz_final': json.dumps(final), 'pz_events': json.dumps(ev), 'pz_summary': json.dumps(summ), 'pzf_data': json.dumps(fol)}
out, n, styles = sys.argv[1], int(sys.argv[3]), sys.argv[4]
os.makedirs(out, exist_ok=True)
for i in range(n):
    style = styles[i % len(styles)]
    d = person(style, i); d['group'] = 'Group %s (simulated)' % style
    json.dump(d, open('%s/P%03d.json' % (out, i + 1), 'w'))
