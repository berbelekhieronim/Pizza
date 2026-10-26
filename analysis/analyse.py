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
        if e[1] in ('add', 'reject', 'move', 'remove', 'tap', 'grow', 'undo', 'sauce', 'cheese'):
            last_end = e[0]
    fin = next((e[0] for e in events if e[1] == 'finish'), None)
    out['t_first_pick'] = next((e[0] for e in events if e[1] == 'pick'), None)
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
        if e[1] in ('add', 'reject', 'move', 'remove', 'tap', 'grow', 'undo', 'sauce', 'cheese'):
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
    hi = hi if hi is not None else max(allv + ([ref] if ref is not None else [])) * 1.08 or 1
    W, right, row = 640, 20, 34
    left = min(300, 24 + 7 * max(len(str(g)) + 5 for g in groups))
    H = 44 + row * len(groups)
    X = lambda v: left + (min(max(v, lo), hi) - lo) / (hi - lo) * (W - left - right)
    s = ['<svg viewBox="0 0 %d %d" class="dots" role="img" aria-label="%s">' % (W, H, esc(title))]
    for t in range(6):
        v = lo + (hi - lo) * t / 5
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

def r4(v):
    return round(v, 4) if isinstance(v, float) else v


def analyse(rows, builds, out_dir, seed, group_col=None):
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
            gs = [p['g'] for p in pieces]
            rec['n_grown'] = sum(g > 1.01 for g in gs)
            rec['size_mean'] = statistics.mean(gs) if gs else None
            rec['size_max'] = max(gs) if gs else None
            rec['topping_area_cm2'] = sum(area_cm2(p) for p in pieces)
            rec['n_perishable_included'] = sum(counts.get(k, 0) > 0 for k in per)
            rec['n_never_picked'] = sum(k not in picked for k in tray)
            rec['n_picked_not_kept'] = sum(k in picked and counts.get(k, 0) == 0 for k in tray)
            nev = Counter(e[1] for e in events)
            for k in ('pick', 'add', 'reject', 'tap', 'move', 'remove', 'grow', 'undo', 'clear', 'hover'):
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('inputs', nargs='+', help='Qualtrics CSV export(s) and/or demo JSON files')
    ap.add_argument('--out', default='pizza_results')
    ap.add_argument('--id', default='PROLIFIC_PID', help='column identifying participants (default PROLIFIC_PID, then ResponseId)')
    ap.add_argument('--builds', default='pz_,pzt_', help='field prefixes of the builds; the first is the participant\'s own pizza')
    ap.add_argument('--seed', type=int, default=1, help='seed for the random layouts behind the symmetry ratios')
    ap.add_argument('--group', default=None, help='column to compare groups by in arrangement.html (e.g. your ASD/NT column); default: condition')
    a = ap.parse_args()
    rows = read_inputs(a.inputs, a.id)
    people = analyse(rows, [b if b.endswith('_') else b + '_' for b in a.builds.split(',') if b], a.out, a.seed, a.group)
    print('%d responses, %d pizzas scored -> %s/' % (len(rows), len(people), a.out))
    if not people:
        print('No pizza fields found. Check that pz_final / __js_pz_final are declared in the survey flow.', file=sys.stderr)


if __name__ == '__main__':
    main()
