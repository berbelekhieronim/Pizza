"""Simulated participants, for previewing the reports before real data exists. The data is made up: the groups are
labelled 'Group A/B (simulated)', the "About you" answers are drawn at random (style A a little more often autistic /
ADHD), and no result from it means anything.

    python3 simulate.py <out_dir> <seed> <n> <styles>
    python3 simulate.py sample 5 60 AB      # 60 participants alternating between the two simulated styles
    python3 simulate.py reference 9 200 B   # 200 pizzas to serve as a reference distribution

Writes one demo-format JSON file per participant, which analysis/analyse.py reads directly.
"""
import os
import json, math, random, sys
R = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 5)
TRAY = ['pep', 'ham', 'chk', 'tun', 'anc', 'mus', 'grp', 'oni', 'oli', 'crn', 'pin', 'jal', 'bas', 'shr', 'egg', 'gor', 'nor', 'kim', 'kan', 'fig']
BASE = {'pep': .68, 'ham': .3, 'chk': .25, 'anc': .07, 'mus': .5, 'grp': .35, 'oni': .4, 'oli': .35, 'crn': .2, 'pin': .2, 'jal': .2,
        'bas': .3, 'shr': .1, 'egg': .07, 'gor': .1, 'nor': .03, 'kim': .04, 'tun': .22, 'kan': .03, 'fig': .05}
MEAT, FISH, ANIMAL = {'pep', 'ham', 'chk', 'kan'}, {'anc', 'shr', 'tun'}, {'egg', 'gor'}
UNUSUAL = {'nor', 'kim', 'kan', 'fig'}
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
    arrangement = R.choices(['scatter', 'mirror', 'ring', 'face'], [.45, .25, .15, .15] if style == 'A' else [.8, .1, .04, .06])[0]
    pts = []
    if arrangement == 'face':          # two eyes, a smiling row of a mouth, sometimes a nose; the rest scattered round the rim
        eye, mouth_ing = (chosen[0] if chosen else 'pep'), (chosen[-1] if chosen else 'oli')
        face = [(eye, -.3, .3), (eye, .3, .3)] + [(mouth_ing, t * .32, -.42 + .14 * t * t) for t in (-1, -.5, 0, .5, 1)]
        if R.random() < .5: face.append((chosen[len(chosen) // 2] if chosen else 'mus', 0, 0))
        a = R.uniform(-.4, .4)
        face = [(k, x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)) for k, x, y in face]
        rest = [k for k in plan][len(face):]
        plan = [k for k, _, _ in face] + rest
        pts = [(x, y) for _, x, y in face] + [(.8 * math.cos(t), .8 * math.sin(t)) for t in [R.uniform(0, 6.283) for _ in rest]]
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
    elif arrangement != 'face':
        rim = R.random() < .2            # some people go right up to (or onto) the crust
        for _ in plan:
            r, t = (R.uniform(.8, .98) if rim and R.random() < .4 else .82 * math.sqrt(R.random())), R.random() * 6.283
            pts.append((r * math.cos(t), r * math.sin(t)))
    grower = R.random() < .25
    slow = 1.35 if style == 'A' else 1.0
    t, ev, final = 0, [[0, 'start', ' '.join(TRAY)]], []
    t += int(R.lognormvariate(8.0, .4) * slow)
    for i, (k, (x, y)) in enumerate(zip(plan, pts)):
        r = math.hypot(x, y)
        if r > .98: x, y = x * .98 / r, y * .98 / r
        x, y = round(x, 3), round(y, 3)
        t += int(R.lognormvariate(6.9, .55) * slow); ev.append([t, 'pick', k, i + 1, 'm'])
        drag = int(R.lognormvariate(6.2, .3)); g = round(R.uniform(1.3, 2.3), 2) if grower and R.random() < .3 else 1
        if g > 1: drag += int((g - 1) / .8 * 1000) + 500
        # how the drag moved: path (pizza diameters), straightness, pauses, longest pause, dwell, edge crossings, hold before moving
        pauses = sum(R.random() < (.35 if style == 'A' else .15) for _ in range(3))
        mv = [round(R.uniform(.6, 1.4), 2), round(min(1, R.betavariate(9, 2) if style == 'B' else R.betavariate(6, 2)), 2), pauses,
              int(R.lognormvariate(5.9, .4)) if pauses else 0, int(R.lognormvariate(5.3, .6)), int(R.random() < .08), int(R.lognormvariate(4.8, .5))]
        t += drag; ev.append([t, 'add', k, i + 1, x, y, drag, 0, g, mv])
        final.append([i + 1, k, x, y, R.randrange(360), round(R.uniform(.9, 1.1), 2), R.randrange(3), i + 1, g])
    t += R.randint(1500, 6000); ev.append([t, 'done']); ev.append([t + 900, 'finish'])
    cheese = 'none' if diet == 'vegan' else R.choices(['light', 'normal', 'extra', 'none'], [.2, .6, .17, .03])[0]
    sauce = R.choices(['tomato', 'white', 'bbq', 'none'], [.82, .06, .09, .03])[0]
    if diet == 'vegan' and sauce == 'white': sauce = 'tomato'
    summ = {'finished': True, 'cond': 'simulated', 'sauce': sauce, 'cheese': cheese, 'tray': TRAY, 'hiddenMs': 0,
            'pointer': R.choice(['touch', 'mouse'])}
    # follow-up (default style): strong feelings about a few ingredients, five answers about each
    strong = R.sample(TRAY, R.choice([0, 1, 1, 2, 2, 3, 4] if style == 'A' else [0, 0, 1, 1, 2, 3]))
    items = {}
    for k in strong:
        on = k in chosen
        items[k] = {'feel': R.choice(['love', 'like'] if on else ['dislike', 'cant', 'mixed']),
                    'about': R.sample(['texture', 'smell', 'taste', 'look', 'touching'], R.randint(1, 3 if style == 'A' else 2)),
                    'safe': R.choice(['yes', 'sometimes', 'no'] if on else ['no', 'no', 'sometimes']),
                    'sameway': R.choice(['yes', 'sometimes', 'no', 'no'] if style == 'A' else ['sometimes', 'no', 'no', 'no']),
                    'crave': R.choice(['often', 'sometimes', 'never'] if on else ['never']), 'placed': plan.count(k)}
    # "About you": a made-up mix of neurotypes, how they were identified, eating history and self-ratings
    neuro = R.choices([['autistic'], ['adhd'], ['autistic', 'adhd'], ['dys'], ['none'], ['pnts']],
                      [.3, .15, .15, .05, .3, .05] if style == 'A' else [.08, .12, .04, .06, .65, .05])[0]
    dx = {c: R.choice(['formal', 'formal', 'self', 'waiting']) for c in neuro if c in ('autistic', 'adhd')}
    eating = [e for e in ('picky', 'arfid', 'allergy') if R.random() < {'picky': .4 if 'autistic' in neuro else .12, 'arfid': .06, 'allergy': .1}[e]] or ['none']
    about = {'neuro': neuro, 'dx': dx, 'eating': eating, 'picky': max(1, min(7, round(R.gauss(3 + len(strong) * .5 + ('picky' in eating) * 1.5, 1.3)))),
             'sensoryfood': max(1, min(7, round(R.gauss(3 + len(strong) * .6, 1.4)))),
             'age': R.choice(['18-24', '25-34', '25-34', '35-44', '45-54', '55-64']), 'gender': R.choice(['woman', 'man', 'woman', 'man', 'nonbinary'])}
    fol = {'style': 'strong', 'strong': strong, 'none': not strong, 'items': items, 'about': about,
           'diet': [diet] if diet != 'none' else ['none'], 'health': ['none'], 'freq': '1-3m', 'pizza': {}, 'finished': True}
    return {'pz_final': json.dumps(final), 'pz_events': json.dumps(ev), 'pz_summary': json.dumps(summ), 'pzf_data': json.dumps(fol)}
out, n, styles = sys.argv[1], int(sys.argv[3]), sys.argv[4]
os.makedirs(out, exist_ok=True)
for i in range(n):
    style = styles[i % len(styles)]
    d = person(style, i); d['group'] = 'Group %s (simulated)' % style
    json.dump(d, open('%s/P%03d.json' % (out, i + 1), 'w'))
