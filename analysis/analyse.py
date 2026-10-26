#!/usr/bin/env python3
"""Score Pizza Builder data: variety, avoidance, symmetry/clustering, order, timing and norm deviation.

    python3 analyse.py export.csv            # a Qualtrics CSV export (any of the three header styles)
    python3 analyse.py demo1.json demo2.json  # files downloaded from the demo page
    python3 analyse.py export.csv --out results --id PROLIFIC_PID

Writes into --out (default: pizza_results/):
    participants.csv     one row per participant: every summary measure
    ingredients_long.csv one row per participant x topping: counts, picks, latency, ratings, reasons, diet conflict
    events_long.csv      every logged interaction, for sequence analyses
    pizzas/<id>.svg      each final pizza redrawn from its coordinates; gallery.html shows them all
    arrangement.html     symmetry and contact, drawn on every pizza, and compared across groups (--group)
    profiles.html        every participant as a profile across all measures: compare any two, clusters, map
    profiles.csv         the standardised profile scores and cluster of each participant
    dashboard.html       the data at a glance: diet breakdown, normality against a reference distribution (--reference),
                         space / size / time by group, and a sortable table of every participant

Standard library only. Measure definitions are in ../CODEBOOK.md.
"""
import argparse
import csv
import json
import math
import os
import random
import statistics
import sys
from collections import Counter

CATS = {'pep': 'meat', 'ham': 'meat', 'chk': 'meat', 'anc': 'seafood', 'mus': 'veg', 'grp': 'veg', 'oni': 'veg',
        'oli': 'veg', 'crn': 'veg', 'pin': 'fruit', 'jal': 'veg', 'bas': 'herb', 'shr': 'seafood', 'egg': 'egg',
        'gor': 'dairy', 'nor': 'seaweed', 'kim': 'veg', 'par': 'fruit', 'ban': 'fruit', 'wal': 'nut'}
NAMES = {'pep': 'Pepperoni', 'ham': 'Ham', 'chk': 'Chicken', 'anc': 'Anchovies', 'mus': 'Mushrooms', 'grp': 'Green pepper',
         'oni': 'Red onion', 'oli': 'Black olives', 'crn': 'Sweetcorn', 'pin': 'Pineapple', 'jal': 'Jalapenos', 'bas': 'Basil',
         'shr': 'Shrimp', 'egg': 'Egg', 'gor': 'Blue cheese', 'nor': 'Nori', 'kim': 'Kimchi', 'par': 'Pear', 'ban': 'Banana', 'wal': 'Walnuts'}
# a-priori conventionality (same as the task script); validate it against the sample's own norm ratings
TIER = {'pep': 'common', 'ham': 'common', 'chk': 'common', 'mus': 'common', 'grp': 'common', 'oni': 'common', 'oli': 'common',
        'crn': 'common', 'jal': 'common', 'bas': 'common', 'anc': 'mid', 'pin': 'mid', 'shr': 'mid', 'egg': 'mid', 'gor': 'mid',
        'nor': 'unusual', 'kim': 'unusual', 'par': 'unusual', 'ban': 'unusual', 'wal': 'unusual'}
# toppings that spoil quickly or carry a food-safety risk (meat, seafood, egg, soft dairy) - for the dietary-vigilance account
PERISHABLE = {'pep', 'ham', 'chk', 'anc', 'shr', 'egg', 'gor'}
SIZE = {'pep': 13, 'ham': 10, 'chk': 8.5, 'anc': 15, 'mus': 12, 'grp': 13.5, 'oni': 12.5, 'oli': 6.2, 'crn': 6, 'pin': 8.6,
        'jal': 6, 'bas': 12, 'shr': 9.5, 'egg': 8.5, 'gor': 6.5, 'nor': 9.5, 'kim': 9, 'par': 12, 'ban': 6.5, 'wal': 7, 'tom': 10}
# each topping's outline as a capsule: half-length along its long axis and half-width, in pizza units before scaling
# (pizza radius = 100 units ~ 15 cm, so 1 unit ~ 1.5 mm). Round toppings have half-length 0.
FOOT = {'pep': (0, 13), 'ham': (1, 6.4), 'chk': (1.5, 6.5), 'anc': (12, 2.8), 'mus': (0, 11), 'grp': (11, 3), 'oni': (10, 2),
        'oli': (0, 6.1), 'crn': (0, 4.7), 'pin': (0, 6.5), 'jal': (0, 5.6), 'bas': (9.5, 5), 'shr': (0, 8), 'egg': (1, 7.2),
        'gor': (0, 5), 'nor': (1.5, 6.3), 'kim': (2, 5.8), 'par': (8, 4), 'ban': (0, 6.2), 'wal': (0.6, 5.8), 'tom': (0, 10)}
MM_PER_UNIT = 1.5
TOUCH_GAP = 1.0      # units: outlines closer than 1.5 mm count as touching
STACK_DEPTH = 0.5    # outlines overlapping by more than half the thinner piece's half-width count as stacked
MEATS = {'pep', 'ham', 'chk'}
# toppings a stated diet usually rules out - lets analyses separate constraint from preference
DIET_EXCLUDES = {
    'vegetarian': MEATS | {'anc', 'shr'}, 'vegan': MEATS | {'anc', 'shr', 'egg', 'gor'}, 'pescatarian': MEATS,
    'nopork': {'pep', 'ham'}, 'halal': {'pep', 'ham'}, 'kosher': {'pep', 'ham', 'shr'}, 'nobeef': {'pep'},
    'dairyfree': {'gor'},
}
# what each topping means for a diet. Kimchi is counted as vegan, as many shop brands are; traditional kimchi contains
# fish sauce, so change it to 'seafood' if that matches your stimulus.
DIET_CLASS = {'pep': 'meat', 'ham': 'meat', 'chk': 'meat', 'anc': 'seafood', 'shr': 'seafood', 'egg': 'vegetarian', 'gor': 'vegetarian'}
PIZZA_CLASSES = [('vegan', 'Vegan'), ('vegetarian', 'Vegetarian'), ('pescatarian', 'Pescatarian'), ('meat', 'Contains meat')]


def topping_diet(ing):
    return DIET_CLASS.get(ing, 'vegan')


def pizza_diet_class(pieces, summary):
    """Strictest diet the whole pizza fits: cheese and white sauce count as dairy."""
    kinds = {topping_diet(p['ing']) for p in pieces}
    if 'meat' in kinds:
        return 'meat'
    if 'seafood' in kinds:
        return 'pescatarian'
    cheese, sauce = (summary or {}).get('cheese'), (summary or {}).get('sauce')
    if 'vegetarian' in kinds or (cheese not in (None, 'none')) or sauce == 'white':
        return 'vegetarian'
    return 'vegan'


PIZZA_ITEMS = ['express', 'distinct', 'auton', 'control', 'system', 'safety']
HEALTH = ['allergy', 'intolerance', 'digestive', 'badexp', 'sensory']
R_VALID = 0.9          # topping centres lie within this radius (pizza radius = 1)
SECTORS = 8
REASONS = ['taste', 'diet', 'culture', 'allergy', 'health', 'safety', 'disgust', 'unfamiliar', 'notpizza', 'nofit', 'noreason', 'other']
SCALES = ['like', 'fam', 'safe', 'disg', 'norm', 'ident']


# ------------------------------------------------------------------ reading

def field(row, name):
    """Embedded data arrives as name (classic layouts) or __js_name (Simple layout)."""
    for k in (name, '__js_' + name):
        v = row.get(k)
        if v not in (None, ''):
            return v
    return None


def loads(v, default=None):
    if v in (None, ''):
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


def read_inputs(paths, id_col):
    rows = []
    for path in paths:
        if path.lower().endswith('.json'):
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
            d = {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in d.items()}
            d.setdefault('_pid', os.path.splitext(os.path.basename(path))[0])
            rows.append(d)
            continue
        with open(path, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                rid = r.get('ResponseId') or r.get('ResponseID') or ''
                if rid and not rid.startswith('R_'):          # Qualtrics' 2nd/3rd header rows
                    continue
                r['_pid'] = r.get(id_col) or rid or 'row%d' % (len(rows) + 1)
                rows.append(r)
    return rows


# ------------------------------------------------------------------ measures

def shannon(counts):
    n = sum(counts)
    return -sum(c / n * math.log(c / n) for c in counts if c) if n else 0.0


def capsule(p):
    """(end a, end b, half-width) of a piece in radius units (pizza radius = 1), y up."""
    h, w = FOOT.get(p['ing'], (0, SIZE.get(p['ing'], 8)))
    a = math.radians(p.get('rot', 0))
    dx, dy = math.cos(a) * h * p['s'] / 100, -math.sin(a) * h * p['s'] / 100   # the task rotates in screen space (y down)
    return (p['x'] - dx, p['y'] - dy), (p['x'] + dx, p['y'] + dy), w * p['s'] / 100


def point_seg(pt, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L = vx * vx + vy * vy
    t = 0 if L == 0 else max(0.0, min(1.0, ((pt[0] - a[0]) * vx + (pt[1] - a[1]) * vy) / L))
    return math.hypot(pt[0] - a[0] - t * vx, pt[1] - a[1] - t * vy)


def seg_dist(a, b, c, d):
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2, d3, d4 = cross(c, d, a), cross(c, d, b), cross(a, b, c), cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4:
        return 0.0
    return min(point_seg(a, c, d), point_seg(b, c, d), point_seg(c, a, b), point_seg(d, a, b))


def contacts(pieces):
    """Every pair of pieces whose outlines touch or overlap: (lower index, upper index, 'touch'|'stack', gap in units).
    Pieces are in drawing order, so in a stacked pair the second one lies on top."""
    caps = [capsule(p) for p in pieces]
    out = []
    for i in range(len(pieces)):
        a1, b1, w1 = caps[i]
        for j in range(i + 1, len(pieces)):
            a2, b2, w2 = caps[j]
            gap = (seg_dist(a1, b1, a2, b2) - w1 - w2) * 100
            if gap <= TOUCH_GAP:
                out.append((i, j, 'stack' if -gap > STACK_DEPTH * min(w1, w2) * 100 else 'touch', gap))
    return out


def contact_measures(pieces):
    n = len(pieces)
    if n < 2:
        return {'n_touch_pairs': 0, 'n_stack_pairs': 0, 'prop_touching': 0.0 if n else None, 'prop_stacked': 0.0 if n else None,
                'max_stack_depth': 1 if n else None}, {}
    con = contacts(pieces)
    touching, stacked, depth = set(), set(), [1] * n
    for i, j, kind, _ in con:
        touching.update((i, j))
        if kind == 'stack':
            stacked.update((i, j))
    for j in range(n):                      # longest pile ending in piece j (drawing order = stacking order)
        for i, jj, kind, _ in con:
            if jj == j and kind == 'stack':
                depth[j] = max(depth[j], depth[i] + 1)
    st = [c for c in con if c[2] == 'stack']
    gaps = []
    caps = [capsule(p) for p in pieces]
    for i in range(n):
        a1, b1, w1 = caps[i]
        gaps.append(min((seg_dist(a1, b1, caps[j][0], caps[j][1]) - w1 - caps[j][2]) * 100 for j in range(n) if j != i))
    out = {'n_touch_pairs': len(con) - len(st), 'n_stack_pairs': len(st),
           'prop_touching': len(touching) / n, 'prop_stacked': len(stacked) / n, 'max_stack_depth': max(depth),
           'stack_same_share': (sum(pieces[i]['ing'] == pieces[j]['ing'] for i, j, _, _ in st) / len(st)) if st else None,
           'touch_same_share': (sum(pieces[i]['ing'] == pieces[j]['ing'] for i, j, _, _ in con) / len(con)) if con else None,
           'nn_gap_mm': statistics.median(gaps) * MM_PER_UNIT}
    per = {'touching': touching, 'on_top': {j for i, j, k, _ in st}, 'under': {i for i, j, k, _ in st}, 'depth': depth, 'pairs': con}
    return out, per


def area_cm2(p):
    """Area of a piece's outline: a capsule of half-length h and half-width w, 1 unit = 1.5 mm."""
    h, w = FOOT.get(p['ing'], (0, SIZE.get(p['ing'], 8)))
    return (math.pi * w * w + 4 * h * w) * p['s'] ** 2 * (MM_PER_UNIT / 10) ** 2


def border_measures(pieces):
    """Where each piece lies relative to the crust: inside the sauce (outline within r = 0.86), on the crust, or
    hanging over the outer edge (outline beyond r = 1). Radius 1 = 15 cm, so 1 radius unit = 150 mm."""
    if not pieces:
        return {'n_on_crust': 0, 'n_over_edge': 0, 'border_share': None, 'n_centre_on_crust': 0, 'max_overhang_mm': None}, []
    zones, outs = [], []
    for p in pieces:
        a, b, w = capsule(p)
        r_out = max(math.hypot(*a), math.hypot(*b)) + w
        outs.append(r_out)
        zones.append('over' if r_out > 1.005 else 'crust' if r_out > 0.86 else 'inside')
    n = len(pieces)
    return {'n_on_crust': zones.count('crust'), 'n_over_edge': zones.count('over'), 'border_share': (n - zones.count('inside')) / n,
            'n_centre_on_crust': sum(math.hypot(p['x'], p['y']) > 0.86 for p in pieces), 'max_overhang_mm': max(0.0, max(outs) - 1) * 150}, zones


def face_detect(pieces):
    """Looks for a face made of toppings: two round, isolated pieces of the same topping as eyes; below them (in the
    face's own orientation, at any rotation) a mouth: one long piece lying along the eye line, or an evenly spaced row of
    3+ pieces centred under the eyes and following a straight line or a smile; at most one nose between; and at most one
    other piece in the face oval; and the face must make up at least 30% of the pieces on the pizza. Pieces sitting on an
    eye (pupils) count as part of it. On simulated pizzas it found 92% of drawn faces (at any rotation, with or without
    nose, pupils and toppings round the rim) and flagged 0-5% of random or mirror-symmetric pizzas and 7% of rings of
    toppings. Check it against human coding of a subset of your own pizzas before relying on it.
    Returns the best face found, or None. Distances are in units of the eye spacing d."""
    n = len(pieces)
    if n < 3:
        return None
    info = []
    for p in pieces:
        a, b, w = capsule(p)
        h = math.hypot(b[0] - a[0], b[1] - a[1]) / 2
        info.append({'x': p['x'], 'y': p['y'], 'w': w, 'h': h, 'ing': p['ing'],
                     'ux': (b[0] - a[0]) / (2 * h) if h else 1.0, 'uy': (b[1] - a[1]) / (2 * h) if h else 0.0})
    best = None
    cos35 = math.cos(math.radians(35))
    for i in range(n):
        for j in range(i + 1, n):
            A, B = info[i], info[j]
            if A['h'] > 0.03 or B['h'] > 0.03:
                continue
            if A['ing'] != B['ing']:            # eyes are a matching pair
                continue
            same = True
            dx, dy = B['x'] - A['x'], B['y'] - A['y']
            d = math.hypot(dx, dy)
            if d < 0.3 or d > 1.0:
                continue
            on = lambda E, q: math.hypot(q['x'] - E['x'], q['y'] - E['y']) <= E['w']
            part = {i, j} | {k for k in range(n) if k not in (i, j) and (on(A, info[k]) or on(B, info[k]))}
            if any(math.hypot(info[k]['x'] - E['x'], info[k]['y'] - E['y']) < 0.4 * d for E in (A, B) for k in range(n) if k not in part):
                continue
            ux, uy = dx / d, dy / d
            mx, my = (A['x'] + B['x']) / 2, (A['y'] + B['y']) / 2
            for sgn in (1, -1):
                px, py = -uy * sgn, ux * sgn
                loc = []
                for k in range(n):
                    if k in part:
                        continue
                    vx, vy = info[k]['x'] - mx, info[k]['y'] - my
                    loc.append((k, (vx * ux + vy * uy) / d, (vx * px + vy * py) / d))
                mouth, mouth_al, kind = None, 0.0, ''
                for k, al, pp in loc:              # one long piece lying along the eye line
                    q = info[k]
                    if (q['h'] >= 0.04 and 0.45 <= pp <= 2.2 and abs(al) <= 0.35 and abs(q['ux'] * ux + q['uy'] * uy) >= cos35
                            and 2 * (q['h'] + q['w']) >= 0.45 * d):
                        mouth, mouth_al, kind = [k], al, q['ing']
                        break
                if mouth is None:                  # or a row of pieces: the longest chain with small steps
                    cand = sorted((al, pp, k) for k, al, pp in loc if 0.45 <= pp <= 2.2 and abs(al) <= 1.1)
                    m = len(cand)
                    length, prev = [1] * m, [-1] * m
                    for b_ in range(m):
                        for a_ in range(b_):
                            if 0 < cand[b_][0] - cand[a_][0] <= 0.8 and abs(cand[b_][1] - cand[a_][1]) <= 0.3 and length[a_] + 1 > length[b_]:
                                length[b_], prev[b_] = length[a_] + 1, a_
                    for end in sorted(range(m), key=lambda e: -length[e]):
                        if length[end] < 3:
                            break
                        chain, c = [], end
                        while c != -1:
                            chain.append(c)
                            c = prev[c]
                        chain.reverse()
                        als = [cand[c][0] for c in chain]
                        pps = [cand[c][1] for c in chain]
                        span = als[-1] - als[0]
                        mal = statistics.mean(als)
                        gaps = [b2 - a2 for a2, b2 in zip(als, als[1:])]
                        even = statistics.pstdev(gaps) <= 0.35 * statistics.mean(gaps)      # evenly spaced, like a drawn line
                        # a smooth line or smile: residual from the best straight line or centred parabola stays small
                        smooth = min(fit_resid(als, pps, 'line'), fit_resid(als, pps, 'smile')) <= 0.08
                        if span >= 0.6 and abs(mal) <= 0.25 and abs(als[0] + als[-1]) <= 0.35 and even and smooth:
                            mouth, mouth_al = [cand[c][2] for c in chain], mal
                            kinds = Counter(info[k]['ing'] for k in mouth)
                            kind = 'row of %d %s' % (len(mouth), '/'.join(NAMES.get(x, x).lower() for x in kinds))
                            break
                if mouth is None:
                    continue
                used = part | set(mouth)
                mouth_top = min(pp for k, al, pp in loc if k in mouth)
                nose = [k for k, al, pp in loc if k not in used and 0.05 <= pp <= mouth_top - 0.1 and abs(al) <= 0.3]   # between eyes and mouth
                mpos = {k: (al, pp) for k, al, pp in loc if k in mouth}
                # the eyes must stand apart from the mouth, not run on into it (as neighbours in a ring of toppings would)
                if len(mouth) > 1:
                    ms = sorted(mpos.values())
                    step = statistics.mean(b2[0] - a2[0] for a2, b2 in zip(ms, ms[1:]))
                    gap_eye = min(math.hypot(al - ex, pp) for al, pp in ms for ex in (-0.5, 0.5))
                    if gap_eye < max(0.45, 1.3 * step):
                        continue
                    # a drawn mouth stops: no further piece of the same topping carries the row on past either end
                    ends = [min(mouth, key=lambda k: mpos[k][0]), max(mouth, key=lambda k: mpos[k][0])]
                    mouth_ings = {info[k]['ing'] for k in mouth}
                    if any(info[k]['ing'] in mouth_ings and k not in used and
                           math.hypot(info[k]['x'] - info[e]['x'], info[k]['y'] - info[e]['y']) <= 1.5 * step * d for e in ends for k in range(n)):
                        continue
                # clutter: stray pieces inside the face oval (around eyes, nose and mouth); toppings further out, like hair, do not count
                half_w = max(0.5, max(abs(v[0]) for v in mpos.values())) + 0.35
                top, bottom = -0.35, max(v[1] for v in mpos.values()) + 0.3
                cy, ry = (top + bottom) / 2, (bottom - top) / 2
                clutter = sum(1 for k, al, pp in loc if k not in used and (al / half_w) ** 2 + ((pp - cy) / ry) ** 2 <= 1) - min(1, len(nose))
                if clutter > 1:
                    continue
                if len(used | set(nose[:1])) < 0.3 * n:   # a face someone makes is a main feature of the pizza, not 5 pieces among 35
                    continue
                score = 1 - 0.15 * clutter - 0.6 * abs(mouth_al)
                if score >= 0.6 and (best is None or score > best['score']):
                    best = {'score': score, 'eyes': (i, j), 'mouth': mouth, 'nose': nose[:1], 'clutter': clutter,
                            'eye_topping': A['ing'], 'mouth_kind': kind,
                            'up_deg': round(math.degrees(math.atan2(-py, -px))) % 360}
    return best


def fit_resid(xs, ys, kind):
    """Largest residual of a least-squares fit: 'line' y = a + b x, or 'smile' y = a + c x² (a curve symmetric about x = 0)."""
    if len(xs) < 3:
        return 0.0
    fx = xs if kind == 'line' else [x * x for x in xs]
    mx, my = statistics.mean(fx), statistics.mean(ys)
    vx = sum((x - mx) ** 2 for x in fx)
    b = sum((x - mx) * (y - my) for x, y in zip(fx, ys)) / vx if vx else 0.0
    return max(abs(y - (my + b * (x - mx))) for x, y in zip(fx, ys))


def size_matching(pieces, tol=0.1):
    """Do people make pieces the same size on purpose? For every resized piece (size more than 10% from normal): is
    there another piece of the same topping / of another topping in the same category / of a different category whose
    size is within 10%? The last is the chance baseline, so size_match_index > 0 means matching sizes within a topping
    more than across categories."""
    resized = [p for p in pieces if abs(p['g'] - 1) > tol]
    def hit(p, pool):
        return any(abs(p['g'] - q['g']) <= tol * max(p['g'], q['g']) for q in pool)
    same, cat, other = [], [], []
    for p in resized:
        sp = [q for q in pieces if q is not p and q['ing'] == p['ing']]
        cp = [q for q in pieces if q['ing'] != p['ing'] and CATS.get(q['ing']) == CATS.get(p['ing'])]
        op = [q for q in pieces if CATS.get(q['ing']) != CATS.get(p['ing'])]
        if sp:
            same.append(hit(p, sp))
        if cp:
            cat.append(hit(p, cp))
        if op:
            other.append(hit(p, op))
    share = lambda v: sum(v) / len(v) if v else None
    out = {'n_resized_pieces': len(resized), 'size_match_same': share(same), 'size_match_category': share(cat), 'size_match_other': share(other)}
    out['size_match_index'] = (out['size_match_same'] - out['size_match_other']) if same and other else None
    return out


def nn_dists(pts):
    out = []
    for i, (x, y) in enumerate(pts):
        best = min((math.hypot(x - a, y - b) for j, (a, b) in enumerate(pts) if j != i), default=None)
        out.append(best)
    return out


def clark_evans(pts):
    """Nearest-neighbour ratio with Donnelly's edge correction for the disc: <1 clustered, ~1 random, >1 evenly spread."""
    n = len(pts)
    if n < 3:
        return None
    area, perim = math.pi * R_VALID ** 2, 2 * math.pi * R_VALID
    expected = 0.5 * math.sqrt(area / n) + (0.0514 + 0.041 / math.sqrt(n)) * perim / n
    return statistics.mean(nn_dists(pts)) / expected


def sym_cost(pieces, transform):
    """Mean distance from each transformed topping to the nearest topping of the same kind (0 = perfect symmetry)."""
    by = {}
    for p in pieces:
        by.setdefault(p['ing'], []).append((p['x'], p['y']))
    total, n = 0.0, 0
    for pts in by.values():
        for x, y in pts:
            tx, ty = transform(x, y)
            total += min(math.hypot(tx - a, ty - b) for a, b in pts)
            n += 1
    return total / n if n else None


def mirror(phi):
    c, s = math.cos(2 * phi), math.sin(2 * phi)
    return lambda x, y: (c * x + s * y, s * x - c * y)


def rot180(x, y):
    return -x, -y


AXES = [math.radians(a) for a in range(0, 180, 10)]


def symmetry(pieces, rnd):
    """Best mirror-axis cost and 180-degree rotation cost, each divided by the same cost for random layouts
    with the same toppings (ratio < 1 = more symmetric than chance)."""
    if len(pieces) < 2:
        return None, None, None
    obs_m = min(sym_cost(pieces, mirror(a)) for a in AXES)
    best_axis = min(AXES, key=lambda a: sym_cost(pieces, mirror(a)))
    obs_r = sym_cost(pieces, rot180)
    null_m, null_r = [], []
    for _ in range(40):
        fake = []
        for p in pieces:
            r, t = R_VALID * math.sqrt(rnd.random()), rnd.random() * 2 * math.pi
            fake.append({'ing': p['ing'], 'x': r * math.cos(t), 'y': r * math.sin(t)})
        null_m.append(min(sym_cost(fake, mirror(a)) for a in AXES))
        null_r.append(sym_cost(fake, rot180))
    return obs_m / statistics.mean(null_m), obs_r / statistics.mean(null_r), round(math.degrees(best_axis))


def rot_symmetry(pieces, rnd):
    """Best k-fold rotational symmetry, k = 2..8, as a ratio to random layouts (< 1 = more symmetric than chance)."""
    if len(pieces) < 2:
        return None, None
    best = None
    for k in range(2, 9):
        a = 2 * math.pi / k
        c, s = math.cos(a), math.sin(a)
        obs = sym_cost(pieces, lambda x, y: (c * x - s * y, s * x + c * y))
        null = []
        for _ in range(20):
            fake = []
            for p in pieces:
                r, t = R_VALID * math.sqrt(rnd.random()), rnd.random() * 2 * math.pi
                fake.append({'ing': p['ing'], 'x': r * math.cos(t), 'y': r * math.sin(t)})
            null.append(sym_cost(fake, lambda x, y: (c * x - s * y, s * x + c * y)))
        ratio = obs / statistics.mean(null)
        if best is None or ratio <= best[0] + 0.02:     # near-ties go to the higher order: an 8-fold ring is also 4-fold
            best = (min(ratio, best[0]) if best else ratio, k)
    return best


def angular_regularity(pieces):
    """For each topping with >= 3 pieces: CV of the angular gaps between its pieces around the centre
    (0 = evenly spaced like clock positions), averaged over toppings."""
    out = []
    for ing in set(p['ing'] for p in pieces):
        ang = sorted(math.atan2(p['y'], p['x']) for p in pieces if p['ing'] == ing)
        if len(ang) < 3:
            continue
        gaps = [b - a for a, b in zip(ang, ang[1:])] + [ang[0] + 2 * math.pi - ang[-1]]
        out.append(statistics.pstdev(gaps) / statistics.mean(gaps))
    return statistics.mean(out) if out else None


def sector_similarity(pieces):
    """Mean cosine similarity between the topping mixes of the 8 slices: 1 = every slice the same (a repeated pattern)."""
    vecs = {}
    for p in pieces:
        vecs.setdefault(sector(p['x'], p['y']), Counter())[p['ing']] += 1
    v = list(vecs.values())
    if len(v) < 2:
        return None
    sims = []
    for i in range(len(v)):
        for j in range(i + 1, len(v)):
            dot = sum(v[i][k] * v[j][k] for k in v[i])
            sims.append(dot / (math.sqrt(sum(x * x for x in v[i].values())) * math.sqrt(sum(x * x for x in v[j].values()))))
    return statistics.mean(sims)


def sweep_consistency(events):
    """Share of consecutive placements that continue round the pizza in the same direction as the previous step
    (1 = a steady clockwise or anticlockwise sweep, ~0.5 = no direction)."""
    ang = [math.atan2(e[5], e[4]) for e in events if e[1] == 'add' and len(e) > 5 and math.hypot(e[4], e[5]) > 0.15]
    steps = [((b - a + math.pi) % (2 * math.pi)) - math.pi for a, b in zip(ang, ang[1:])]
    steps = [d for d in steps if abs(d) > 1e-6]
    if len(steps) < 3:
        return None
    return sum((a > 0) == (b > 0) for a, b in zip(steps, steps[1:])) / (len(steps) - 1)


def sector(x, y):
    return int(((math.atan2(y, x) + 2 * math.pi) % (2 * math.pi)) / (2 * math.pi / SECTORS)) % SECTORS


def spatial(pieces, rnd):
    out = {}
    n = len(pieces)
    if n == 0:
        out.update(border_measures(pieces)[0])
        out.update({'face_detected': 0, 'face_score': 0.0})
        return out
    xs, ys = [p['x'] for p in pieces], [p['y'] for p in pieces]
    rs = [math.hypot(x, y) for x, y in zip(xs, ys)]
    out['centroid_offset'] = math.hypot(statistics.mean(xs), statistics.mean(ys))
    out['mean_r'] = statistics.mean(rs)
    out['sd_r'] = statistics.pstdev(rs) if n > 1 else 0.0
    out['prop_outer'] = sum(r > 0.6 for r in rs) / n
    ang = [math.atan2(y, x) for x, y in zip(xs, ys)]
    out['circ_resultant'] = math.hypot(sum(map(math.cos, ang)), sum(map(math.sin, ang))) / n
    sec = Counter(sector(x, y) for x, y in zip(xs, ys))
    counts = [sec.get(i, 0) for i in range(SECTORS)]
    out['sectors_used'] = sum(c > 0 for c in counts)
    m = n / SECTORS
    out['sector_cv'] = statistics.pstdev(counts) / m
    out['sector_chi2'] = sum((c - m) ** 2 / m for c in counts)
    # does every slice get every topping? (only toppings with enough pieces to go round count)
    cov = []
    for ing in set(p['ing'] for p in pieces):
        own = [p for p in pieces if p['ing'] == ing]
        if len(own) >= 2:
            cov.append(len(set(sector(p['x'], p['y']) for p in own)) / min(SECTORS, len(own)))
    out['slice_spread'] = statistics.mean(cov) if cov else None
    pts = list(zip(xs, ys))
    out['clark_evans'] = clark_evans(pts)
    if n >= 3:
        nn = nn_dists(pts)
        out['nn_cv'] = statistics.pstdev(nn) / statistics.mean(nn) if statistics.mean(nn) else None
    out['angular_regularity'] = angular_regularity(pieces)
    out['sector_similarity'] = sector_similarity(pieces)
    per = [clark_evans([(p['x'], p['y']) for p in pieces if p['ing'] == ing]) for ing in set(p['ing'] for p in pieces)]
    per = [v for v in per if v is not None]
    out['clark_evans_within'] = statistics.mean(per) if per else None
    if n >= 2:
        same = 0
        for i, p in enumerate(pieces):
            j = min((k for k in range(n) if k != i), key=lambda k: math.hypot(p['x'] - pieces[k]['x'], p['y'] - pieces[k]['y']))
            same += pieces[j]['ing'] == p['ing']
        c = Counter(p['ing'] for p in pieces)
        expected = sum(v * (v - 1) for v in c.values()) / (n * (n - 1))
        out['segregation'] = same / n - expected
    out['coverage'] = coverage(pieces)
    out.update(contact_measures(pieces)[0])
    out.update(border_measures(pieces)[0])
    f = face_detect(pieces)
    out['face_detected'] = int(f is not None)
    out['face_score'] = f['score'] if f else 0.0
    out['face_eyes'] = NAMES.get(f['eye_topping'], f['eye_topping']) if f else None
    out['face_mouth'] = (NAMES.get(f['mouth_kind'], f['mouth_kind']) if f else None)
    out['face_nose'] = (int(bool(f['nose'])) if f else None)
    out['face_up_deg'] = f['up_deg'] if f else None
    out['sym_mirror'], out['sym_rot180'], out['sym_axis_deg'] = symmetry(pieces, rnd)
    out['sym_rot_best'], out['sym_rot_k'] = rot_symmetry(pieces, rnd)
    return out


def coverage(pieces, grid=48):
    """Share of the sauced area (r < 0.86) under a topping, from a grid of sample points."""
    hit = tot = 0
    caps = [capsule(p) for p in pieces]
    for i in range(grid):
        for j in range(grid):
            x, y = -0.86 + 1.72 * (i + 0.5) / grid, -0.86 + 1.72 * (j + 0.5) / grid
            if x * x + y * y > 0.86 ** 2:
                continue
            tot += 1
            hit += any(point_seg((x, y), a, b) <= w for a, b, w in caps)
    return hit / tot if tot else None


def order_measures(events):
    adds = [e for e in events if e[1] == 'add']
    seq = [e[2] for e in adds]
    out = {'first_topping': seq[0] if seq else None}
    n = len(seq)
    if n >= 2:
        switches = sum(a != b for a, b in zip(seq, seq[1:])) / (n - 1)
        c = Counter(seq)
        expected = 1 - sum(v * (v - 1) for v in c.values()) / (n * (n - 1))
        out['switch_rate'] = switches
        out['sweep_consistency'] = sweep_consistency(events)
        out['blockiness'] = expected - switches       # > 0: grouped by topping, < 0: alternating
        ranks = {cat: [i / (n - 1) for i, k in enumerate(seq) if CATS.get(k) == cat] for cat in ('meat', 'veg')}
        if ranks['meat'] and ranks['veg']:
            out['meat_before_veg'] = statistics.mean(ranks['veg']) - statistics.mean(ranks['meat'])
    return out


def timing(events, summary):
    out = {}
    adds = [e[0] for e in events if e[1] == 'add']
    gaps = [b - a for a, b in zip(adds, adds[1:])]
    drags = [e[6] for e in events if e[1] in ('add', 'move') and len(e) > 6]
    # decision time: from the end of one action to picking up the next topping (excludes dragging itself)
    decisions, last_end = [], None
    for e in events:
        if e[1] == 'pick' and last_end is not None:
            decisions.append(e[0] - last_end)
        if e[1] in ('add', 'reject', 'move', 'remove', 'tap', 'resize', 'grow', 'undo', 'sauce', 'cheese'):
            last_end = e[0]
    fin = next((e[0] for e in events if e[1] == 'finish'), None)
    out['t_first_pick'] = next((e[0] for e in events if e[1] == 'pick'), None)
    out['t_done_first'] = next((e[0] for e in events if e[1] == 'done'), None)      # first press of "I'm done"
    out['t_submit'] = fin                                                         # confirmed: the pizza is submitted
    out['n_done_presses'] = sum(e[1] == 'done' for e in events)
    out['t_after_done'] = (fin - out['t_done_first']) if (fin is not None and out['t_done_first'] is not None) else None
    out['t_finish'] = fin
    out['t_active'] = (fin - (summary or {}).get('hiddenMs', 0)) if fin is not None else None
    out['add_gap_median'] = statistics.median(gaps) if gaps else None
    out['decision_median'] = statistics.median(decisions) if decisions else None
    out['drag_median'] = statistics.median(drags) if drags else None
    return out


def practice_measures(summary, events):
    if not summary:
        return {}
    drags = [e[6] for e in events if e[1] in ('add', 'move') and len(e) > 6]
    errs = summary.get('targetErr') or []
    return {'practice_drag_median': statistics.median(drags) if drags else summary.get('dragMsMedian'),
            'practice_target_err': errs[0] if errs else None, 'practice_target_tries': len(errs),
            'practice_ms': (summary.get('stepT') or [None])[-1], 'practice_pointer': summary.get('pointer')}


def ingredient_rows(pid, prefix, summary, events, counts, follow, diet, pieces=()):
    tray = (summary or {}).get('tray') or list(CATS)
    picks, rejects, removes, first_pick, first_add, hover = Counter(), Counter(), Counter(), {}, {}, Counter()
    decide, last_end = {}, None
    for e in events:
        k = e[2] if len(e) > 2 else None
        if e[1] in ('add', 'reject', 'move', 'remove', 'tap', 'resize', 'grow', 'undo', 'sauce', 'cheese'):
            last_end = e[0]
        if e[1] == 'pick':
            picks[k] += 1
            first_pick.setdefault(k, e[0])
            if last_end is not None:
                decide.setdefault(k, []).append(e[0] - last_end)
        elif e[1] == 'add':
            first_add.setdefault(k, e[0])
        elif e[1] == 'reject':
            rejects[k] += 1
        elif e[1] == 'remove':
            removes[k] += 1
        elif e[1] == 'hover':
            hover[k] += e[3]
    excluded = set().union(*[DIET_EXCLUDES.get(d, set()) for d in diet]) if diet else set()
    per = contact_measures(list(pieces))[1] if len(pieces) > 1 else {}
    items = (follow or {}).get('items', {})
    rows = []
    for ing in tray:
        it = items.get(ing, {})
        r = {'pid': pid, 'build': prefix.rstrip('_'), 'ing': ing, 'name': NAMES.get(ing, ing), 'cat': CATS.get(ing),
             'tier': TIER.get(ing), 'perishable': int(ing in PERISHABLE),
             'tray_pos': tray.index(ing) + 1, 'count': counts.get(ing, 0), 'included': int(counts.get(ing, 0) > 0),
             'picks': picks[ing], 'rejects': rejects[ing], 'removes': removes[ing],
             'picked_not_kept': int(picks[ing] > 0 and counts.get(ing, 0) == 0),
             'first_pick_ms': first_pick.get(ing), 'first_add_ms': first_add.get(ing), 'hover_ms': hover[ing] or None,
             'decision_ms_mean': statistics.mean(decide[ing]) if ing in decide else None,
             'area_cm2': sum(area_cm2(p) for p in pieces if p['ing'] == ing),
             'size_mean': (statistics.mean(p['g'] for p in pieces if p['ing'] == ing) if counts.get(ing, 0) else None),
             'n_touching': sum(1 for i in per.get('touching', ()) if pieces[i]['ing'] == ing),
             'n_on_top': sum(1 for i in per.get('on_top', ()) if pieces[i]['ing'] == ing),
             'n_covered': sum(1 for i in per.get('under', ()) if pieces[i]['ing'] == ing),
             'diet_conflict': int(ing in excluded) if diet else None}
        for s in SCALES:
            r[s] = it.get(s)
        r['never_tasted'] = int(bool(it.get('never'))) if it else None
        rs = it.get('reasons')
        for reason in REASONS:
            r['why_' + reason] = (int(reason in rs) if rs is not None else None)
        r['why_other_text'] = it.get('other') or None
        r['rating_ms'] = it.get('ms')
        rows.append(r)
    return rows


def corr(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return statistics.correlation(xs, ys)


# ------------------------------------------------------------------ drawing

COLORS = {'pep': '#a8281e', 'ham': '#e59a94', 'chk': '#e6cc9c', 'anc': '#5d3d2f', 'mus': '#d9c3a1', 'grp': '#3f8a2e',
          'oni': '#93357a', 'oli': '#25231f', 'crn': '#f2c63a', 'pin': '#f3cf55', 'jal': '#6ea548', 'bas': '#2f7d32', 'tom': '#d8432c'}
SAUCE = {'none': '#ecd3a0', 'tomato': '#b8321f', 'white': '#ece2cc', 'bbq': '#6b2614'}
CHEESE = {'none': 0, 'light': 0.35, 'normal': 0.65, 'extra': 0.9}
LONG = {'anc': (1, 0.22), 'grp': (0.95, 0.3), 'oni': (0.9, 0.25), 'bas': (0.9, 0.45), 'mus': (0.9, 0.8)}


def base_svg(summary):
    return ('<circle r="100" fill="#d9a35a"/><circle r="86" fill="%s"/><circle r="84" fill="#f6dc8a" opacity="%s"/>'
            % (SAUCE.get((summary or {}).get('sauce') or 'none', '#ecd3a0'), CHEESE.get((summary or {}).get('cheese') or 'normal', 0.65)))


def glyph(p, extra=''):
    (ax, ay), (bx, by), w = capsule(p)
    col = COLORS.get(p['ing'], '#888')
    if (ax, ay) == (bx, by):
        return '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"%s/>' % (ax * 100, -ay * 100, w * 100, col, extra)
    return ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f" stroke-linecap="round"%s/>'
            % (ax * 100, -ay * 100, bx * 100, -by * 100, col, w * 200, extra))


def pizza_svg(pieces, summary, label=''):
    s = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-105 -118 210 225" width="210" height="225" font-family="sans-serif">', base_svg(summary)]
    s += [glyph(p) for p in pieces]
    s.append('<text x="0" y="-106" text-anchor="middle" font-size="10" fill="#333">%s</text></svg>' % esc(label))
    return ''.join(s)


def esc(t):
    return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def match_class(d):
    return 'ok' if d <= 0.06 else 'near' if d <= 0.15 else 'miss'


def ghost_panel(pieces, summary, transform, guides):
    """Pizza with, for every piece, a ring where its symmetric partner would have to be, coloured by whether one is there."""
    by = {}
    for p in pieces:
        by.setdefault(p['ing'], []).append(p)
    s = ['<svg viewBox="-106 -106 212 212" role="img">', base_svg(None if False else {}), guides]
    s[1] = '<circle r="100" class="crust"/><circle r="86" class="sauce"/>'
    s += [glyph(p, ' opacity=".9"') for p in pieces]
    for p in pieces:
        tx, ty = transform(p['x'], p['y'])
        q = min(by[p['ing']], key=lambda o: math.hypot(tx - o['x'], ty - o['y']))
        d = math.hypot(tx - q['x'], ty - q['y'])
        c = match_class(d)
        if c != 'ok':
            s.append('<line class="link %s" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (c, tx * 100, -ty * 100, q['x'] * 100, -q['y'] * 100))
        s.append('<circle class="ghost %s" cx="%.1f" cy="%.1f" r="%.1f"/>' % (c, tx * 100, -ty * 100, max(capsule(p)[2] * 100 * 0.75, 3)))
    return ''.join(s) + '</svg>'


def mirror_panel(pieces, axis_deg):
    phi = math.radians(axis_deg or 0)
    ex, ey = math.cos(phi) * 104, -math.sin(phi) * 104
    guide = '<line class="axis" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (-ex, -ey, ex, ey)
    return ghost_panel(pieces, None, mirror(phi), guide)


def rotation_panel(pieces, k):
    k = k or 2
    a = 2 * math.pi / k
    c, s_ = math.cos(a), math.sin(a)
    guide = ''.join('<line class="spoke" x1="0" y1="0" x2="%.1f" y2="%.1f"/>' % (math.cos(i * a + math.pi / 2) * 100, -math.sin(i * a + math.pi / 2) * 100) for i in range(k))
    return ghost_panel(pieces, None, lambda x, y: (c * x - s_ * y, s_ * x + c * y), guide)


def contact_panel(pieces):
    _, per = contact_measures(pieces)
    s = ['<svg viewBox="-106 -106 212 212" role="img"><circle r="100" class="crust"/><circle r="86" class="sauce"/>']
    tops = per.get('on_top', set())
    for i, p in enumerate(pieces):
        s.append(glyph(p, ' opacity="%s"' % ('1' if i in per.get('touching', ()) else '.45')))
        if i in tops:
            (ax, ay), (bx, by), w = capsule(p)
            s.append('<circle class="stacktop" cx="%.1f" cy="%.1f" r="%.1f"/>' % (p['x'] * 100, -p['y'] * 100, w * 100 + 3))
    for i, j, kind, _ in per.get('pairs', ()):
        s.append('<line class="%s" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (kind, pieces[i]['x'] * 100, -pieces[i]['y'] * 100, pieces[j]['x'] * 100, -pieces[j]['y'] * 100))
    for i, dpt in enumerate(per.get('depth', ())):
        if dpt >= 3 and i not in per.get('under', ()):      # label each pile once, on its top piece
            s.append('<text class="depth" x="%.1f" y="%.1f">%d</text>' % (pieces[i]['x'] * 100, -pieces[i]['y'] * 100 + 3.5, dpt))
    return ''.join(s) + '</svg>'


def dot_plot(title, values, ref=None, ref_label='', lo=0.0, hi=None, fmt='%.2f'):
    """values: {group: [numbers]}. One row of dots per group, with the median marked."""
    groups = [g for g in values if values[g]]
    if not groups:
        return ''
    allv = [v for g in groups for v in values[g]]
    step = None
    if hi is None:                      # round the top of the axis up to a tidy step so the ticks land on round numbers
        top = max(allv + ([ref] if ref is not None else [])) * 1.05
        raw = max((top - lo) / 5, 1e-9)
        mag = 10 ** math.floor(math.log10(raw))
        step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
        hi = lo + step * math.ceil((top - lo) / step - 1e-9)
    W, right, row = 640, 20, 34
    left = min(300, 24 + 7 * max(len(str(g)) + 5 for g in groups))
    H = 44 + row * len(groups)
    X = lambda v: left + (min(max(v, lo), hi) - lo) / (hi - lo) * (W - left - right)
    s = ['<svg viewBox="0 0 %d %d" class="dots" role="img" aria-label="%s">' % (W, H, esc(title))]
    n_ticks = round((hi - lo) / step) if step else 5
    for t in range(n_ticks + 1):
        v = lo + (hi - lo) * t / n_ticks
        s.append('<line class="grid" x1="%.1f" x2="%.1f" y1="18" y2="%d"/><text class="tick" x="%.1f" y="%d">%s</text>' % (X(v), X(v), H - 20, X(v), H - 6, fmt % v))
    if ref is not None:
        s.append('<line class="ref" x1="%.1f" x2="%.1f" y1="14" y2="%d"/><text class="reflabel" x="%.1f" y="12">%s</text>' % (X(ref), X(ref), H - 20, X(ref), esc(ref_label)))
    rnd = random.Random(7)
    for gi, g in enumerate(groups):
        y = 34 + gi * row
        s.append('<text class="glabel" x="%d" y="%.1f">%s <tspan class="n">n=%d</tspan></text>' % (left - 10, y + 4, esc(g), len(values[g])))
        for v in values[g]:
            s.append('<circle class="dot g%d" cx="%.1f" cy="%.1f" r="4.5"/>' % (gi % 4, X(v), y + rnd.uniform(-7, 7)))
        m = statistics.median(values[g])
        s.append('<line class="median" x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f"/>' % (X(m), X(m), y - 12, y + 12))
    return '<figure><figcaption>%s</figcaption>%s</svg></figure>' % (esc(title), ''.join(s))


REPORT_CSS = """
:root { --bg:#f7f4f0; --fg:#2a2421; --muted:#6e635b; --line:#ddd3c8; --panel:#ffffff; --crust:#e2b06a; --sauce:#f3e6c9;
  --ok:#2e8b57; --near:#d08a00; --miss:#c23b22; --axis:#2457a6; --g0:#2457a6; --g1:#c2571a; --g2:#5b8c2a; --g3:#8a4fa8;
  --font: "Segoe UI", system-ui, -apple-system, sans-serif; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#1c1917; --fg:#ece5dd; --muted:#aa9e93; --line:#3b332d; --panel:#25201c;
  --crust:#8a6438; --sauce:#4a3f33; --ok:#5cc28a; --near:#f0b43c; --miss:#ff7a5c; --axis:#7fb0ff; --g0:#7fb0ff; --g1:#ff9d5c; --g2:#a5d36b; --g3:#d39cf0; color-scheme: dark; } }
:root[data-theme="dark"] { --bg:#1c1917; --fg:#ece5dd; --muted:#aa9e93; --line:#3b332d; --panel:#25201c;
  --crust:#8a6438; --sauce:#4a3f33; --ok:#5cc28a; --near:#f0b43c; --miss:#ff7a5c; --axis:#7fb0ff; --g0:#7fb0ff; --g1:#ff9d5c; --g2:#a5d36b; --g3:#d39cf0; color-scheme: dark; }
body { background: var(--bg); color: var(--fg); font: 15px/1.45 var(--font); margin: 0; }
.wrap { max-width: 1100px; margin: 0 auto; padding-block: 20px 48px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
h1 { font-size: 1.5rem; margin: 0 0 6px; text-wrap: balance; } h2 { font-size: 1.1rem; margin: 28px 0 10px; }
p { max-width: 70ch; } .muted { color: var(--muted); }
.key { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: .88rem; color: var(--muted); align-items: center; }
.key i { display: inline-block; width: 12px; height: 12px; border-radius: 50%; border: 2.5px solid; margin-right: 5px; vertical-align: -2px; }
.key .ok { border-color: var(--ok); } .key .near { border-color: var(--near); } .key .miss { border-color: var(--miss); }
.key .ln { width: 18px; height: 0; border-radius: 0; border-width: 2px 0 0; }
figure { margin: 0 0 14px; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; overflow-x: auto; }
figcaption { font-weight: 600; margin-bottom: 4px; }
.dots { width: 100%; min-width: 480px; height: auto; display: block; }
.dots .grid { stroke: var(--line); } .dots .tick { fill: var(--muted); font-size: 11px; text-anchor: middle; font-variant-numeric: tabular-nums; }
.dots .ref { stroke: var(--fg); stroke-dasharray: 4 3; } .dots .reflabel { fill: var(--fg); font-size: 11px; text-anchor: middle; }
.dots .glabel { fill: var(--fg); font-size: 13px; text-anchor: end; } .dots .n { fill: var(--muted); font-size: 11px; }
.dots .dot { fill-opacity: .7; } .g0 { fill: var(--g0); } .g1 { fill: var(--g1); } .g2 { fill: var(--g2); } .g3 { fill: var(--g3); }
.dots .median { stroke: var(--fg); stroke-width: 2.5; }
.cards { display: grid; gap: 14px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; min-width: 0; }
.card h3 { margin: 0 0 8px; font-size: 1rem; } .card h3 span { color: var(--muted); font-weight: 400; }
.panels { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 640px) { .panels { grid-template-columns: 1fr; } }
.panel { min-width: 0; } .panel svg { width: 100%; max-width: 300px; height: auto; display: block; margin: 0 auto; }
.panel b { display: block; font-size: .9rem; } .panel .v { font-size: .85rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.crust { fill: var(--crust); } .sauce { fill: var(--sauce); }
.axis { stroke: var(--axis); stroke-width: 1.6; stroke-dasharray: 6 4; } .spoke { stroke: var(--axis); stroke-width: 1; stroke-dasharray: 3 3; opacity: .8; }
.ghost { fill: none; stroke-width: 2.2; } .ghost.ok { stroke: var(--ok); } .ghost.near { stroke: var(--near); } .ghost.miss { stroke: var(--miss); }
.link { stroke-width: 1.1; stroke-dasharray: 2 2; } .link.near { stroke: var(--near); } .link.miss { stroke: var(--miss); }
.touch { stroke: var(--near); stroke-width: 1.6; } .stack { stroke: var(--miss); stroke-width: 3; }
.stacktop { fill: none; stroke: var(--miss); stroke-width: 1.6; stroke-dasharray: 3 2; }
.depth { fill: #fff; stroke: #000; stroke-width: .6; paint-order: stroke; font: 700 11px var(--font); text-anchor: middle; }
"""


DASH_CSS = """
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 14px 0 6px; }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; }
.kpi b { display: block; font-size: 1.5rem; font-variant-numeric: tabular-nums; } .kpi span { color: var(--muted); font-size: .85rem; }
.vegan { fill: var(--d-vegan); background: var(--d-vegan); } .vegetarian { fill: var(--d-veg); background: var(--d-veg); }
.pescatarian, .seafood { fill: var(--d-fish); background: var(--d-fish); } .meat { fill: var(--d-meat); background: var(--d-meat); }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: .86rem; color: var(--muted); margin: 4px 0 8px; }
.legend i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
svg text.lab { fill: var(--fg); font-size: 12px; } svg text.val { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
svg text.inbar { fill: #fff; font-size: 11px; font-weight: 600; }
.hist rect.refbar { fill: var(--line); } .band { fill: var(--miss); opacity: .07; } .band.mid { fill: var(--near); opacity: .09; }
.cross { border-collapse: collapse; font-size: .9rem; } .cross th, .cross td { border-bottom: 1px solid var(--line); padding: 4px 10px; text-align: right; }
.cross th:first-child, .cross td:first-child { text-align: left; } .flag { color: var(--miss); font-weight: 600; }
.tablewrap { overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; }
table.people { border-collapse: collapse; font-size: .85rem; width: 100%; min-width: 1100px; font-variant-numeric: tabular-nums; }
table.people th { position: sticky; top: 0; background: var(--panel); text-align: right; padding: 8px 8px; border-bottom: 2px solid var(--line); cursor: pointer; white-space: nowrap; user-select: none; }
table.people th:first-child, table.people td:first-child, table.people th.l, table.people td.l { text-align: left; }
table.people th[aria-sort=ascending]:after { content: " \\25B2"; } table.people th[aria-sort=descending]:after { content: " \\25BC"; }
table.people td { text-align: right; padding: 4px 8px; border-bottom: 1px solid var(--line); }
table.people td svg { width: 54px; height: 54px; display: block; }
table.people th .grp { display: block; font-weight: 400; color: var(--muted); font-size: .72rem; }
.chip { display: inline-block; padding: 1px 8px; border-radius: 999px; color: #fff; font-size: .78rem; white-space: nowrap; }
.chip.typical { background: var(--ok); } .chip.uncommon { background: var(--near); } .chip.unusual { background: var(--miss); }
.note { font-size: .85rem; color: var(--muted); }
"""
DASH_TOKENS = """
:root { --d-vegan:#3f8f4a; --d-veg:#c99a12; --d-fish:#2f78b5; --d-meat:#b8432a; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --d-vegan:#64b56f; --d-veg:#e2b93b; --d-fish:#5ea3dd; --d-meat:#e0715a; } }
:root[data-theme="dark"] { --d-vegan:#64b56f; --d-veg:#e2b93b; --d-fish:#5ea3dd; --d-meat:#e0715a; }
"""


def stacked_bars(title, rows, classes):
    """rows: [(label, Counter of class -> n)]. Horizontal 100% bars, one per row."""
    W, left, right, rowh = 680, 170, 16, 30
    H = 10 + rowh * len(rows)
    s = ['<svg viewBox="0 0 %d %d" class="dots" role="img" aria-label="%s">' % (W, H, esc(title))]
    for i, (label, cnt) in enumerate(rows):
        y, n = 6 + i * rowh, sum(cnt.values())
        s.append('<text class="lab" x="%d" y="%d" text-anchor="end">%s <tspan class="val">n=%d</tspan></text>' % (left - 8, y + 15, esc(label), n))
        x = left
        for k, _ in classes:
            w = (W - left - right) * cnt.get(k, 0) / n if n else 0
            if w <= 0:
                continue
            s.append('<rect class="%s" x="%.1f" y="%d" width="%.1f" height="20" rx="2"/>' % (k, x, y, w))
            if w > 34:
                s.append('<text class="inbar" x="%.1f" y="%d" text-anchor="middle">%d%%</text>' % (x + w / 2, y + 14, round(100 * cnt[k] / n)))
            x += w
    return '<figure><figcaption>%s</figcaption>%s</svg></figure>' % (esc(title), ''.join(s))


def topping_rates(recs, groups, toppings):
    """Share of pizzas in each group that include each topping, coloured by the topping's diet class."""
    W, left, right, rowh = 680, 130, 50, 14 * max(1, len(groups)) + 8
    order = sorted(toppings, key=lambda k: -sum(r['n_' + k] > 0 for r in recs))
    H = 30 + rowh * len(order)
    s = ['<svg viewBox="0 0 %d %d" class="dots" role="img" aria-label="Topping popularity">' % (W, H)]
    for t in range(6):
        x = left + (W - left - right) * t / 5
        s.append('<line class="grid" x1="%.1f" x2="%.1f" y1="16" y2="%d"/><text class="tick" x="%.1f" y="12">%d%%</text>' % (x, x, H, x, t * 20))
    for i, k in enumerate(order):
        y = 22 + i * rowh
        s.append('<text class="lab" x="%d" y="%d" text-anchor="end">%s</text>' % (left - 8, y + rowh / 2 + 2, esc(NAMES.get(k, k))))
        for gi, g in enumerate(groups):
            rs = [r for r in recs if r['_group'] == g]
            rate = sum(r['n_' + k] > 0 for r in rs) / len(rs) if rs else 0
            w = (W - left - right) * rate
            s.append('<rect class="%s" x="%d" y="%.1f" width="%.1f" height="11" rx="2" opacity="%s"/>' % (topping_diet(k), left, y + gi * 14, w, '1' if gi == 0 else '.55'))
            s.append('<text class="val" x="%.1f" y="%.1f">%d%%%s</text>' % (left + w + 4, y + gi * 14 + 9.5, round(rate * 100), (' ' + esc(g)) if len(groups) > 1 and i == 0 else ''))
    return ''.join(s) + '</svg>'


def normality_hist(ref_scores, recs, groups):
    """Histogram of the reference distribution, with every sample pizza as a dot under it, by group."""
    if not ref_scores:
        return ''
    allv = ref_scores + [r['atypicality_bits'] for r in recs if r.get('atypicality_bits') is not None]
    lo, hi = min(allv), max(allv)
    hi = hi if hi > lo else lo + 1
    W, left, right, bins = 680, 130, 16, 24
    X = lambda v: left + (v - lo) / (hi - lo) * (W - left - right)
    cnt = [0] * bins
    for v in ref_scores:
        cnt[min(bins - 1, int((v - lo) / (hi - lo) * bins))] += 1
    top, hh = max(cnt), 110
    H = hh + 36 + 30 * len(groups)
    srt = sorted(ref_scores)
    q = lambda f: srt[min(len(srt) - 1, int(f * len(srt)))]
    s = ['<svg viewBox="0 0 %d %d" class="dots hist" role="img" aria-label="Normality distribution">' % (W, H)]
    s.append('<rect class="band mid" x="%.1f" y="0" width="%.1f" height="%d"/>' % (X(q(.75)), X(q(.95)) - X(q(.75)), H - 22))
    s.append('<rect class="band" x="%.1f" y="0" width="%.1f" height="%d"/>' % (X(q(.95)), W - right - X(q(.95)), H - 22))
    bw = (W - left - right) / bins
    for i, c in enumerate(cnt):
        h = hh * c / top if top else 0
        s.append('<rect class="refbar" x="%.1f" y="%.1f" width="%.1f" height="%.1f"/>' % (left + i * bw + 1, 10 + hh - h, bw - 2, h))
    s.append('<text class="lab" x="%d" y="%d" text-anchor="end">reference</text>' % (left - 8, 10 + hh - 4))
    s.append('<text class="val" x="%.1f" y="10">uncommon</text><text class="val" x="%.1f" y="10">unusual</text>' % (X(q(.75)) + 4, X(q(.95)) + 4))
    rnd = random.Random(3)
    for gi, g in enumerate(groups):
        y = hh + 30 + gi * 30
        vals = [r['atypicality_bits'] for r in recs if r['_group'] == g and r.get('atypicality_bits') is not None]
        s.append('<text class="lab" x="%d" y="%d" text-anchor="end">%s</text>' % (left - 8, y + 4, esc(g)))
        for v in vals:
            s.append('<circle class="dot g%d" cx="%.1f" cy="%.1f" r="4"/>' % (gi % 4, X(v), y + rnd.uniform(-6, 6)))
        if vals:
            m = statistics.median(vals)
            s.append('<line class="median" x1="%.1f" x2="%.1f" y1="%d" y2="%d"/>' % (X(m), X(m), y - 11, y + 11))
    for t in range(6):
        v = lo + (hi - lo) * t / 5
        s.append('<text class="tick" x="%.1f" y="%d">%.0f</text>' % (X(v), H - 6, v))
    return ''.join(s) + '</svg>'


def thumb(pieces, summary):
    return ('<svg viewBox="-102 -102 204 204" aria-hidden="true">%s%s</svg>' % (base_svg(summary), ''.join(glyph(p) for p in pieces)))


DASH_COLS = [  # (key, heading, group, format)
    ('diet_class', 'Diet', 'composition', None), ('n_pieces', 'Pieces', 'composition', '%d'), ('n_distinct', 'Toppings', 'composition', '%d'),
    ('n_distinct_unusual', 'Unusual', 'composition', '%d'), ('composition_pct', 'Which %ile', 'normality', '%.0f'), ('count_pct', 'How many %ile', 'normality', '%.0f'),
    ('normality_band', 'Band', 'normality', None),
    ('sym_mirror', 'Mirror sym.', 'space', '%.2f'), ('sym_rot_best', 'Rotation sym.', 'space', '%.2f'), ('clark_evans', 'Spread (CE)', 'space', '%.2f'),
    ('coverage', 'Coverage', 'space', '%.2f'), ('prop_touching', 'Touching', 'space', '%.2f'), ('max_stack_depth', 'Pile', 'space', '%d'),
    ('topping_area_cm2', 'Area cm²', 'size', '%.0f'), ('n_grown', 'Enlarged', 'size', '%d'), ('n_shrunk', 'Shrunk', 'size', '%d'), ('size_max', 'Max size', 'size', '%.1f'),
    ('t_first_pick', 'First pick s', 'time', 's'), ('decision_median', 'Decision s', 'time', 's'), ('t_submit', 'Done s', 'time', 's'),
    ('n_on_crust', 'On crust', 'space', '%d'), ('n_over_edge', 'Over edge', 'space', '%d'), ('face_detected', 'Face', 'figurative', '%d'),
]


def dashboard_report(entries, ref_info, group_label):
    recs = [r for r, _ in entries]
    if not recs:
        return '<!doctype html><title>Pizza Data Preview</title><p>No pizzas to show.</p>'
    groups = []
    for r in recs:
        if r['_group'] not in groups:
            groups.append(r['_group'])
    med = lambda k: statistics.median([r[k] for r in recs if isinstance(r.get(k), (int, float))] or [0])
    kpis = ''.join('<div class="kpi"><b>%s</b><span>%s</span></div>' % (v, esc(l)) for v, l in [
        (len(recs), 'pizzas'), (len(groups), 'groups' if len(groups) > 1 else 'group'), ('%.0f' % med('n_pieces'), 'median pieces'),
        ('%.0f' % med('n_distinct'), 'median toppings'), ('%.0f s' % (med('t_active') / 1000), 'median build time'),
        ('%d' % ref_info['n'], 'pizzas in the reference')])
    legend = '<div class="legend">%s</div>' % ''.join('<span><i class="%s"></i>%s</span>' % (k, esc(l)) for k, l in PIZZA_CLASSES)
    diet_rows = [('All', Counter(r['diet_class'] for r in recs))] + ([(g, Counter(r['diet_class'] for r in recs if r['_group'] == g)) for g in groups] if len(groups) > 1 else [])
    diet = stacked_bars('What diet does the finished pizza fit?', diet_rows, PIZZA_CLASSES)
    pieces_rows = [(g, Counter({'vegan': sum(r['n_vegan_pieces'] for r in recs if r['_group'] == g), 'vegetarian': sum(r['n_vegetarian_pieces'] for r in recs if r['_group'] == g),
                                'pescatarian': sum(r['n_seafood_pieces'] for r in recs if r['_group'] == g), 'meat': sum(r['n_meat_pieces'] for r in recs if r['_group'] == g)})) for g in groups]
    pieces = stacked_bars('Share of all topping pieces by diet class', pieces_rows, [('vegan', ''), ('vegetarian', ''), ('pescatarian', ''), ('meat', '')])
    stated = [r for r in recs if r.get('diet')]
    cross = ''
    if stated:
        cats = [('vegan', 'vegan'), ('vegetarian', 'vegetarian'), ('pescatarian', 'pescatarian'), ('none', 'no diet / other')]
        def said(r):
            d = (r.get('diet') or '').split()
            return next((k for k, _ in cats[:3] if k in d), 'none')
        allowed = {'vegan': {'vegan'}, 'vegetarian': {'vegan', 'vegetarian'}, 'pescatarian': {'vegan', 'vegetarian', 'pescatarian'}}
        rows_html = ''
        for k, label in cats:
            rs = [r for r in stated if said(r) == k]
            if not rs:
                continue
            c = Counter(r['diet_class'] for r in rs)
            bad = sum(1 for r in rs if k in allowed and r['diet_class'] not in allowed[k])
            rows_html += '<tr><td>Says %s</td>%s<td class="%s">%s</td></tr>' % (esc(label), ''.join('<td>%d</td>' % c.get(pk, 0) for pk, _ in PIZZA_CLASSES),
                                                                             'flag' if bad else '', bad if k in allowed else '-')
        cross = ('<figure><figcaption>Stated diet × the pizza they made</figcaption><table class="cross"><tr><th>Stated diet</th>%s<th>Breaks own diet</th></tr>%s</table>'
                 '<p class="note">A pizza that breaks the stated diet is worth checking: a misclick, an unclear topping, or a diet held loosely.</p></figure>'
                 % (''.join('<th>%s</th>' % esc(l) for _, l in PIZZA_CLASSES), rows_html))
    ref_txt = ('%d pizzas from a separate reference set' % ref_info['n']) if ref_info['external'] else ('the other %d pizzas in this sample (each pizza is left out of its own reference)' % (ref_info['n'] - 1))
    hist = normality_hist(ref_info['scores'], recs, groups)
    bands = '<div class="legend">%s</div>' % ''.join(
        '<span>%s %s</span>' % ('<span class="chip %s">%s</span>' % (b, b), ' '.join('%s: %d' % (esc(g), sum(1 for r in recs if r['_group'] == g and r.get('normality_band') == b)) for g in groups))
        for b in ('typical', 'uncommon', 'unusual'))
    unusual = sorted([e for e in entries if e[0].get('atypicality_pct') is not None], key=lambda e: -e[0]['atypicality_bits'])[:6]
    examples = ''.join('<div class="card" style="display:flex;gap:12px;align-items:center"><div style="width:90px;flex:none">%s</div><div><b>%s</b> <span class="chip %s">%s · %.0fth percentile</span><div class="note">%s</div></div></div>'
                       % (thumb(p, {}), esc(r['pid']), r['normality_band'], r['normality_band'], r['atypicality_pct'], esc(r.get('unusual_elements') or 'common toppings only'))
                       for r, p in unusual)
    vals = lambda k, scale=1: {g: [r[k] / scale for r in recs if r['_group'] == g and isinstance(r.get(k), (int, float))] for g in groups}
    space = (dot_plot('Mirror symmetry vs random (lower = more symmetric)', vals('sym_mirror'), 1.0, 'random', hi=1.5) +
             dot_plot('Spread: Clark-Evans ratio (<1 clustered, >1 evenly spaced)', vals('clark_evans'), 1.0, 'random') +
             dot_plot('Share of the pizza covered by toppings', vals('coverage'), lo=0.0, hi=1.0) +
             dot_plot('Share of pieces touching another piece', vals('prop_touching'), lo=0.0, hi=1.0))
    size = (dot_plot('Total topping area (cm² on a 30 cm pizza)', vals('topping_area_cm2'), lo=0.0, fmt='%.0f') +
            dot_plot('Number of pieces', vals('n_pieces'), lo=0.0, fmt='%.0f') +
            dot_plot('Size matching: share of resized pieces sized like another piece of the same topping', vals('size_match_same'), lo=0.0, hi=1.0) +
            dot_plot('Mean piece size (1 = normal; holding a topping pulses it between 0.5 and 2.5)', vals('size_mean'), lo=0.5, hi=2.5, fmt='%.1f'))
    time_ = (dot_plot('Median decision time, seconds (end of one action to picking up the next topping)', vals('decision_median', 1000), lo=0.0, fmt='%.1f') +
             dot_plot('Total build time, seconds (time on other tabs removed)', vals('t_active', 1000), lo=0.0, fmt='%.0f') +
             dot_plot('Time to first topping, seconds', vals('t_first_pick', 1000), lo=0.0, fmt='%.1f') +
             dot_plot('Time to completion: confirmed "I\'m done", seconds', vals('t_submit', 1000), lo=0.0, fmt='%.0f'))
    head = '<tr><th class="l">Pizza</th><th class="l">Participant</th><th class="l">Group</th>%s</tr>' % ''.join(
        '<th%s>%s<span class="grp">%s</span></th>' % (' class="l"' if f is None else '', esc(h), g) for _, h, g, f in DASH_COLS)
    body = []
    for r, p in sorted(entries, key=lambda e: str(e[0]['pid'])):
        cells = []
        for k, _, _, f in DASH_COLS:
            v = r.get(k)
            if v is None:
                cells.append('<td data-v="">-</td>')
            elif f is None:
                cls = {'diet_class': 'chip ' + str(v), 'normality_band': 'chip ' + str(v)}.get(k, '')
                cells.append('<td class="l" data-v="%s"><span class="%s">%s</span></td>' % (esc(v), cls, esc(v)))
            elif f == 's':
                cells.append('<td data-v="%s">%.1f</td>' % (v, v / 1000))
            else:
                cells.append('<td data-v="%s">%s</td>' % (v, f % v))
        body.append('<tr><td>%s</td><td class="l" data-v="%s">%s</td><td class="l" data-v="%s">%s</td>%s</tr>' % (thumb(p, {}), esc(r['pid']), esc(r['pid']), esc(r['_group']), esc(r['_group']), ''.join(cells)))
    sort_js = """<script>
document.querySelectorAll('table.people th').forEach(function (th, i) {
  if (i === 0) return;
  th.tabIndex = 0;
  function sortBy() {
    var tb = th.closest('table').tBodies[0], rows = [].slice.call(tb.rows), asc = th.getAttribute('aria-sort') !== 'ascending';
    th.closest('tr').querySelectorAll('th').forEach(function (h) { h.removeAttribute('aria-sort'); });
    th.setAttribute('aria-sort', asc ? 'ascending' : 'descending');
    rows.sort(function (a, b) {
      var x = a.cells[i].dataset.v, y = b.cells[i].dataset.v, nx = parseFloat(x), ny = parseFloat(y);
      if (x === '' || y === '') return x === '' ? 1 : -1;
      var c = (!isNaN(nx) && !isNaN(ny)) ? nx - ny : String(x).localeCompare(String(y));
      return asc ? c : -c;
    });
    rows.forEach(function (r) { tb.appendChild(r); });
  }
  th.addEventListener('click', sortBy);
  th.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(); } });
});
</script>"""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<title>Pizza Data Preview</title><style>%s%s%s</style></head><body><div class="wrap">'
            '<h1>Pizza data preview</h1><p class="muted">%d pizzas, compared by <code>%s</code>. Every number comes from the recorded coordinates, sizes and timestamps; '
            'column definitions are in CODEBOOK.md.</p><div class="kpis">%s</div>'
            '<h2>Diet: vegan, vegetarian, pescatarian or meat</h2><p class="muted">Each topping has a diet class; cheese and white sauce count as dairy, so a vegan '
            'pizza needs no cheese. A pizza is classed by the strictest diet it fits.</p>%s%s%s%s'
            '<h2>How normal is each pizza?</h2><p class="muted">Two things are compared with the reference (%s). <b>Which toppings</b>: how surprising '
            'the set of toppings is given how often each topping appears; adding a rare topping or leaving off a near-universal one both add surprise (in bits, plotted below). '
            '<b>How many</b>: how extreme the number of different toppings is, in either direction, so a plain pizza or one with everything stands out. '
            'Each becomes a percentile of the reference, and the band uses the more extreme of the two: under 75 is <b>typical</b>, 75-95 <b>uncommon</b>, above 95 <b>unusual</b>.</p>'
            '<figure><figcaption>Which toppings: reference distribution (bars) and this sample (dots; bar = median)</figcaption>%s</figure>%s'
            '<h3>Most unusual pizzas</h3><div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))">%s</div>'
            '<h2>Space</h2>%s<h2>Size and amount</h2>%s<h2>Time</h2>%s'
            '<h2>Every participant</h2><p class="muted">Click a column to sort.</p><div class="tablewrap"><table class="people"><thead>%s</thead><tbody>%s</tbody></table></div>'
            '</div>%s</body></html>'
            % (REPORT_CSS, DASH_TOKENS, DASH_CSS, len(recs), esc(group_label), kpis, legend, diet, pieces, cross,
               esc(ref_txt), hist, bands, examples, space, size, time_, head, ''.join(body), sort_js))


def fmtv(v, f='%.2f'):
    return '-' if v is None else (f % v if isinstance(v, float) else str(v))


def arrangement_report(entries, group_label):
    """entries: list of (record, pieces). Returns the HTML of the symmetry and contact report."""
    by_group = {}
    for rec, _ in entries:
        by_group.setdefault(str(rec.get('_group') or 'all'), []).append(rec)
    def vals(key):
        return {g: [r[key] for r in rs if isinstance(r.get(key), (int, float))] for g, rs in by_group.items()}
    plots = (dot_plot('Mirror symmetry (best axis), relative to random layouts. Lower = more symmetric', vals('sym_mirror'), 1.0, 'random', hi=1.5) +
             dot_plot('Rotational symmetry (best of 2- to 8-fold), relative to random layouts', vals('sym_rot_best'), 1.0, 'random', hi=1.5) +
             dot_plot('Share of pieces touching another piece', vals('prop_touching'), lo=0.0, hi=1.0) +
             dot_plot('Share of pieces stacked on or under another piece', vals('prop_stacked'), lo=0.0, hi=1.0) +
             dot_plot('Tallest pile (layers; 1 = nothing stacked)', vals('max_stack_depth'), lo=1.0, fmt='%.1f'))
    cards = []
    for rec, pieces in sorted(entries, key=lambda e: (e[0].get('sym_mirror') is None, e[0].get('sym_mirror') or 0)):
        if len(pieces) < 2:
            continue
        head = '<h3>%s <span>%s · %s · %d pieces</span></h3>' % (esc(rec['pid']), esc(rec['build']), esc(rec.get('_group') or ''), rec['n_pieces'])
        p1 = '<div class="panel">%s<b>Mirror</b><div class="v">%s × random · axis %s°</div></div>' % (mirror_panel(pieces, rec.get('sym_axis_deg')), fmtv(rec.get('sym_mirror')), fmtv(rec.get('sym_axis_deg')))
        p2 = '<div class="panel">%s<b>Rotation</b><div class="v">%s × random · best %s-fold · half-turn %s ×</div></div>' % (rotation_panel(pieces, rec.get('sym_rot_k')), fmtv(rec.get('sym_rot_best')), fmtv(rec.get('sym_rot_k')), fmtv(rec.get('sym_rot180')))
        p3 = ('<div class="panel">%s<b>Contact and stacking</b><div class="v">%s touching pairs · %s stacked pairs · tallest pile %s · median gap %s mm</div></div>'
              % (contact_panel(pieces), fmtv(rec.get('n_touch_pairs')), fmtv(rec.get('n_stack_pairs')), fmtv(rec.get('max_stack_depth')), fmtv(rec.get('nn_gap_mm'), '%.1f')))
        cards.append('<section class="card">%s<div class="panels">%s%s%s</div></section>' % (head, p1, p2, p3))
    key = ('<div class="key"><span><i class="ok"></i>a matching topping is there</span><span><i class="near"></i>one is close (within 15% of the radius)</span>'
           '<span><i class="miss"></i>none nearby</span><span><i class="ok ln" style="border-color:var(--axis)"></i>mirror axis / rotation spokes</span>'
           '<span><i class="ln" style="border-color:var(--near)"></i>touching</span><span><i class="ln" style="border-color:var(--miss);border-top-width:3px"></i>stacked (dashed ring = piece on top)</span></div>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<title>Pizza Arrangement Report</title><style>%s</style></head><body><div class="wrap">'
            '<h1>Pizza arrangement: symmetry and contact</h1>'
            '<p class="muted">Each ring marks where a topping would have to be for the pizza to be perfectly symmetric: reflected across the best mirror axis, '
            'or turned by the best rotation. The ring\'s colour says whether a piece of the same topping is actually there. The score is the average distance '
            'from each ring to the nearest matching piece, divided by the same distance for random pizzas with the same toppings: 0 is perfect symmetry, 1 is no '
            'more symmetric than chance. The contact panel joins pieces whose outlines touch or overlap; faded pieces touch nothing, and a number gives the '
            'height of a pile of three or more. A negative gap means pieces overlap. Groups come from the <code>%s</code> column.</p>'
            '%s<h2>Across the sample</h2>%s<h2>Each pizza, most mirror-symmetric first</h2><div class="cards">%s</div></div></body></html>'
            % (REPORT_CSS, esc(group_label), key, plots, ''.join(cards)))


# ------------------------------------------------------------------ main

def atypicality(own, ref_sets, toppings):
    """Surprisal (bits) of a pizza's set of toppings under a reference sample: for every topping on offer, how
    unlikely it is to be on (or off) a pizza, from its inclusion rate in the reference (smoothed by +0.5)."""
    n = len(ref_sets)
    total, parts = 0.0, []
    for k in toppings:
        rate = (sum(k in r for r in ref_sets) + 0.5) / (n + 1)
        inc = k in own
        bits = -math.log2(rate if inc else 1 - rate)
        total += bits
        parts.append((bits, k, inc, rate))
    return total, sorted(parts, reverse=True)


def count_extremeness(size, ref_sizes):
    """How extreme a number of different toppings is in the reference, in both directions (very few or very many):
    100 × (1 − two-sided tail probability)."""
    n = len(ref_sizes)
    if not n:
        return None, None
    le, ge = sum(x <= size for x in ref_sizes), sum(x >= size for x in ref_sizes)
    tail = min(1.0, 2 * min((le + 0.5) / (n + 1), (ge + 0.5) / (n + 1)))
    return 100 * (1 - tail), sum(x == size for x in ref_sizes) / n


def normality(own_recs, ref_sets_external, toppings):
    """Scores every pizza against the reference distribution. Without an external reference each pizza is scored
    against all the others (leave one out). Two views: which toppings (composition_pct, from atypicality_bits) and how
    many different toppings (count_pct). atypicality_pct and normality_band take whichever is more extreme."""
    sets = [frozenset(k for k in toppings if r['n_' + k] > 0) for r in own_recs]
    if ref_sets_external:
        ref = list(ref_sets_external)
        ref_scores = [atypicality(ref[i], ref[:i] + ref[i + 1:], toppings)[0] for i in range(len(ref))]
        scored = [atypicality(sset, ref, toppings) for sset in sets]
    else:
        ref = sets
        scored = [atypicality(sets[i], sets[:i] + sets[i + 1:], toppings) for i in range(len(sets))]
        ref_scores = [x[0] for x in scored]
    for i, (rec, (bits, parts)) in enumerate(zip(own_recs, scored)):
        below = sum(x < bits for x in ref_scores) + 0.5 * sum(x == bits for x in ref_scores)
        comp = 100 * below / len(ref_scores) if ref_scores else None
        sizes = [len(r) for r in ref] if ref_sets_external else [len(r) for j, r in enumerate(ref) if j != i]
        cnt, same = count_extremeness(len(sets[i]), sizes)
        pct = max(v for v in (comp, cnt) if v is not None) if (comp is not None or cnt is not None) else None
        rec['atypicality_bits'] = bits
        rec['composition_pct'] = comp
        rec['count_pct'] = cnt
        rec['atypicality_pct'] = pct
        rec['normality_band'] = None if pct is None else 'typical' if pct < 75 else 'uncommon' if pct < 95 else 'unusual'
        why = []
        if cnt is not None and cnt >= 75:
            k = len(sets[i])
            why.append('%s (like %d%% of reference pizzas)' % ('no toppings' if k == 0 else '1 topping' if k == 1 else '%d different toppings' % k, round(same * 100)))
        why += ['%s %s (on %d%% of reference pizzas)' % ('added' if inc else 'left off', NAMES.get(k, k).lower(), round(rate * 100))
                for b, k, inc, rate in parts[:3] if b >= 2]
        rec['unusual_elements'] = '; '.join(why[:3]) or None
    return ref_scores, len(ref)


# The profile: one standardised score per measure, signed so that a higher score always means "more" of the named
# trait (e.g. mirror symmetry uses -sym_mirror, because a lower ratio is more symmetric). 'log' = log(1 + x) first.
PROFILE_FEATURES = [
    ('Composition', 'n_pieces', 'Pieces', 'log', 1), ('Composition', 'n_distinct', 'Different toppings', None, 1),
    ('Composition', 'shannon', 'Variety', None, 1), ('Composition', 'prop_unusual_distinct', 'Unusual toppings', None, 1),
    ('Composition', 'diet_rank', 'Animal products', None, 1),
    ('Normality', 'composition_pct', 'Unusual combination', None, 1), ('Normality', 'count_pct', 'Unusual number of toppings', None, 1),
    ('Space', 'sym_mirror', 'Mirror symmetry', None, -1), ('Space', 'sym_rot_best', 'Rotational symmetry', None, -1),
    ('Space', 'nn_cv', 'Even spacing', None, -1), ('Space', 'sector_similarity', 'Repeating slice pattern', None, 1),
    ('Space', 'clark_evans', 'Spread out', None, 1), ('Space', 'coverage', 'Coverage', None, 1),
    ('Space', 'prop_touching', 'Touching', None, 1), ('Space', 'prop_stacked', 'Stacking', None, 1),
    ('Space', 'border_share', 'On or over the crust', None, 1), ('Space', 'centroid_offset', 'Off-centre', None, 1),
    ('Size', 'topping_area_cm2', 'Amount (area)', 'log', 1), ('Size', 'size_sd', 'Size variation', None, 1),
    ('Size', 'resized_share', 'Pieces resized', None, 1), ('Size', 'size_match_same', 'Size matching within a topping', None, 1),
    ('Order', 'blockiness', 'Grouped by topping', None, 1), ('Order', 'sweep_consistency', 'Placed in a sweep', None, 1),
    ('Time', 't_first_pick', 'Time to start', 'log', 1), ('Time', 'decision_median', 'Decision time', 'log', 1),
    ('Time', 't_submit', 'Time to completion', 'log', 1),
    ('Figurative', 'face_score', 'Face-like', None, 1),
]


def build_profiles(recs):
    """z-scores of every profile feature across the participants given (missing values take the sample median)."""
    cols = []
    for dom, key, label, tf, sign in PROFILE_FEATURES:
        raw = [r.get(key) if isinstance(r.get(key), (int, float)) else None for r in recs]
        vals = [(math.log1p(max(v, 0)) if tf == 'log' else v) * sign if v is not None else None for v in raw]
        present = [v for v in vals if v is not None]
        med = statistics.median(present) if present else 0.0
        filled = [v if v is not None else med for v in vals]
        mu = statistics.mean(filled) if filled else 0.0
        sd = statistics.pstdev(filled) if len(filled) > 1 else 0.0
        cols.append([max(-3.0, min(3.0, (v - mu) / sd)) if sd > 0 else 0.0 for v in filled])
    return [[c[i] for c in cols] for i in range(len(recs))]


def euclid(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def ward(Z):
    """Agglomerative clustering with Ward's criterion (Lance-Williams updates on squared distances).
    Returns the merges as (a, b, height, new_id, size), ids 0..n-1 being the participants."""
    n = len(Z)
    D = {}
    for i in range(n):
        for j in range(i + 1, n):
            D[(i, j)] = sum((x - y) ** 2 for x, y in zip(Z[i], Z[j]))
    size = {i: 1 for i in range(n)}
    active = set(range(n))
    merges, nid = [], n
    key = lambda a, b: (a, b) if a < b else (b, a)
    while len(active) > 1:
        (a, b), dab = min(D.items(), key=lambda kv: kv[1])
        for k in active - {a, b}:
            dka, dkb = D.pop(key(k, a)), D.pop(key(k, b))
            sk, sa, sb = size[k], size[a], size[b]
            D[key(k, nid)] = ((sk + sa) * dka + (sk + sb) * dkb - sk * dab) / (sk + sa + sb)
        del D[(a, b)]
        size[nid] = size[a] + size[b]
        active -= {a, b}
        active.add(nid)
        merges.append((a, b, math.sqrt(max(dab, 0)), nid, size[nid]))
        nid += 1
    return merges


def cut(merges, n, k):
    parent = list(range(n + len(merges)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, _, nid, _ in merges[:n - k]:
        parent[find(a)] = nid
        parent[find(b)] = nid
    roots, labels = {}, []
    for i in range(n):
        r = find(i)
        labels.append(roots.setdefault(r, len(roots)))
    return labels


def leaf_order(merges, n):
    if not merges:
        return list(range(n))
    kids = {nid: (a, b) for a, b, _, nid, _ in merges}
    out, stack = [], [merges[-1][3]]
    while stack:
        x = stack.pop()
        if x < n:
            out.append(x)
        else:
            a, b = kids[x]
            stack += [b, a]
    return out


def silhouette(Z, labels, dist):
    ks = set(labels)
    if len(ks) < 2:
        return None
    vals = []
    for i in range(len(Z)):
        own = [dist[i][j] for j in range(len(Z)) if j != i and labels[j] == labels[i]]
        if not own:
            vals.append(0.0)
            continue
        a = statistics.mean(own)
        b = min(statistics.mean([dist[i][j] for j in range(len(Z)) if labels[j] == c]) for c in ks if c != labels[i])
        vals.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return statistics.mean(vals)


def jacobi_eig(M):
    """Eigenvalues and eigenvectors of a symmetric matrix, largest first (Jacobi rotations)."""
    n = len(M)
    A = [row[:] for row in M]
    V = [[float(i == j) for j in range(n)] for i in range(n)]
    for _ in range(100):
        off = sum(A[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        if off < 1e-12:
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(A[p][q]) < 1e-14:
                    continue
                th = 0.5 * math.atan2(2 * A[p][q], A[q][q] - A[p][p])
                c, s_ = math.cos(th), math.sin(th)
                for k in range(n):
                    akp, akq = A[k][p], A[k][q]
                    A[k][p], A[k][q] = c * akp - s_ * akq, s_ * akp + c * akq
                for k in range(n):
                    apk, aqk = A[p][k], A[q][k]
                    A[p][k], A[q][k] = c * apk - s_ * aqk, s_ * apk + c * aqk
                for k in range(n):
                    vkp, vkq = V[k][p], V[k][q]
                    V[k][p], V[k][q] = c * vkp - s_ * vkq, s_ * vkp + c * vkq
    pairs = sorted(((A[i][i], [V[k][i] for k in range(n)]) for i in range(n)), key=lambda t: -t[0])
    return [p[0] for p in pairs], [p[1] for p in pairs]


def chi2_sf(x, df):
    """P(chi-square with df degrees of freedom > x), via the regularised upper incomplete gamma function."""
    if x <= 0 or df <= 0:
        return 1.0
    a, z = df / 2.0, x / 2.0
    if z < a + 1:                              # series
        term = total = 1.0 / a
        ap = a
        for _ in range(500):
            ap += 1
            term *= z / ap
            total += term
            if abs(term) < abs(total) * 1e-12:
                break
        return max(0.0, 1 - total * math.exp(-z + a * math.log(z) - math.lgamma(a)))
    b, c, d = z + 1 - a, 1e300, 1 / (z + 1 - a)   # continued fraction
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        h *= d * c
        if abs(d * c - 1) < 1e-12:
            break
    return min(1.0, math.exp(-z + a * math.log(z) - math.lgamma(a)) * h)


CLUSTER_COLORS = ['#2457a6', '#c2571a', '#3f8f4a', '#8a4fa8', '#b8892a', '#1f8a8a', '#b8432a', '#5d6b7a']


def profile_analysis(entries, k_force=None):
    """Profiles, distances, Ward clusters (k chosen by silhouette unless forced), PCA."""
    recs = [r for r, _ in entries]
    Z = build_profiles(recs)
    n = len(Z)
    out = {'Z': Z, 'labels': [0] * n, 'k': 1, 'sil': {}, 'order': list(range(n)), 'merges': [], 'pcs': None}
    if n < 4:
        return out
    dist = [[euclid(Z[i], Z[j]) for j in range(n)] for i in range(n)]
    merges = ward(Z)
    ks = range(2, min(8, n - 1) + 1)
    sil = {k: silhouette(Z, cut(merges, n, k), dist) for k in ks}
    k = k_force or max(sil, key=lambda kk: (sil[kk] or -1))
    out.update({'labels': cut(merges, n, k), 'k': k, 'sil': sil, 'order': leaf_order(merges, n), 'merges': merges, 'dist': dist})
    p = len(Z[0])
    C = [[sum(Z[i][a] * Z[i][b] for i in range(n)) / (n - 1) for b in range(p)] for a in range(p)]
    vals, vecs = jacobi_eig(C)
    tot = sum(v for v in vals if v > 0) or 1
    out['pcs'] = {'var': [vals[0] / tot, vals[1] / tot], 'vecs': vecs[:2],
                  'xy': [[sum(Z[i][a] * vecs[c][a] for a in range(p)) for c in range(2)] for i in range(n)]}
    return out


def describe_cluster(Zc):
    """Plain-language summary of a cluster's mean profile: the strongest differences from the sample."""
    means = [statistics.mean(col) for col in zip(*Zc)]
    ranked = sorted(range(len(means)), key=lambda i: -abs(means[i]))
    parts = ['%s %s' % ('more' if means[i] > 0 else 'less', PROFILE_FEATURES[i][2].lower()) for i in ranked[:4] if abs(means[i]) >= 0.4]
    return means, (', '.join(parts) if parts else 'close to the sample average on every measure')


def dendrogram_svg(merges, n, order, labels, width=220):
    """Dendrogram drawn sideways, leaves top to bottom in the heatmap's row order."""
    if not merges:
        return ''
    rowh = max(4, min(14, 900 // max(n, 1)))
    H = n * rowh
    ypos = {leaf: (i + 0.5) * rowh for i, leaf in enumerate(order)}
    hmax = max(m[2] for m in merges) or 1
    X = lambda h: width - 6 - (width - 12) * h / hmax
    xpos = {i: X(0) for i in range(n)}
    s = ['<svg viewBox="0 0 %d %d" width="%d" height="%d" class="dendro" aria-hidden="true">' % (width, H, width, H)]
    for a, b, h, nid, _ in merges:
        xa, xb, xn = xpos[a], xpos[b], X(h)
        s.append('<path d="M%.1f %.1fH%.1fV%.1fH%.1f"/>' % (xa, ypos[a], xn, ypos[b], xb))
        xpos[nid], ypos[nid] = xn, (ypos[a] + ypos[b]) / 2
    return ''.join(s) + '</svg>', rowh


def heat_color(z):
    a = min(1.0, abs(z) / 2.5)
    return ('rgba(200,80,40,%.2f)' if z > 0 else 'rgba(40,100,190,%.2f)') % (0.08 + 0.85 * a)


PROFILE_CSS = """
.heat { display: flex; gap: 0; overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 10px; }
.heat .dendro path { fill: none; stroke: var(--muted); stroke-width: 1; }
.heat table { border-collapse: collapse; font-size: 11px; }
.heat td { padding: 0; } .heat td.c { width: 18px; min-width: 18px; }
.heat th { font-weight: 400; color: var(--muted); height: 130px; vertical-align: bottom; padding: 0 0 4px; }
.heat th div { writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap; font-size: 11px; }
.heat td.id { padding: 0 6px; white-space: nowrap; color: var(--fg); font-variant-numeric: tabular-nums; }
.heat td.band { width: 10px; min-width: 10px; }
.heat td.dcell { vertical-align: top; padding: 0 4px 0 0; line-height: 0; } .heat td.dcell svg { display: block; }
.heat tbody tr { line-height: 1; }
.heat tr.dom th { height: auto; font-weight: 600; color: var(--fg); text-align: left; font-size: 11px; padding: 0 0 2px 2px; border-left: 2px solid var(--line); }
.cl-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.cl-card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; min-width: 0; }
.cl-card h3 { margin: 0 0 4px; font-size: 1rem; display: flex; align-items: center; gap: 8px; }
.sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px; }
.thumbs { display: flex; gap: 6px; margin-top: 8px; } .thumbs svg { width: 70px; height: 70px; }
.pbars { width: 100%; font-size: 12px; border-collapse: collapse; }
.pbars td { padding: 1px 4px; } .pbars td.lab { white-space: nowrap; color: var(--muted); width: 1%; }
.pbars .dom td { color: var(--fg); font-weight: 600; padding-top: 6px; }
.pbar { position: relative; height: 12px; background: linear-gradient(90deg, transparent calc(50% - 1px), var(--line) calc(50% - 1px), var(--line) calc(50% + 1px), transparent calc(50% + 1px)); }
.pbar i { position: absolute; top: 2px; height: 8px; border-radius: 2px; }
.pbar i.a { background: var(--g0); } .pbar i.b { background: var(--g1); opacity: .85; top: 6px; height: 6px; }
.compare { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: 14px; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; }
@media (max-width: 760px) { .compare { grid-template-columns: 1fr; } }
.compare select { font: inherit; padding: 6px 8px; border-radius: 8px; border: 1px solid var(--line); background: var(--bg); color: var(--fg); max-width: 100%; }
.compare .pick { display: flex; flex-direction: column; gap: 8px; }
.compare .pz { display: flex; gap: 10px; } .compare .pz figure { margin: 0; padding: 6px; text-align: center; flex: 1; }
.compare .pz svg { width: 100%; max-width: 150px; height: auto; }
.sim li { margin: 2px 0; } .sim button { font: inherit; background: none; border: 0; color: var(--g0); text-decoration: underline; cursor: pointer; padding: 0; }
.scatter .pt { stroke: var(--panel); stroke-width: 1.2; } .scatter .axis-l { stroke: var(--line); } .scatter text { fill: var(--muted); font-size: 11px; }
"""


def profiles_report(entries, prof, group_label):
    recs = [r for r, _ in entries]
    n = len(recs)
    if n < 4:
        return '<!doctype html><title>Pizza Profiles</title><p>Profiles and clusters need at least 4 pizzas.</p>'
    Z, labels, k, order = prof['Z'], prof['labels'], prof['k'], prof['order']
    groups = []
    for r in recs:
        if r['_group'] not in groups:
            groups.append(r['_group'])
    # heatmap with dendrogram
    dsvg, rowh = dendrogram_svg(prof['merges'], n, order, labels)
    doms = []
    for f in PROFILE_FEATURES:
        if not doms or doms[-1][0] != f[0]:
            doms.append([f[0], 0])
        doms[-1][1] += 1
    head = ('<tr class="dom"><th></th><th></th><th></th>%s</tr><tr><th></th><th></th><th></th>%s</tr>'
            % (''.join('<th colspan="%d">%s</th>' % (c, esc(d)) for d, c in doms), ''.join('<th><div>%s</div></th>' % esc(f[2]) for f in PROFILE_FEATURES)))
    rows = ''.join('<tr style="height:%dpx">%s<td class="id">%s</td><td class="band" style="background:%s" title="cluster %d"></td>%s</tr>' % (
        rowh, ('<td class="dcell" rowspan="%d">%s</td>' % (n, dsvg)) if r == 0 else '', esc(recs[i]['pid']) if rowh >= 10 else '',
        CLUSTER_COLORS[labels[i] % 8], labels[i] + 1,
        ''.join('<td class="c" style="background:%s" title="%s: %s %+.1f"></td>' % (heat_color(z), esc(recs[i]['pid']), esc(PROFILE_FEATURES[c][2]), z) for c, z in enumerate(Z[i])))
        for r, i in enumerate(order))
    heat = '<div class="heat"><table><thead>%s</thead><tbody>%s</tbody></table></div>' % (head, rows)
    # clusters
    sil = ' · '.join('k=%d: %.2f' % (kk, v) for kk, v in sorted(prof['sil'].items()) if v is not None)
    cards = []
    for c in range(k):
        idx = [i for i in range(n) if labels[i] == c]
        Zc = [Z[i] for i in idx]
        means, words = describe_cluster(Zc)
        gc = Counter(recs[i]['_group'] for i in idx)
        cen = means
        near = sorted(idx, key=lambda i: euclid(Z[i], cen))[:4]
        bars = ''.join('<tr><td class="lab">%s</td><td><div class="pbar"><i class="a" style="%s"></i></div></td></tr>' % (
            esc(PROFILE_FEATURES[f][2]), bar_style(means[f])) for f in sorted(range(len(means)), key=lambda f: -abs(means[f]))[:6])
        cards.append('<div class="cl-card"><h3><span class="sw" style="background:%s"></span>Cluster %d <span class="muted" style="font-weight:400">%d pizzas</span></h3>'
                     '<p style="margin:0 0 6px">%s.</p><p class="note" style="margin:0 0 6px">%s</p><table class="pbars">%s</table><div class="thumbs">%s</div></div>'
                     % (CLUSTER_COLORS[c % 8], c + 1, len(idx), esc(words[0].upper() + words[1:]),
                        esc(' · '.join('%s: %d' % (g, gc.get(g, 0)) for g in groups)), bars, ''.join(thumb(entries[i][1], {}) for i in near)))
    # cluster x group
    cross = ''
    if len(groups) > 1:
        tab = [[sum(1 for i in range(n) if labels[i] == c and recs[i]['_group'] == g) for g in groups] for c in range(k)]
        rt = [sum(r) for r in tab]
        ct = [sum(tab[c][g] for c in range(k)) for g in range(len(groups))]
        chi = sum((tab[c][g] - rt[c] * ct[g] / n) ** 2 / (rt[c] * ct[g] / n) for c in range(k) for g in range(len(groups)) if rt[c] and ct[g])
        df = (k - 1) * (len(groups) - 1)
        pval = chi2_sf(chi, df)
        small = sum(1 for c in range(k) for g in range(len(groups)) if rt[c] * ct[g] / n < 5)
        cross = ('<figure><figcaption>Clusters by %s</figcaption><table class="cross"><tr><th>Cluster</th>%s</tr>%s</table>'
                 '<p class="note">χ²(%d) = %.2f, p = %.3f.%s This tests whether the groups spread differently across the clusters; '
                 'the clusters were found without using the groups.</p></figure>'
                 % (esc(group_label), ''.join('<th>%s</th>' % esc(g) for g in groups),
                    ''.join('<tr><td><span class="sw" style="background:%s"></span> %d</td>%s</tr>' % (CLUSTER_COLORS[c % 8], c + 1, ''.join('<td>%d</td>' % v for v in tab[c])) for c in range(k)),
                    df, chi, pval, (' %d of %d expected counts are below 5, so treat p as rough (an exact or permutation test is safer).' % (small, k * len(groups))) if small else ''))
    # PCA map
    scatter = ''
    if prof['pcs']:
        xy = prof['pcs']['xy']
        xs, ys = [p[0] for p in xy], [p[1] for p in xy]
        lim = max(1.0, max(abs(v) for v in xs + ys)) * 1.08
        W, H = 520, 420
        X = lambda v: 30 + (v + lim) / (2 * lim) * (W - 40)
        Y = lambda v: H - 30 - (v + lim) / (2 * lim) * (H - 40)
        shapes = ['circle', 'rect', 'tri', 'diamond']
        def mark(i):
            x, y, col, sh = X(xs[i]), Y(ys[i]), CLUSTER_COLORS[labels[i] % 8], shapes[groups.index(recs[i]['_group']) % 4]
            t = '<title>%s · cluster %d · %s</title>' % (esc(recs[i]['pid']), labels[i] + 1, esc(recs[i]['_group']))
            if sh == 'circle':
                return '<circle class="pt" cx="%.1f" cy="%.1f" r="5.5" fill="%s">%s</circle>' % (x, y, col, t)
            if sh == 'rect':
                return '<rect class="pt" x="%.1f" y="%.1f" width="10" height="10" fill="%s">%s</rect>' % (x - 5, y - 5, col, t)
            if sh == 'tri':
                return '<path class="pt" d="M%.1f %.1fL%.1f %.1fL%.1f %.1fZ" fill="%s">%s</path>' % (x, y - 6, x + 6, y + 5, x - 6, y + 5, col, t)
            return '<path class="pt" d="M%.1f %.1fL%.1f %.1fL%.1f %.1fL%.1f %.1fZ" fill="%s">%s</path>' % (x, y - 6, x + 6, y, x, y + 6, x - 6, y, col, t)
        load = lambda c: ', '.join('%s %s' % ('+' if prof['pcs']['vecs'][c][a] > 0 else '−', PROFILE_FEATURES[a][2].lower())
                                   for a in sorted(range(len(PROFILE_FEATURES)), key=lambda a: -abs(prof['pcs']['vecs'][c][a]))[:3])
        scatter = ('<figure><figcaption>Map of all profiles (first two principal components). Colour = cluster, shape = %s</figcaption>'
                   '<svg viewBox="0 0 %d %d" class="dots scatter" style="max-width:%dpx" role="img" aria-label="Profile map">'
                   '<line class="axis-l" x1="%.1f" x2="%.1f" y1="10" y2="%d"/><line class="axis-l" y1="%.1f" y2="%.1f" x1="30" x2="%d"/>%s'
                   '<text x="%d" y="%d" text-anchor="end">PC1 %.0f%%</text><text x="34" y="20">PC2 %.0f%%</text></svg>'
                   '<p class="note">PC1 is mostly: %s. PC2 is mostly: %s. Shapes: %s.</p></figure>'
                   % (esc(group_label), W, H, W, X(0), X(0), H - 30, Y(0), Y(0), W - 10, ''.join(mark(i) for i in range(n)),
                      W - 12, H - 36, prof['pcs']['var'][0] * 100, prof['pcs']['var'][1] * 100, esc(load(0)), esc(load(1)),
                      esc(', '.join('%s = %s' % (['●', '■', '▲', '◆'][gi % 4], g) for gi, g in enumerate(groups)))))
    # data for the in-page comparison
    data = {'features': [[f[0], f[2]] for f in PROFILE_FEATURES],
            'people': [{'id': str(recs[i]['pid']), 'group': str(recs[i]['_group']), 'cluster': labels[i] + 1,
                        'z': [round(z, 3) for z in Z[i]], 'svg': thumb(entries[i][1], {})} for i in range(n)],
            'colors': CLUSTER_COLORS}
    script = """<script>
var D = %s;
(function () {
  var sa = document.getElementById('pa'), sb = document.getElementById('pb');
  D.people.forEach(function (p, i) {
    var label = p.id + ' (' + p.group + ', cluster ' + p.cluster + ')';
    sa.add(new Option(label, i)); sb.add(new Option(label, i));
  });
  sb.selectedIndex = D.people.length > 1 ? 1 : 0;
  function dist(a, b) { var s = 0; for (var i = 0; i < a.length; i++) s += (a[i] - b[i]) * (a[i] - b[i]); return Math.sqrt(s); }
  var all = []; for (var i = 0; i < D.people.length; i++) for (var j = i + 1; j < D.people.length; j++) all.push(dist(D.people[i].z, D.people[j].z));
  all.sort(function (x, y) { return x - y; });
  function bar(z, cls) { var w = Math.min(50, Math.abs(z) / 3 * 50); return '<i class="' + cls + '" style="left:' + (z < 0 ? 50 - w : 50) + '%%;width:' + w + '%%"></i>'; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function show() {
    var A = D.people[sa.value], B = D.people[sb.value], d = dist(A.z, B.z), rank = 0;
    while (rank < all.length && all[rank] < d) rank++;
    var rows = '', dom = '';
    D.features.forEach(function (f, i) {
      if (f[0] !== dom) { dom = f[0]; rows += '<tr class="dom"><td colspan="2">' + esc(dom) + '</td></tr>'; }
      rows += '<tr><td class="lab">' + esc(f[1]) + '</td><td><div class="pbar">' + bar(A.z[i], 'a') + bar(B.z[i], 'b') + '</div></td></tr>';
    });
    document.getElementById('bars').innerHTML = rows;
    document.getElementById('pzs').innerHTML = '<figure><div style="color:var(--g0);font-weight:600">' + esc(A.id) + '</div>' + A.svg + '<div class="note">cluster ' + A.cluster + '</div></figure>' +
      '<figure><div style="color:var(--g1);font-weight:600">' + esc(B.id) + '</div>' + B.svg + '<div class="note">cluster ' + B.cluster + '</div></figure>';
    document.getElementById('dist').textContent = 'Distance ' + d.toFixed(2) + ': closer than ' + Math.round(100 - 100 * rank / Math.max(1, all.length)) + '%% of all pairs.';
    var near = D.people.map(function (p, i) { return [dist(A.z, p.z), i]; }).filter(function (x) { return x[1] != sa.value; }).sort(function (x, y) { return x[0] - y[0]; }).slice(0, 5);
    document.getElementById('near').innerHTML = near.map(function (x) { var p = D.people[x[1]]; return '<li><button type="button" data-i="' + x[1] + '">' + esc(p.id) + '</button> · ' + esc(p.group) + ' · cluster ' + p.cluster + ' · ' + x[0].toFixed(2) + '</li>'; }).join('');
  }
  document.getElementById('near').addEventListener('click', function (e) { var i = e.target.getAttribute('data-i'); if (i != null) { sb.value = i; show(); } });
  sa.onchange = show; sb.onchange = show; show();
})();
</script>""" % json.dumps(data)
    compare = ('<div class="compare"><div class="pick"><label for="pa"><b style="color:var(--g0)">Participant A</b></label><select id="pa"></select>'
               '<label for="pb"><b style="color:var(--g1)">Participant B</b></label><select id="pb"></select><div class="pz" id="pzs"></div>'
               '<p class="note" id="dist"></p><div><b>Most similar to A</b><ol class="sim" id="near"></ol></div></div>'
               '<div><table class="pbars" id="bars"></table><p class="note">Bars run from the sample average (centre line) towards less (left) or more (right) of each trait, '
               'in standard deviations (to ±3).</p></div></div>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<title>Pizza Profiles</title><style>%s%s%s</style></head><body><div class="wrap">'
            '<h1>Pizza profiles and clusters</h1>'
            '<p class="muted">Each participant\'s pizza is summarised as a profile of %d measures in seven areas. Each score is standardised across these %d '
            'participants (0 = sample average, ±1 = one standard deviation) and signed so that higher always means <i>more</i> of the named trait. '
            'Profiles are compared by their Euclidean distance and grouped with hierarchical clustering (Ward\'s method). The number of clusters, %d, is the one with the best '
            'average silhouette (%s); higher is better, and values under about 0.25 mean the clusters overlap.</p>'
            '<h2>Compare two participants</h2>%s'
            '<h2>Clusters</h2><div class="cl-cards">%s</div>%s%s'
            '<h2>All profiles</h2><p class="muted">One row per participant, ordered by the clustering tree; the coloured band is the cluster. '
            'Orange = above the sample average, blue = below.</p>%s'
            '</div>%s</body></html>'
            % (REPORT_CSS, DASH_CSS, PROFILE_CSS, len(PROFILE_FEATURES), n, k, esc(sil), compare, ''.join(cards), cross, scatter, heat, script))


def bar_style(z):
    w = min(50.0, abs(z) / 3 * 50)
    return 'left:%.1f%%;width:%.1f%%' % (50 - w if z < 0 else 50, w)


def r4(v):
    return round(v, 4) if isinstance(v, float) else v


def analyse(rows, builds, out_dir, seed, group_col=None, ref_rows=None, k_force=None):
    rnd = random.Random(seed)
    people, ing_long, ev_long, svgs, arrangement = [], [], [], [], []
    for row in rows:
        pid = row['_pid']
        follow = loads(field(row, 'pzf_data'), {}) or {}
        diet = follow.get('diet') or []
        p_sum = loads(field(row, 'pzp_summary'), {})
        p_ev = loads(field(row, 'pzp_events'), [])
        for prefix in builds:
            final = loads(field(row, prefix + 'final'))
            if final is None:
                continue
            summary = loads(field(row, prefix + 'summary'), {}) or {}
            events = loads(field(row, prefix + 'events'), []) or []
            # 's' is the drawn size: the small random variation times how much the participant grew the piece (hold to grow)
            pieces = [{'id': f[0], 'ing': f[1], 'x': f[2], 'y': f[3], 'rot': f[4], 'g': (f[8] if len(f) > 8 else 1),
                       's': f[5] * (f[8] if len(f) > 8 else 1)} for f in final]
            counts = Counter(p['ing'] for p in pieces)
            tray = summary.get('tray') or list(CATS)
            cvec = [counts.get(k, 0) for k in tray]
            n = len(pieces)
            rec = {'pid': pid, 'build': prefix.rstrip('_'), 'condition': summary.get('cond'), 'finished': summary.get('finished'),
                   'n_pieces': n, 'n_distinct': sum(c > 0 for c in cvec),
                   'shannon': shannon(cvec), 'evenness': (shannon(cvec) / math.log(sum(c > 0 for c in cvec))) if sum(c > 0 for c in cvec) > 1 else None,
                   'simpson': (1 - sum((c / n) ** 2 for c in cvec)) if n else None,
                   'n_categories': len(set(CATS.get(p['ing']) for p in pieces)),
                   'meat_or_fish': int(any(CATS.get(p['ing']) in ('meat', 'fish') for p in pieces)),
                   'sauce': summary.get('sauce'), 'cheese': summary.get('cheese')}
            for k in CATS:
                rec['n_' + k] = counts.get(k, 0)
            picked = set(e[2] for e in events if e[1] == 'pick')
            inc = [k for k in tray if counts.get(k, 0) > 0]
            for tier in ('common', 'mid', 'unusual'):
                rec['n_distinct_' + tier] = sum(TIER.get(k) == tier for k in inc)
            rec['prop_unusual_distinct'] = rec['n_distinct_unusual'] / len(inc) if inc else None
            rec['prop_unusual_pieces'] = sum(counts[k] for k in inc if TIER.get(k) == 'unusual') / n if n else None
            per = [k for k in tray if k in PERISHABLE]
            rec['diet_class'] = pizza_diet_class(pieces, summary)
            rec['diet_rank'] = ['vegan', 'vegetarian', 'pescatarian', 'meat'].index(rec['diet_class'])
            area_by = Counter()
            for p in pieces:
                area_by[topping_diet(p['ing'])] += area_cm2(p)
            tot_area = sum(area_by.values())
            for k in ('vegan', 'vegetarian', 'seafood', 'meat'):
                rec['n_' + k + '_pieces'] = sum(topping_diet(p['ing']) == k for p in pieces)
                rec['area_share_' + k] = area_by[k] / tot_area if tot_area else None
            rec['_tray'] = tray
            gs = [p['g'] for p in pieces]
            rec['n_grown'] = sum(g > 1.01 for g in gs)
            rec['n_shrunk'] = sum(g < 0.99 for g in gs)
            rec['size_min'] = min(gs) if gs else None
            rec['size_mean'] = statistics.mean(gs) if gs else None
            rec['size_max'] = max(gs) if gs else None
            rec['size_sd'] = statistics.pstdev(gs) if len(gs) > 1 else 0.0
            rec['resized_share'] = (sum(abs(g - 1) > 0.01 for g in gs) / len(gs)) if gs else None
            rec.update(size_matching(pieces))
            rec['topping_area_cm2'] = sum(area_cm2(p) for p in pieces)
            rec['n_perishable_included'] = sum(counts.get(k, 0) > 0 for k in per)
            rec['n_never_picked'] = sum(k not in picked for k in tray)
            rec['n_picked_not_kept'] = sum(k in picked and counts.get(k, 0) == 0 for k in tray)
            nev = Counter(e[1] for e in events)
            for k in ('pick', 'add', 'reject', 'tap', 'move', 'remove', 'resize', 'undo', 'clear', 'hover'):
                rec['n_ev_' + k] = nev.get(k, 0)
            rec.update(spatial(pieces, rnd))
            rec.update(order_measures(events))
            rec.update(timing(events, summary))
            rec.update(practice_measures(p_sum, p_ev))
            if rec.get('practice_drag_median') and rec.get('drag_median'):
                rec['drag_vs_practice'] = rec['drag_median'] / rec['practice_drag_median']
            for k in ('pointer', 'coarse', 'layout', 'pizzaPx', 'vw', 'vh', 'dpr', 'hiddenMs', 'hides'):
                rec[k] = summary.get(k)
            rec['diet'] = ' '.join(diet) or None
            rec['diet_other'] = follow.get('dietOther') or None
            health = follow.get('health')
            for h in HEALTH:
                rec['health_' + h] = (int(h in health) if health is not None else None)
            rec['health_any'] = (int(any(h in health for h in HEALTH)) if health is not None else None)
            rec['health_other'] = follow.get('healthOther') or None
            pz = follow.get('pizza') or {}
            for k in PIZZA_ITEMS:
                rec['pz_' + k] = pz.get(k)
            rec['pizza_freq'] = follow.get('freq')
            rec['flag_tab_away'] = int((summary.get('hiddenMs') or 0) > 30000)
            rec['flag_fast'] = int(rec['t_finish'] is not None and rec['t_finish'] < 15000)
            rec['flag_empty'] = int(n == 0)
            ings = ingredient_rows(pid, prefix, summary, events, counts, follow, diet, pieces)
            if follow.get('items'):
                inc = [r['included'] for r in ings]
                norm = [r['norm'] for r in ings]
                rec['norm_incl_corr'] = corr(inc, norm)
                rec['counter_normative'] = sum(1 for r in ings if r['included'] and r['norm'] is not None and r['norm'] <= 3)
                rec['normative_avoided'] = sum(1 for r in ings if not r['included'] and r['norm'] is not None and r['norm'] >= 5)
                dev = [abs(r['included'] - (r['norm'] - 1) / 6) for r in ings if r['norm'] is not None]
                rec['perceived_norm_dev'] = statistics.mean(dev) if dev else None
                rec['like_incl_corr'] = corr(inc, [r['like'] for r in ings])
                rec['disg_incl_corr'] = corr(inc, [r['disg'] for r in ings])
                idents = [r['ident'] for r in ings if r['included'] and r['ident'] is not None]
                rec['ident_mean'] = statistics.mean(idents) if idents else None
                iu = [r['ident'] for r in ings if r['included'] and r['ident'] is not None and r['tier'] == 'unusual']
                rec['ident_mean_unusual'] = statistics.mean(iu) if iu else None
                safe_inc = [r['safe'] for r in ings if r['included'] and r['safe'] is not None]
                rec['safe_mean_included'] = statistics.mean(safe_inc) if safe_inc else None
                norm_inc = [r['norm'] for r in ings if r['included'] and r['norm'] is not None]
                rec['norm_mean_included'] = statistics.mean(norm_inc) if norm_inc else None
            people.append(rec)
            ing_long.extend(ings)
            for e in events:
                ev_long.append({'pid': pid, 'build': prefix.rstrip('_'), 't_ms': e[0], 'type': e[1],
                                'a': e[2] if len(e) > 2 else None, 'b': e[3] if len(e) > 3 else None,
                                'x': e[4] if len(e) > 4 else None, 'y': e[5] if len(e) > 5 else None,
                                'drag_ms': e[6] if len(e) > 6 else None, 'snapped': e[7] if len(e) > 7 else None})
            svgs.append((pid, prefix, pizza_svg(pieces, summary, '%s %s (%d)' % (pid, prefix.rstrip('_'), n))))
            rec['group'] = (row.get(group_col) if group_col else None) or None
            arrangement.append((rec, pieces))

    # deviation from what the rest of the sample actually did (leave-one-out inclusion rates)
    own = [p for p in people if p['build'] == builds[0].rstrip('_')]
    for p in own:
        others = [q for q in own if q['pid'] != p['pid']]
        if not others:
            continue
        rate = {k: sum(q['n_' + k] > 0 for q in others) / len(others) for k in CATS}
        mean_n = {k: statistics.mean(q['n_' + k] for q in others) for k in CATS}
        p['sample_norm_dev'] = statistics.mean(abs(int(p['n_' + k] > 0) - rate[k]) for k in CATS)
        p['sample_count_dev'] = sum(abs(p['n_' + k] - mean_n[k]) for k in CATS)
        mine = [k for k in CATS if p['n_' + k] > 0]
        p['ingredient_rarity'] = statistics.mean(1 - rate[k] for k in mine) if mine else None
        pairs = [(a, b) for i, a in enumerate(mine) for b in mine[i + 1:]]
        if pairs:
            p['combo_rarity'] = statistics.mean(1 - sum(q['n_' + a] > 0 and q['n_' + b] > 0 for q in others) / len(others) for a, b in pairs)
        sets = [{k for k in CATS if q['n_' + k] > 0} for q in others]
        jac = [len(set(mine) & t) / len(set(mine) | t) for t in sets if set(mine) | t]
        p['profile_uniqueness'] = 1 - statistics.mean(jac) if jac else None
    # how normal or unusual each pizza's composition is, against a reference distribution of pizzas
    toppings = []
    for p in own:
        for k in p.get('_tray') or []:
            if k not in toppings:
                toppings.append(k)
    toppings = toppings or list(CATS)
    ext = None
    if ref_rows:
        ext = []
        for r in ref_rows:
            fin = loads(field(r, builds[0] + 'final'))
            if fin is not None:
                ext.append(frozenset(f[1] for f in fin if f[1] in toppings))
    ref_scores, ref_n = normality(own, ext, toppings) if own else ([], 0)
    ref_info = {'scores': ref_scores, 'n': ref_n, 'external': bool(ext), 'toppings': toppings}
    # own pizza versus "a typical participant's" pizza, when both were built
    if len(builds) > 1:
        by = {(p['pid'], p['build']): p for p in people}
        for p in own:
            t = by.get((p['pid'], builds[1].rstrip('_')))
            if not t:
                continue
            a = {k for k in CATS if p['n_' + k] > 0}
            b = {k for k in CATS if t['n_' + k] > 0}
            p['typical_jaccard'] = len(a & b) / len(a | b) if a | b else None
            p['typical_count_dev'] = sum(abs(p['n_' + k] - t['n_' + k]) for k in CATS)
            p['typical_d_pieces'] = p['n_pieces'] - t['n_pieces']
            p['typical_d_distinct'] = p['n_distinct'] - t['n_distinct']

    os.makedirs(os.path.join(out_dir, 'pizzas'), exist_ok=True)
    trays = {id(p): p.pop('_tray', None) for p in people}
    write_csv(os.path.join(out_dir, 'participants.csv'), people)
    write_csv(os.path.join(out_dir, 'ingredients_long.csv'), ing_long)
    write_csv(os.path.join(out_dir, 'events_long.csv'), ev_long)
    cells = []
    for pid, prefix, svg in svgs:
        name = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in '%s_%s' % (pid, prefix.rstrip('_')))
        with open(os.path.join(out_dir, 'pizzas', name + '.svg'), 'w', encoding='utf-8') as f:
            f.write(svg)
        cells.append(svg)
    for rec, _ in arrangement:
        rec['_group'] = rec.get('group') or rec.get('condition') or 'all'
    with open(os.path.join(out_dir, 'arrangement.html'), 'w', encoding='utf-8') as f:
        f.write(arrangement_report(arrangement, group_col or 'condition'))
    for rec, _ in arrangement:
        rec.pop('_group', None)
    for rec, _ in arrangement:
        rec['_group'] = rec.get('group') or rec.get('condition') or 'all'
    own_entries = [e for e in arrangement if e[0]['build'] == builds[0].rstrip('_')]
    with open(os.path.join(out_dir, 'dashboard.html'), 'w', encoding='utf-8') as f:
        f.write(dashboard_report(own_entries, ref_info, group_col or 'condition'))
    prof = profile_analysis(own_entries, k_force)
    for (rec, _), z, lab in zip(own_entries, prof['Z'], prof['labels']):
        rec['cluster'] = lab + 1 if prof['k'] > 1 else None
    with open(os.path.join(out_dir, 'profiles.html'), 'w', encoding='utf-8') as f:
        f.write(profiles_report(own_entries, prof, group_col or 'condition'))
    write_csv(os.path.join(out_dir, 'profiles.csv'), [
        dict([('pid', r['pid']), ('group', r['_group']), ('cluster', r.get('cluster'))] + [('z_' + f[1], round(v, 4)) for f, v in zip(PROFILE_FEATURES, z)])
        for (r, _), z in zip(own_entries, prof['Z'])])
    for rec, _ in arrangement:
        rec.pop('_group', None)
    write_csv(os.path.join(out_dir, 'participants.csv'), people)
    with open(os.path.join(out_dir, 'gallery.html'), 'w', encoding='utf-8') as f:
        f.write('<!doctype html><meta charset="utf-8"><title>Pizza gallery</title>'
                '<body style="font-family:sans-serif;display:flex;flex-wrap:wrap;gap:8px">' + ''.join(cells) + '</body>')
    return people


def write_csv(path, rows):
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r4(v) for k, v in r.items()})


def main():
    if sys.version_info < (3, 10):
        sys.exit('The analysis needs Python 3.10 or newer (this is %d.%d).' % sys.version_info[:2])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('inputs', nargs='+', help='Qualtrics CSV export(s) and/or demo JSON files')
    ap.add_argument('--out', default='pizza_results')
    ap.add_argument('--id', default='PROLIFIC_PID', help='column identifying participants (default PROLIFIC_PID, then ResponseId)')
    ap.add_argument('--builds', default='pz_,pzt_', help='field prefixes of the builds; the first is the participant\'s own pizza')
    ap.add_argument('--seed', type=int, default=1, help='seed for the random layouts behind the symmetry ratios')
    ap.add_argument('--group', default=None, help='column to compare groups by in the reports (e.g. your ASD/NT column); default: condition')
    ap.add_argument('--clusters', type=int, default=None, help='number of clusters (default: chosen by silhouette)')
    ap.add_argument('--reference', nargs='+', default=None, help='pizzas that define "normal" (e.g. a pilot export or demo JSON files); '
                    'default: each pizza is compared with all the others in the sample')
    a = ap.parse_args()
    rows = read_inputs(a.inputs, a.id)
    ref_rows = read_inputs(a.reference, a.id) if a.reference else None
    people = analyse(rows, [b if b.endswith('_') else b + '_' for b in a.builds.split(',') if b], a.out, a.seed, a.group, ref_rows, a.clusters)
    print('%d responses, %d pizzas scored -> %s/' % (len(rows), len(people), a.out))
    if not people:
        print('No pizza fields found. Check that pz_final / __js_pz_final are declared in the survey flow.', file=sys.stderr)


if __name__ == '__main__':
    main()
