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
        if best is None or ratio < best[0]:
            best = (ratio, k)
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
        overl = 0
        for i in range(n):
            for k in range(i + 1, n):
                a, b = pieces[i], pieces[k]
                lim = (SIZE[a['ing']] * a['s'] + SIZE[b['ing']] * b['s']) * 0.55 / 100
                overl += math.hypot(a['x'] - b['x'], a['y'] - b['y']) < lim
        out['overlap_pairs'] = overl
    out['coverage'] = coverage(pieces)
    out['sym_mirror'], out['sym_rot180'], out['sym_axis_deg'] = symmetry(pieces, rnd)
    out['sym_rot_best'], out['sym_rot_k'] = rot_symmetry(pieces, rnd)
    return out


def coverage(pieces, grid=48):
    """Share of the sauced area (r < 0.86) under a topping, from a grid of sample points."""
    hit = tot = 0
    for i in range(grid):
        for j in range(grid):
            x, y = -0.86 + 1.72 * (i + 0.5) / grid, -0.86 + 1.72 * (j + 0.5) / grid
            if x * x + y * y > 0.86 ** 2:
                continue
            tot += 1
            hit += any(math.hypot(x - p['x'], y - p['y']) < SIZE[p['ing']] * p['s'] * 0.75 / 100 for p in pieces)
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
        if e[1] in ('add', 'reject', 'move', 'remove', 'tap', 'undo', 'sauce', 'cheese'):
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


def ingredient_rows(pid, prefix, summary, events, counts, follow, diet):
    tray = (summary or {}).get('tray') or list(CATS)
    picks, rejects, removes, first_pick, first_add, hover = Counter(), Counter(), Counter(), {}, {}, Counter()
    decide, last_end = {}, None
    for e in events:
        k = e[2] if len(e) > 2 else None
        if e[1] in ('add', 'reject', 'move', 'remove', 'tap', 'undo', 'sauce', 'cheese'):
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


def pizza_svg(pieces, summary, label=''):
    s = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-105 -118 210 225" width="210" height="225" font-family="sans-serif">',
         '<circle r="100" fill="#d9a35a"/>',
         '<circle r="86" fill="%s"/>' % SAUCE.get((summary or {}).get('sauce') or 'none', '#ecd3a0'),
         '<circle r="84" fill="#f6dc8a" opacity="%s"/>' % CHEESE.get((summary or {}).get('cheese') or 'normal', 0.65)]
    for p in pieces:
        size = SIZE.get(p['ing'], 8) * p['s']
        x, y, col = p['x'] * 100, -p['y'] * 100, COLORS.get(p['ing'], '#888')
        if p['ing'] in LONG:
            a, b = LONG[p['ing']]
            s.append('<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="%s" transform="rotate(%d %.1f %.1f)"/>' % (x, y, size * a, size * b, col, p['rot'], x, y))
        elif p['ing'] in ('oli', 'jal'):
            s.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" stroke-width="%.1f"/>' % (x, y, size * 0.7, col, size * 0.45))
        else:
            s.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"/>' % (x, y, size * 0.85, col))
    s.append('<text x="0" y="-106" text-anchor="middle" font-size="10" fill="#333">%s</text></svg>' % label.replace('&', '&amp;').replace('<', '&lt;'))
    return ''.join(s)


# ------------------------------------------------------------------ main

def r4(v):
    return round(v, 4) if isinstance(v, float) else v


def analyse(rows, builds, out_dir, seed):
    rnd = random.Random(seed)
    people, ing_long, ev_long, svgs = [], [], [], []
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
            pieces = [{'id': f[0], 'ing': f[1], 'x': f[2], 'y': f[3], 'rot': f[4], 's': f[5]} for f in final]
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
            rec['n_perishable_included'] = sum(counts.get(k, 0) > 0 for k in per)
            rec['n_never_picked'] = sum(k not in picked for k in tray)
            rec['n_picked_not_kept'] = sum(k in picked and counts.get(k, 0) == 0 for k in tray)
            nev = Counter(e[1] for e in events)
            for k in ('pick', 'add', 'reject', 'tap', 'move', 'remove', 'undo', 'clear', 'hover'):
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
            ings = ingredient_rows(pid, prefix, summary, events, counts, follow, diet)
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
    a = ap.parse_args()
    rows = read_inputs(a.inputs, a.id)
    people = analyse(rows, [b if b.endswith('_') else b + '_' for b in a.builds.split(',') if b], a.out, a.seed)
    print('%d responses, %d pizzas scored -> %s/' % (len(rows), len(people), a.out))
    if not people:
        print('No pizza fields found. Check that pz_final / __js_pz_final are declared in the survey flow.', file=sys.stderr)


if __name__ == '__main__':
    main()
