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
    explore.html         for discovering patterns: every measure and topping screened across every way of grouping people
                         (self-described neurotype, diagnosis status, eating history, gender, age, device, --group columns)
                         and against continuous self-reports (--covariates), ranked by effect size with FDR q-values
    explore.csv          every comparison behind explore.html

Standard library only. Measure definitions are in ../CODEBOOK.md.
"""
import argparse
import bisect
import csv
import hashlib
import json
import math
import os
import random
import shutil
import sqlite3
import statistics
import sys
from collections import Counter

CATS = {'pep': 'meat', 'ham': 'meat', 'chk': 'meat', 'anc': 'seafood', 'mus': 'veg', 'grp': 'veg', 'oni': 'veg',
        'oli': 'veg', 'crn': 'veg', 'pin': 'fruit', 'jal': 'veg', 'bas': 'herb', 'shr': 'seafood', 'egg': 'egg',
        'gor': 'dairy', 'nor': 'seaweed', 'kim': 'veg', 'par': 'fruit', 'ban': 'fruit', 'wal': 'nut',
        'tun': 'seafood', 'kan': 'meat', 'fig': 'fruit'}
NAMES = {'pep': 'Pepperoni', 'ham': 'Ham', 'chk': 'Chicken', 'anc': 'Anchovies', 'mus': 'Mushrooms', 'grp': 'Green pepper',
         'oni': 'Red onion', 'oli': 'Black olives', 'crn': 'Sweetcorn', 'pin': 'Pineapple', 'jal': 'Jalapenos', 'bas': 'Basil',
         'shr': 'Shrimp', 'egg': 'Egg', 'gor': 'Blue cheese', 'nor': 'Nori', 'kim': 'Kimchi', 'par': 'Pear', 'ban': 'Banana', 'wal': 'Walnuts',
         'tun': 'Tuna', 'kan': 'Kangaroo', 'fig': 'Fig'}
# a-priori conventionality (same as the task script); validate it against the sample's own norm ratings
TIER = {'pep': 'common', 'ham': 'common', 'chk': 'common', 'mus': 'common', 'grp': 'common', 'oni': 'common', 'oli': 'common',
        'crn': 'common', 'jal': 'common', 'bas': 'common', 'anc': 'mid', 'pin': 'mid', 'shr': 'mid', 'egg': 'mid', 'gor': 'mid',
        'nor': 'unusual', 'kim': 'unusual', 'par': 'unusual', 'ban': 'unusual', 'wal': 'unusual',
        'tun': 'common', 'kan': 'unusual', 'fig': 'unusual'}
# toppings that spoil quickly or carry a food-safety risk (meat, seafood, egg, soft dairy) - for the dietary-vigilance account
PERISHABLE = {'pep', 'ham', 'chk', 'anc', 'shr', 'egg', 'gor', 'tun', 'kan'}
SIZE = {'pep': 13, 'ham': 10, 'chk': 8.5, 'anc': 15, 'mus': 12, 'grp': 13.5, 'oni': 12.5, 'oli': 6.2, 'crn': 6, 'pin': 8.6,
        'jal': 6, 'bas': 12, 'shr': 9.5, 'egg': 8.5, 'gor': 6.5, 'nor': 9.5, 'kim': 9, 'par': 12, 'ban': 6.5, 'wal': 7, 'tom': 10,
        'tun': 8, 'kan': 11, 'fig': 10}
# each topping's outline as a capsule: half-length along its long axis and half-width, in pizza units before scaling
# (pizza radius = 100 units ~ 15 cm, so 1 unit ~ 1.5 mm). Round toppings have half-length 0.
FOOT = {'pep': (0, 13), 'ham': (1, 6.4), 'chk': (1.5, 6.5), 'anc': (12, 2.8), 'mus': (0, 11), 'grp': (11, 3), 'oni': (10, 2),
        'oli': (0, 6.1), 'crn': (0, 4.7), 'pin': (0, 6.5), 'jal': (0, 5.6), 'bas': (9.5, 5), 'shr': (0, 8), 'egg': (1, 7.2),
        'gor': (0, 5), 'nor': (1.5, 6.3), 'kim': (2, 5.8), 'par': (8, 4), 'ban': (0, 6.2), 'wal': (0.6, 5.8), 'tom': (0, 10),
        'tun': (1, 6), 'kan': (7, 4.2), 'fig': (0, 9)}
MM_PER_UNIT = 1.5
# nutrients per 100 g and grams per standard piece, from USDA SR28 (tools/build_nutrition.py); the task uses the same table
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nutrition.json'), encoding='utf-8') as _f:
    NUTRITION = json.load(_f)
NUTRIENTS = ['kcal', 'protein', 'carbs', 'sugars', 'fat', 'satfat', 'fibre', 'salt', 'vitA', 'vitC', 'vitD', 'vitB12', 'folate', 'calcium', 'iron', 'potassium']
NUT_COL = {k: 'nut_%s%s' % (k, '' if k == 'kcal' else '_' + {'g': 'g', 'mg': 'mg', 'µg': 'ug'}[NUTRITION['units'][k]]) for k in NUTRIENTS}
TOUCH_GAP = 1.0      # units: outlines closer than 1.5 mm count as touching
STACK_DEPTH = 0.5    # outlines overlapping by more than half the thinner piece's half-width count as stacked
MEATS = {'pep', 'ham', 'chk', 'kan'}
# toppings a stated diet usually rules out - lets analyses separate constraint from preference
DIET_EXCLUDES = {
    'vegetarian': MEATS | {'anc', 'shr', 'tun'}, 'vegan': MEATS | {'anc', 'shr', 'tun', 'egg', 'gor'}, 'pescatarian': MEATS,
    'nopork': {'pep', 'ham'}, 'halal': {'pep', 'ham', 'kan'}, 'kosher': {'pep', 'ham', 'shr', 'kan'}, 'nobeef': {'pep'},
    'dairyfree': {'gor'},
}
# what each topping means for a diet. Kimchi is counted as vegan, as many shop brands are; traditional kimchi contains
# fish sauce, so change it to 'seafood' if that matches your stimulus.
DIET_CLASS = {'pep': 'meat', 'ham': 'meat', 'chk': 'meat', 'kan': 'meat', 'anc': 'seafood', 'shr': 'seafood', 'tun': 'seafood',
              'egg': 'vegetarian', 'gor': 'vegetarian'}
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
# the follow-up's default style: strong feelings about an ingredient, then five questions about each one tapped
FEEL_POS, FEEL_NEG = {'love', 'like'}, {'dislike', 'cant'}
ABOUT = ['texture', 'smell', 'taste', 'look', 'touching', 'other']


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
        if path.lower().endswith(('.db', '.sqlite')):         # the study server's database (server/data/study.db)
            con = sqlite3.connect('file:%s?mode=ro' % os.path.abspath(path), uri=True)
            con.row_factory = sqlite3.Row
            for s in con.execute('SELECT * FROM sessions ORDER BY started, pid'):
                d = {k: '' if s[k] is None else str(s[k]) for k in s.keys() if k != 'grp'}
                d['group'] = s['grp'] or ''
                d.update(con.execute('SELECT name, value FROM fields WHERE pid = ?', (s['pid'],)).fetchall())
                d['_pid'] = s['pid']
                rows.append(d)
            con.close()
            continue
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


def face_features(pieces):
    """Groups pieces into features: the same topping when touching (a heap of corn as one eye), different toppings when
    one clearly sits on the other (an olive on a pepperoni: one eye with a pupil). Each feature: member piece indices, centre (area-weighted), equivalent radius, elongation along
    its main axis, that axis, and its main topping. Units are pizza radii."""
    n = len(pieces)
    caps = [capsule(p) for p in pieces]
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i in range(n):
        for j in range(i + 1, n):
            gap = seg_dist(caps[i][0], caps[i][1], caps[j][0], caps[j][1]) - caps[i][2] - caps[j][2]
            same = pieces[i]['ing'] == pieces[j]['ing']
            # the same topping merges when touching (a heap of corn); different toppings only when one clearly sits on the
            # other (a pupil), so an eyebrow that just touches an eye stays separate
            if (same and gap <= 0.01) or gap <= -0.5 * min(caps[i][2], caps[j][2]):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    feats = []
    for members in groups.values():
        areas = []
        for i in members:
            (a1, a2), (b1, b2), w = caps[i]
            h = math.hypot(b1 - a1, b2 - a2) / 2
            areas.append(math.pi * w * w + 4 * h * w)
        A = sum(areas)
        cx = sum(pieces[i]['x'] * ar for i, ar in zip(members, areas)) / A
        cy = sum(pieces[i]['y'] * ar for i, ar in zip(members, areas)) / A
        pts = []                                  # both ends of every member's outline axis
        for i in members:
            pts += [caps[i][0], caps[i][1]]
        sxx = sum((x - cx) ** 2 for x, _ in pts)
        syy = sum((y - cy) ** 2 for _, y in pts)
        sxy = sum((x - cx) * (y - cy) for x, y in pts)
        th = 0.5 * math.atan2(2 * sxy, sxx - syy)
        ux, uy = math.cos(th), math.sin(th)
        wbar = sum(caps[i][2] for i in members) / len(members)
        along = [(x - cx) * ux + (y - cy) * uy for x, y in pts]
        across = [-(x - cx) * uy + (y - cy) * ux for x, y in pts]
        length = max(along) - min(along) + 2 * wbar
        width = max(across) - min(across) + 2 * wbar
        feats.append({'members': members, 'x': cx, 'y': cy, 'r': math.sqrt(A / math.pi), 'elong': length / max(width, 1e-6),
                      'len': length, 'ux': ux, 'uy': uy, 'ing': Counter(pieces[i]['ing'] for i in members).most_common(1)[0][0]})
    return feats


def face_detect(pieces):
    """Looks for a face made of toppings, at any rotation. Touching pieces are first merged into features (see
    face_features), so eyes may be single pieces, pieces with pupils, or small heaps. A face is:
    - two round-ish eyes of similar size (the same topping, or different toppings at a small score penalty),
      0.25-1.3 pizza radii apart, with nothing else close to either eye except eyebrows;
    - below them (in the face's own orientation) a mouth: one long feature lying along the eye line, or an evenly
      spaced row of 3+ features centred under the eyes, following a straight line or a smile, that stops at both ends
      (not part of a longer ring), and does not run straight on from the eyes;
    - at most one nose between eyes and mouth; matching pairs placed symmetrically on the face (eyebrows, cheeks) count
      as part of it; at most one other feature inside the face oval;
    - the face is a main feature: its pieces are at least 30% of the pieces near it and of the whole pizza.
    Returns the best face (piece indices of eyes, mouth, nose, decorations, and a score from 0.6 to 1), or None.
    tests/face_benchmark.py measures it on many kinds of drawn faces and non-faces; check it against human coding of
    a subset of your own pizzas before relying on it."""
    n = len(pieces)
    if n < 3:
        return None
    F = face_features(pieces)
    m = len(F)
    best = None
    cos35 = math.cos(math.radians(35))

    def eye_like(f):
        """A single round piece, a heap of one topping, or a piece with pupils sitting inside it."""
        if f['elong'] > 1.7:
            return False
        mem = f['members']
        if len(mem) == 1:
            return capsule(pieces[mem[0]])[2] > 0 and math.hypot(*[a - b for a, b in zip(*capsule(pieces[mem[0]])[:2])]) / 2 <= 0.03
        if len(mem) > 6:
            return False
        if len({pieces[pc]['ing'] for pc in mem}) == 1:
            return True
        host = max(mem, key=lambda pc: capsule(pieces[pc])[2])
        hw = capsule(pieces[host])[2]
        return all(math.hypot(pieces[pc]['x'] - pieces[host]['x'], pieces[pc]['y'] - pieces[host]['y']) <= hw for pc in mem if pc != host)

    eyes_ok = [eye_like(f) for f in F]
    for i in range(m):
        for j in range(i + 1, m):
            A, B = F[i], F[j]
            if not (eyes_ok[i] and eyes_ok[j]):
                continue
            if max(A['r'], B['r']) / max(1e-6, min(A['r'], B['r'])) > 1.6:
                continue
            same = A['ing'] == B['ing']
            dx, dy = B['x'] - A['x'], B['y'] - A['y']
            d = math.hypot(dx, dy)
            if d < 0.25 or d > 1.3 or d < 1.1 * (A['r'] + B['r']):
                continue
            ux, uy = dx / d, dy / d
            mx, my = (A['x'] + B['x']) / 2, (A['y'] + B['y']) / 2
            for sgn in (1, -1):
                px, py = -uy * sgn, ux * sgn            # points from the eyes towards the mouth
                loc = []                                # (feature, along, perp) in units of d
                for k in range(m):
                    if k not in (i, j):
                        vx, vy = F[k]['x'] - mx, F[k]['y'] - my
                        loc.append((k, (vx * ux + vy * uy) / d, (vx * px + vy * py) / d))
                pos = {k: (al, pp) for k, al, pp in loc}
                # one pair of eyebrows (just above the eyes) and one pair of cheeks (beside the face), each a matching
                # pair placed symmetrically, belong to the face
                def mirrored_pair(zone):
                    found = None
                    for k1, al1, pp1 in loc:
                        for k2, al2, pp2 in loc:
                            if (k1 < k2 and F[k1]['ing'] == F[k2]['ing'] and al1 * al2 < 0 and abs(al1 + al2) <= 0.15
                                    and abs(pp1 - pp2) <= 0.15 and zone(al1, pp1) and zone(al2, pp2)):
                                found = {k1, k2}
                    return found or set()
                brows = mirrored_pair(lambda al, pp: -0.6 <= pp <= -0.1 and abs(abs(al) - 0.5) <= 0.3)
                cheeks = mirrored_pair(lambda al, pp: 0.1 <= pp <= 1.0 and 0.55 <= abs(al) <= 1.1)
                deco = brows | cheeks
                # eyes stand alone: nothing but eyebrows close to either eye
                if any(math.hypot(al - ex, pp) < 0.4 for k, al, pp in loc if k not in brows for ex in (-0.5, 0.5)):
                    continue
                # the mouth is found among single pieces (not merged features): one long piece along the eye line, or an
                # evenly spaced row. Pieces belonging to the eyes or to eyebrows/cheeks are left out.
                taken = set(F[i]['members']) | set(F[j]['members']) | {pc for k in deco for pc in F[k]['members']}
                ploc = []
                for pc, p in enumerate(pieces):
                    if pc not in taken:
                        vx, vy = p['x'] - mx, p['y'] - my
                        ploc.append((pc, (vx * ux + vy * uy) / d, (vx * px + vy * py) / d))
                ppos = {pc: (al, pp) for pc, al, pp in ploc}
                mouth, mouth_al, kind = None, 0.0, ''
                for pc, al, pp in ploc:
                    (a1, a2), (b1, b2), w = capsule(pieces[pc])
                    h = math.hypot(b1 - a1, b2 - a2) / 2
                    if h >= 0.04 and 0.45 <= pp <= 2.2 and abs(al) <= 0.35 and abs(((b1 - a1) * ux + (b2 - a2) * uy) / (2 * h)) >= cos35 \
                            and 2 * (h + w) >= 0.45 * d:
                        mouth, mouth_al, kind = [pc], al, NAMES.get(pieces[pc]['ing'], pieces[pc]['ing'])
                        break
                if mouth is None:
                    cand = sorted((al, pp, pc) for pc, al, pp in ploc if 0.45 <= pp <= 2.2 and abs(al) <= 1.1)
                    cn = len(cand)
                    length, prev = [1] * cn, [-1] * cn
                    for b_ in range(cn):
                        for a_ in range(b_):
                            if 0 < cand[b_][0] - cand[a_][0] <= 0.8 and abs(cand[b_][1] - cand[a_][1]) <= 0.3 and length[a_] + 1 > length[b_]:
                                length[b_], prev[b_] = length[a_] + 1, a_
                    for end in sorted(range(cn), key=lambda e: -length[e]):
                        if length[end] < 3:
                            break
                        chain, c = [], end
                        while c != -1:
                            chain.append(c)
                            c = prev[c]
                        chain.reverse()
                        als = [cand[c][0] for c in chain]
                        pps = [cand[c][1] for c in chain]
                        gaps = [b2 - a2 for a2, b2 in zip(als, als[1:])]
                        even = statistics.pstdev(gaps) <= 0.35 * statistics.mean(gaps)
                        smooth = min(fit_resid(als, pps, 'line'), fit_resid(als, pps, 'smile')) <= 0.08
                        if als[-1] - als[0] >= 0.6 and abs(statistics.mean(als)) <= 0.25 and abs(als[0] + als[-1]) <= 0.35 and even and smooth:
                            mouth, mouth_al = [cand[c][2] for c in chain], statistics.mean(als)
                            kinds = Counter(pieces[pc]['ing'] for pc in mouth)
                            kind = 'row of %d %s' % (len(mouth), '/'.join(NAMES.get(x, x).lower() for x in kinds))
                            break
                if mouth is None:
                    continue
                if len(mouth) > 1:
                    ms = sorted(ppos[pc] for pc in mouth)
                    step = statistics.mean(b2[0] - a2[0] for a2, b2 in zip(ms, ms[1:]))
                    if min(math.hypot(al - ex, pp) for al, pp in ms for ex in (-0.5, 0.5)) < max(0.45, 1.3 * step):
                        continue                        # the eyes run straight on into the mouth: a ring, not a face
                    ends = [min(mouth, key=lambda pc: ppos[pc][0]), max(mouth, key=lambda pc: ppos[pc][0])]
                    mings = {pieces[pc]['ing'] for pc in mouth}
                    eye_pcs = set(F[i]['members']) | set(F[j]['members'])
                    if any(pieces[pc]['ing'] in mings and pc not in mouth and pc not in eye_pcs
                           and math.hypot(pieces[pc]['x'] - pieces[e]['x'], pieces[pc]['y'] - pieces[e]['y']) <= 1.5 * step * d
                           for e in ends for pc in range(n)):
                        continue                        # the row carries on past an end: part of a ring
                mouth_feats = {k for k in range(m) if set(F[k]['members']) & set(mouth)}
                mouth_al_max = max(abs(ppos[pc][0]) for pc in mouth)
                mouth_top = min(ppos[pc][1] for pc in mouth)
                mouth_bottom = max(ppos[pc][1] for pc in mouth)
                used = mouth_feats | deco
                nose = [k for k, al, pp in loc if k not in used and 0.05 <= pp <= mouth_top - 0.1 and abs(al) <= 0.3
                        and len(F[k]['members']) <= 2 and F[k]['r'] <= 1.5 * max(A['r'], B['r'])]
                half_w = max(0.5, mouth_al_max) + 0.35
                top, bottom = -0.35, mouth_bottom + 0.3
                cy, ry = (top + bottom) / 2, (bottom - top) / 2
                clutter = sum(1 for k, al, pp in loc if k not in used and (al / half_w) ** 2 + ((pp - cy) / ry) ** 2 <= 1) - min(1, len(nose))
                if clutter > 1 or (not same and (clutter > 0 or (len(mouth) == 1 and not nose))):
                    continue                            # mismatched eyes need a clean face and a row mouth or a nose
                # the face is a main feature of its surroundings: its pieces are at least 30% of the pieces near it
                face_feats = [i, j] + sorted(mouth_feats) + nose[:1] + sorted(deco)
                face_pieces = {pc for f in face_feats for pc in F[f]['members']}
                fcx = mx + px * d * (mouth_top / 2)
                fcy = my + py * d * (mouth_top / 2)
                near = sum(1 for p in pieces if math.hypot(p['x'] - fcx, p['y'] - fcy) <= 1.4 * d)
                if len(face_pieces) < 0.3 * max(near, 1) or len(face_pieces) < 0.3 * n:
                    continue
                score = 1 - 0.15 * clutter - 0.6 * abs(mouth_al) - (0 if same else 0.1)
                if score >= 0.6 and (best is None or score > best['score']):
                    piece_list = lambda fs: sorted(pc for f in fs for pc in F[f]['members'])
                    best = {'score': score, 'eyes': tuple(piece_list([i]) + piece_list([j])), 'mouth': sorted(mouth),
                            'nose': piece_list(nose[:1]), 'deco': piece_list(sorted(deco)), 'clutter': clutter,
                            'brows': int(bool(brows)), 'cheeks': int(bool(cheeks)), 'eye_topping': A['ing'] if same else A['ing'] + '+' + B['ing'],
                            'mouth_kind': kind, 'up_deg': round(math.degrees(math.atan2(-py, -px))) % 360}
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


def piece_radius(p):
    """Bounding radius of a piece in pizza units (pizza radius = 1), including how much it was resized."""
    return SIZE.get(p['ing'], 8) * p.get('s', 1) / 100


def sym_match(pieces, transform):
    """How many pieces have a symmetric partner: each piece's image under the transform must land on a piece of the
    same topping, within tolerance = half the sum of the two pieces' radii (the image overlaps the partner's middle).
    One-to-one: each piece is used once as a source and once as a partner, closest pairs first. A piece on the axis
    (or at the centre of a rotation) can be its own partner. Returns (matched, matched pairs [(i, j, distance)])."""
    groups = {}
    for i, p in enumerate(pieces):
        groups.setdefault(p['ing'], []).append((i, p['x'], p['y'], piece_radius(p)))
    cand = []
    for g in groups.values():
        for i, x, y, ri in g:
            tx, ty = transform(x, y)
            for j, qx, qy, rj in g:
                d = math.sqrt((tx - qx) ** 2 + (ty - qy) ** 2)
                if d <= 0.5 * (ri + rj):
                    cand.append((d, i, j))
    cand.sort()
    src, dst, pairs = set(), set(), []
    for d, i, j in cand:
        if i not in src and j not in dst:
            src.add(i); dst.add(j); pairs.append((i, j, d))
    return len(pairs), pairs


def mirror_about(cx, cy, phi):
    c, s = math.cos(2 * phi), math.sin(2 * phi)
    return lambda x, y: (cx + c * (x - cx) + s * (y - cy), cy + s * (x - cx) - c * (y - cy))


def mirror(phi):
    return mirror_about(0.0, 0.0, phi)


def rotate_about(cx, cy, a):
    c, s = math.cos(a), math.sin(a)
    return lambda x, y: (cx + c * (x - cx) - s * (y - cy), cy + s * (x - cx) + c * (y - cy))


def sym_centres(pieces):
    """Centres tried for an axis or rotation: the pizza's centre, and the toppings' centroid when it is elsewhere."""
    cx, cy = sum(p['x'] for p in pieces) / len(pieces), sum(p['y'] for p in pieces) / len(pieces)
    return [(0.0, 0.0)] + ([(cx, cy)] if math.sqrt(cx * cx + cy * cy) > 0.02 else [])


def best_mirror(pieces):
    """Best mirror axis: every 3 degrees (0-177) through each centre, then the three best refined in 0.25 degree steps
    (+-1.5 degrees). Better = more matched pieces, then a smaller summed partner distance; on a full tie the earlier
    candidate stays (centres in order, angles ascending). Returns (matched, axis_deg, centre)."""
    def score(c, deg):
        m, pairs = sym_match(pieces, mirror_about(c[0], c[1], math.radians(deg)))
        return m, round(sum(d for _, _, d in pairs), 6)      # rounded so equal axes tie the same way in every language
    better = lambda a, b: a[0] > b[0] or (a[0] == b[0] and a[1] < b[1])
    coarse = [score(c, a) + (a, c) for c in sym_centres(pieces) for a in range(0, 180, 3)]
    top = sorted(coarse, key=lambda t: (-t[0], t[1]))[:3]          # stable: ties keep their order
    best = None
    for _, _, a0, c in top:
        for k in range(-6, 7):
            a = (a0 + 0.25 * k) % 180
            cand = score(c, a) + (a, c)
            if best is None or better(cand, best):
                best = cand
    return best[0], best[2], best[3]


def best_rotation(pieces):
    """Best k-fold rotation, k = 2..8, about each centre. Equal matches go to the higher k (an 8-fold ring is also
    4- and 2-fold). Returns (matched, k, centre)."""
    best = None
    for c in sym_centres(pieces):
        for k in range(2, 9):
            m = sym_match(pieces, rotate_about(c[0], c[1], 2 * math.pi / k))[0]
            if best is None or m > best[0] or (m == best[0] and k > best[1]):
                best = (m, k, c)
    return best


def spacing_floor(pieces):
    """The pizza's own closest spacing: the 10th percentile of its centre-to-nearest-centre distances (0 under 3 pieces)."""
    if len(pieces) < 3:
        return 0.0
    nn = sorted(min(math.hypot(p['x'] - q['x'], p['y'] - q['y']) for q in pieces if q is not p) for p in pieces)
    return nn[int(0.1 * (len(nn) - 1))]


def random_like(pieces, rnd, d0=0.0):
    """The same pieces (topping, size) at random positions on the pizza, no two centres closer than d0 (the pizza's own
    spacing_floor): people spread their toppings out, and a chance level from piled-up random layouts would make even
    spacing look like symmetry. Up to 100 tries per piece, then the last position is kept."""
    out = []
    for p in pieces:
        for _ in range(100):
            r, t = R_VALID * math.sqrt(rnd.random()), rnd.random() * 2 * math.pi
            x, y = r * math.cos(t), r * math.sin(t)
            if all(math.hypot(x - q['x'], y - q['y']) >= d0 for q in out):
                break
        out.append(dict(p, x=x, y=y))
    return out


SYM_NULLS = 12


def symmetry(pieces, rnd):
    """Mirror and rotational symmetry as the share of pieces with a symmetric partner (sym_match), at the best axis /
    rotation, against the share the same pieces get at random positions, spaced like this pizza, with the same search
    (chance, mean of SYM_NULLS layouts). score = (share - chance) / (1 - chance) above chance and (share - chance) / chance below it:
    -1 = nothing matched, 0 = what chance gives, 1 = every piece matched."""
    n = len(pieces)
    if n < 2:
        return {}
    m, axis, mc = best_mirror(pieces)
    r, k, rc = best_rotation(pieces)
    d0 = spacing_floor(pieces)
    fakes = [random_like(pieces, rnd, d0) for _ in range(SYM_NULLS)]
    m0 = statistics.mean(best_mirror(f)[0] for f in fakes) / n
    r0 = statistics.mean(best_rotation(f)[0] for f in fakes) / n
    def score(share, ch):
        if share >= ch:
            return (share - ch) / (1 - ch) if ch < 1 else 0.0
        return (share - ch) / ch
    return {'mirror_match': m / n, 'mirror_chance': m0, 'mirror_score': score(m / n, m0), 'mirror_axis_deg': round(axis, 2),
            'mirror_cx': mc[0], 'mirror_cy': mc[1],
            'rot_match': r / n, 'rot_k': k, 'rot_chance': r0, 'rot_score': score(r / n, r0), 'rot_cx': rc[0], 'rot_cy': rc[1]}


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


MEASURE_CACHE = os.environ.get('PIZZA_MEASURE_CACHE')     # a folder: spatial measures kept between runs (tools/cloud_sync.py)
with open(os.path.abspath(__file__), 'rb') as _f:
    CODE_HASH = hashlib.sha1(_f.read()).hexdigest()[:12]   # a change to this file invalidates the cache


def write_methods(methods, path):
    """The Methods page depends on the code only: with the measure cache, built once per code version and copied."""
    if not MEASURE_CACHE:
        return methods.write(path)
    with open(methods.__file__, 'rb') as f:
        key = hashlib.sha1((CODE_HASH + hashlib.sha1(f.read()).hexdigest()).encode()).hexdigest()[:16]
    cached = os.path.join(MEASURE_CACHE, 'methods-%s.html' % key)
    if not os.path.exists(cached):
        tmp = '%s.%d.tmp' % (cached, os.getpid())
        os.makedirs(MEASURE_CACHE, exist_ok=True)
        methods.write(tmp)
        os.replace(tmp, cached)
    shutil.copyfile(cached, path)


def cached_spatial(pieces, rnd, ident):
    """spatial() of one pizza, read from the measure cache when this exact pizza (pieces, seed, id, build) was measured
    before by this version of the code. The symmetry search is most of the analysis time, and the reports job analyses
    the same pizzas in every study and every run."""
    if not MEASURE_CACHE:
        return spatial(pieces, rnd)
    h = hashlib.sha1(json.dumps([CODE_HASH, ident, pieces], sort_keys=True).encode()).hexdigest()
    path = os.path.join(MEASURE_CACHE, h[:2], h + '.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        pass
    out = spatial(pieces, rnd)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = '%s.%d.tmp' % (path, os.getpid())
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f)
    os.replace(tmp, path)                                     # atomic: parallel runs never read half a file
    return out


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
    out['face_eyes'] = ' + '.join(NAMES.get(k, k) for k in f['eye_topping'].split('+')) if f else None
    out['face_mouth'] = (NAMES.get(f['mouth_kind'], f['mouth_kind']) if f else None)
    out['face_nose'] = (int(bool(f['nose'])) if f else None)
    out['face_up_deg'] = f['up_deg'] if f else None
    out['face_brows'] = f['brows'] if f else None
    out['face_cheeks'] = f['cheeks'] if f else None
    out.update(symmetry(pieces, rnd))
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


def movement_measures(events):
    """How the drags moved (index 9 of add / move / reject / remove events, recorded from task version with movement):
    path in pizza diameters, straightness (straight-line distance / path), pauses of 250 ms+ mid-drag, the longest one,
    dwell (still time before letting go), crossings of the pizza edge, and the hold before the piece first moved."""
    mv = [e[9] for e in events if e[1] in ('add', 'move', 'reject', 'remove') and len(e) > 9 and isinstance(e[9], list) and len(e[9]) >= 7]
    if not mv:
        return {}
    med = lambda i: statistics.median([m[i] for m in mv if m[i] is not None]) if any(m[i] is not None for m in mv) else None
    return {'mv_n': len(mv), 'mv_path': med(0), 'mv_straight': med(1), 'mv_pauses': statistics.mean(m[2] for m in mv),
            'mv_paused_share': sum(m[2] > 0 for m in mv) / len(mv), 'mv_longest_pause': max(m[3] for m in mv),
            'mv_dwell': med(4), 'mv_crossings': statistics.mean(m[5] for m in mv), 'mv_hold': med(6)}


CONSIDER_MS = 500    # a tray topping the mouse rested on this long in total counts as considered


def piece_grams(p):
    """Grams of one piece: the standard piece's grams x (drawn size)^2 (a flat slice: weight follows area)."""
    t = NUTRITION['toppings'].get(p['ing'])
    return t['grams'] * p['s'] ** 2 if t else 0.0


def nutrition_measures(pieces, summary):
    """Nutrients of the whole pizza (toppings + dough + sauce + cheese, as the nutrition panel shows them) and of the
    toppings alone. amount = grams / 100 x the food's amount per 100 g, summed."""
    def add(tot, food, grams):
        if food and food.get('per100') and grams:
            tot['grams'] += grams
            for k in NUTRIENTS:
                tot[k] += food['per100'][k] * grams / 100
    top = dict.fromkeys(NUTRIENTS + ['grams'], 0.0)
    for p in pieces:
        add(top, NUTRITION['toppings'].get(p['ing']), piece_grams(p))
    whole = dict(top)
    B = NUTRITION['base']
    sauce, cheese = (summary or {}).get('sauce') or 'tomato', (summary or {}).get('cheese') or 'normal'
    add(whole, B['dough'], B['dough']['grams'])
    add(whole, B['sauce'].get(sauce), (B['sauce'].get(sauce) or {}).get('grams', 0))
    add(whole, B['cheese'].get(cheese), (B['cheese'].get(cheese) or {}).get('grams', 0))
    out = {NUT_COL[k]: whole[k] for k in NUTRIENTS}
    out.update({'nut_grams': whole['grams'], 'top_grams': top['grams'], 'top_kcal': top['kcal'],
                'top_kcal_share': top['kcal'] / whole['kcal'] if whole['kcal'] else None,
                'nutrition_panel': int(bool((summary or {}).get('nutrition')))})
    return out


NUTRI_SIGHTS = ('nshow', 'nmodal')     # the nutrition shown: "Show nutrition information", or the "I'm done" dialog
NUTRI_SAME_KCAL = 10                   # kcal: a smaller change in the pizza's energy counts as the same energy
NUTRI_DELTAS = ['kcal', 'protein', 'fat', 'satfat', 'sugars', 'salt', 'fibre']
REVEAL_KEYS = (['nutrition_reveal', 'nutri_revealed', 'nutri_n_reveals', 'nutri_first_reveal_ms', 'nutri_reveal_share', 'nutri_open_ms',
                'n_nutri_done_seen', 'n_changed_mind', 'nutri_seen', 'nutri_first_seen_ms', 'nutri_first_seen_how', 'nutri_kcal_at_sight',
                'post_nutri_changed', 'post_nutri_added', 'post_nutri_removed']
               + ['post_nutri_d_' + NUT_COL[k][4:] for k in NUTRI_DELTAS]
               + ['post_nutri_d_%s_pieces' % c for c in ('vegan', 'vegetarian', 'seafood', 'meat')]
               + ['post_nutri_base_changed', 'post_nutri_direction', 'pre_nutri_adds_per_min', 'post_nutri_adds_per_min',
                  'pre_nutri_removal_share', 'post_nutri_removal_share', 'rebuilt_after_done', 'post_done_d_kcal', 'post_done_direction'])


def replay_pieces(events, upto, s_rand):
    """The pieces on the pizza just after events[upto]: {id: {'ing', 's'}}, s = drawn size (random variation x hold-to-resize
    g), following adds, removals, Start over, resizes and every kind of Undo. The random variation is logged with each add
    from 0.13.0 on; for older logs it comes from the finished pizza (pieces removed before the end: 1)."""
    on, gone, cleared, gprev = {}, {}, [], {}
    for e in events[:upto + 1]:
        typ = e[1]
        if typ == 'add' and len(e) > 5:
            on[e[3]] = {'ing': e[2], 's0': e[10] if len(e) > 10 and e[10] else s_rand.get(e[3], 1.0), 'g': e[8] if len(e) > 8 and e[8] else 1}
        elif typ == 'remove' and len(e) > 3 and e[3] in on:
            gone[e[3]] = on.pop(e[3])
        elif typ == 'clear':
            cleared.append(on)
            on = {}
        elif typ in ('resize', 'move') and len(e) > 3 and e[3] in on:
            g = e[4] if typ == 'resize' else (e[8] if len(e) > 8 and e[8] else on[e[3]]['g'])
            gprev.setdefault(e[3], []).append(on[e[3]]['g'])
            on[e[3]]['g'] = g
        elif typ == 'undo' and len(e) > 3:
            act, ref = e[2], e[3]
            if act == 'add':
                on.pop(ref, None)
            elif act == 'remove' and ref in gone:
                on[ref] = gone.pop(ref)
            elif act == 'clear' and cleared:
                on.update(cleared.pop())
            elif act in ('move', 'resize') and ref in on and gprev.get(ref):
                on[ref]['g'] = gprev[ref].pop()
    return {k: {'ing': v['ing'], 's': v['s0'] * v['g']} for k, v in on.items()}


def reveal_measures(events, final, summary):
    """The nutrition-reveal setting (0.13.0): whether, when and how often the participant chose to see the pizza's
    nutrition, whether they went back to building from the "I'm done" dialog ("I changed my mind"), and how the pizza
    changed after they first saw its nutrition. The pizza at that moment comes from replaying the log (replay_pieces) and
    its nutrients from nutrition_measures, with the sauce and cheese logged with the sight; change = final - then."""
    out = dict.fromkeys(REVEAL_KEYS)
    setting = (summary or {}).get('reveal')
    out['nutrition_reveal'] = int(bool(setting))
    if not setting:
        return out
    s_rand = {f[0]: f[5] for f in final}
    final_p = [{'ing': f[1], 's': f[5] * (f[8] if len(f) > 8 else 1)} for f in final]
    base = (summary.get('sauce') or 'tomato', summary.get('cheese') or 'normal')
    nut_final = nutrition_measures(final_p, {'sauce': base[0], 'cheese': base[1]})
    t_end = next((e[0] for e in events if e[1] == 'finish'), events[-1][0] if events else 0)
    shows = [e for e in events if e[1] == 'nshow']
    out.update(nutri_revealed=int(bool(shows)), nutri_n_reveals=len(shows), n_nutri_done_seen=sum(e[1] == 'nmodal' for e in events),
               n_changed_mind=sum(e[1] == 'changemind' for e in events))
    open_ms, t_open = 0, None
    for e in events:
        if e[1] == 'nshow':
            t_open = e[0]
        elif e[1] in ('nhide', 'finish') and t_open is not None:
            open_ms += e[0] - t_open
            t_open = None
    out['nutri_open_ms'] = open_ms
    if shows:
        out['nutri_first_reveal_ms'] = shows[0][0]
        out['nutri_reveal_share'] = shows[0][0] / t_end if t_end else None
    sights = [i for i, e in enumerate(events) if e[1] in NUTRI_SIGHTS]
    out['nutri_seen'] = int(bool(sights))
    if not sights:
        return out

    def state(i):
        e = events[i]
        b = (e[4], e[5]) if len(e) > 5 and e[4] else base
        pcs = list(replay_pieces(events, i, s_rand).values())
        return pcs, b, nutrition_measures(pcs, {'sauce': b[0], 'cheese': b[1]})

    def changed(pcs, b):
        key = lambda ps: sorted((p['ing'], round(p['s'], 4)) for p in ps)
        return int(key(pcs) != key(final_p) or tuple(b) != base)

    def direction(ch, dk):
        return 'unchanged' if not ch else 'lighter' if dk <= -NUTRI_SAME_KCAL else 'heavier' if dk >= NUTRI_SAME_KCAL else 'same energy'

    i = sights[0]
    t0 = events[i][0]
    pcs, b, nut = state(i)
    ch = changed(pcs, b)
    out.update(nutri_first_seen_ms=t0, nutri_first_seen_how='reveal' if events[i][1] == 'nshow' else 'done', nutri_kcal_at_sight=nut['nut_kcal'], post_nutri_changed=ch)
    for k in NUTRI_DELTAS:
        out['post_nutri_d_' + NUT_COL[k][4:]] = nut_final[NUT_COL[k]] - nut[NUT_COL[k]]
    for c in ('vegan', 'vegetarian', 'seafood', 'meat'):
        out['post_nutri_d_%s_pieces' % c] = sum(topping_diet(p['ing']) == c for p in final_p) - sum(topping_diet(p['ing']) == c for p in pcs)
    out['post_nutri_base_changed'] = int(any(e[1] in ('sauce', 'cheese') for e in events[i + 1:]))
    out['post_nutri_direction'] = direction(ch, out['post_nutri_d_kcal'])

    def adds_removals(evs):
        return (sum(e[1] == 'add' for e in evs),
                sum(1 if e[1] == 'remove' or (e[1] == 'undo' and len(e) > 2 and e[2] == 'add') else (e[2] if e[1] == 'clear' and len(e) > 2 and isinstance(e[2], int) else 0) for e in evs))
    a0, r0 = adds_removals(events[:i])
    a1, r1 = adds_removals(events[i + 1:])
    out.update(post_nutri_added=a1, post_nutri_removed=r1,
               pre_nutri_adds_per_min=a0 / (t0 / 60000) if t0 >= 1000 else None,
               post_nutri_adds_per_min=a1 / ((t_end - t0) / 60000) if t_end - t0 >= 1000 else None,
               pre_nutri_removal_share=r0 / a0 if a0 else None, post_nutri_removal_share=r1 / a1 if a1 else None)
    j = next((k for k in sights if events[k][1] == 'nmodal'), None)      # the first "I'm done" dialog
    if j is not None:
        pj, bj, nj = state(j)
        chj = changed(pj, bj)
        out['post_done_d_kcal'] = nut_final['nut_kcal'] - nj['nut_kcal']
        out['post_done_direction'] = direction(chj, out['post_done_d_kcal'])
        out['rebuilt_after_done'] = int(out['n_changed_mind'] > 0 and chj)
    return out


def action_history(events):
    """Replays the log to follow every piece: added, moved, removed (dragged off, undone, or wiped by "Start over")
    and restored (undo of a removal or of "Start over"). Returns (pieces still on the pizza {id: piece},
    removals [dict], moves [dict]). Works with logs from before "clear"/"undo" recorded piece ids (then a cleared
    pizza is restored as a whole)."""
    on, removals, moves, clears = {}, [], [], []
    def remove(pid, t, how):
        pc = on.pop(pid)
        removals.append({'piece_id': pid, 'ing': pc['ing'], 'how': how, 't_added': pc['t'], 't_removed': t,
                         'ms_on_pizza': t - pc['t'], 'x': pc['x'], 'y': pc['y'], 'restored': 0, '_piece': pc})
    for e in events:
        t, typ = e[0], e[1]
        if typ == 'add' and len(e) > 5:
            on[e[3]] = {'ing': e[2], 't': t, 'x': e[4], 'y': e[5]}
        elif typ == 'move' and len(e) > 5 and e[3] in on:
            pc = on[e[3]]
            moves.append({'piece_id': e[3], 'ing': pc['ing'], 't': t, 'dist': math.hypot(e[4] - pc['x'], e[5] - pc['y'])})
            pc['x'], pc['y'] = e[4], e[5]
        elif typ == 'remove' and len(e) > 3 and e[3] in on:
            remove(e[3], t, 'dragged off')
        elif typ == 'clear':
            ids = list(on)
            for pid in ids:
                remove(pid, t, 'start over')
            clears.append(removals[len(removals) - len(ids):])
        elif typ == 'undo' and len(e) > 3:
            act, ref = e[2], e[3]
            if act == 'add' and ref in on:
                remove(ref, t, 'undo')
            elif act == 'remove':
                for r in reversed(removals):
                    if r['piece_id'] == ref and r['how'] == 'dragged off' and not r['restored']:
                        r['restored'] = 1
                        on[ref] = r['_piece']
                        break
            elif act == 'clear' and clears:
                for r in clears.pop():
                    r['restored'] = 1
                    on[r['piece_id']] = r['_piece']
            elif act == 'move' and moves and moves[-1]['piece_id'] == ref:
                moves[-1]['undone'] = 1
    for r in removals:
        r.pop('_piece', None)
    return on, removals, moves


NUDGE = 0.08          # pizza radii (~1.2 cm): a move shorter than this is fine-tuning
ADJ_NULLS = 12        # random moves per real move, for the chance of a symmetry gain
ADJ_COLUMNS = ['pid', 'build', 't', 'piece_id', 'ing', 'kind', 'dist', 'nudge', 'sym_gain_mirror', 'sym_gain_rot', 'sym_gain', 'sym_chance',
               'spacing', 'same_topping_dist_change', 'contacts_change', 'r_before', 'r_after', 'g_before', 'g_after', 'size_match_gain',
               'after_done', 'reason']


def adjustment_measures(events, final, rec, rnd):
    """What each adjustment (a placed piece moved, or resized in place) did. The log is replayed; every move is judged
    against the pizza as it was at that moment:
    - symmetry: change in the number of pieces with a partner (sym_match) at the finished pizza's best mirror axis and
      best rotation; gain > 0 = the move made the pizza more symmetric. Chance: the same piece moved the same distance
      in ADJ_NULLS random directions; sym_chance = share of those that also gain.
    - spacing (+1 if the piece's nearest-neighbour distance moved towards the pizza's median nearest-neighbour
      distance, -1 if away), grouping (change in distance to the nearest piece of the same topping), contacts (change
      in pieces touching it), distance from the centre, and nudge (moved less than NUDGE).
    - resize in place: size_match_gain = 1 if the piece is now within 10% of the size of another piece of the same
      topping and was not before.
    reason = the first that applies: symmetry, grouping, spreading, spacing, unstacking, inward, outward, nudge, other
    (resizes: size match, resize)."""
    s_rand = {f[0]: f[5] for f in final}
    on, rows, gone, cleared, prev = {}, [], {}, [], {}      # prev: piece id -> stack of (x, y, g) before each move / resize
    first_done = next((e[0] for e in events if e[1] == 'done'), None)
    T_m = T_r = None
    if rec.get('mirror_axis_deg') is not None:
        T_m = mirror_about(rec['mirror_cx'], rec['mirror_cy'], math.radians(rec['mirror_axis_deg']))
        T_r = rotate_about(rec['rot_cx'], rec['rot_cy'], 2 * math.pi / rec['rot_k'])
    def plist(state):
        return [{'ing': v['ing'], 'x': v['x'], 'y': v['y'], 's': s_rand.get(k, 1.0) * v['g'], 'rot': 0, 'g': v['g'], '_id': k} for k, v in state.items()]
    def matched(state, T):
        return sym_match(plist(state), T)[0] if T and len(state) > 1 else 0
    def nn(state, pid):
        me = state[pid]
        return min((math.hypot(me['x'] - v['x'], me['y'] - v['y']) for k, v in state.items() if k != pid), default=None)
    def nn_same(state, pid):
        me = state[pid]
        return min((math.hypot(me['x'] - v['x'], me['y'] - v['y']) for k, v in state.items() if k != pid and v['ing'] == me['ing']), default=None)
    def contacts_of(state, pid):
        ps = plist(state)
        me = [p for p in ps if p['_id'] == pid][0]
        a1, b1, w1 = capsule(me)
        n_ = 0
        for p in ps:
            if p is not me:
                a2, b2, w2 = capsule(p)
                n_ += (seg_dist(a1, b1, a2, b2) - w1 - w2) * 100 <= TOUCH_GAP
        return n_
    for e in events:
        typ = e[1]
        if typ == 'add' and len(e) > 5:
            on[e[3]] = {'ing': e[2], 'x': e[4], 'y': e[5], 'g': e[8] if len(e) > 8 and e[8] else 1}
        elif typ == 'remove' and len(e) > 3 and e[3] in on:
            gone[e[3]] = on.pop(e[3])
        elif typ == 'clear':
            cleared.append(on)
            on = {}
        elif typ == 'undo' and len(e) > 3:
            act, ref = e[2], e[3]
            if act == 'add':
                on.pop(ref, None)
            elif act == 'remove' and ref in gone:
                on[ref] = gone.pop(ref)
            elif act == 'clear' and cleared:
                on.update(cleared.pop())
            elif act in ('move', 'resize') and ref in on and prev.get(ref):
                x, y, g = prev[ref].pop()
                on[ref].update(x=x, y=y, g=g)
        elif typ == 'resize' and len(e) > 4 and e[3] in on:
            pc, g_new = on[e[3]], e[4]
            same = [v['g'] for k, v in on.items() if k != e[3] and v['ing'] == pc['ing']]
            hit = lambda g: any(abs(g - h) <= 0.1 * max(g, h) for h in same)
            gain = int(hit(g_new) and not hit(pc['g']))
            rows.append({'t': e[0], 'piece_id': e[3], 'ing': pc['ing'], 'kind': 'resize', 'g_before': pc['g'], 'g_after': g_new, 'size_match_gain': gain,
                         'after_done': int(first_done is not None and e[0] > first_done), 'reason': 'size match' if gain else 'resize'})
            prev.setdefault(e[3], []).append((pc['x'], pc['y'], pc['g']))
            pc['g'] = g_new
        elif typ == 'move' and len(e) > 5 and e[3] in on:
            pid, pc = e[3], on[e[3]]
            before = {k: dict(v) for k, v in on.items()}
            after = {k: dict(v) for k, v in on.items()}
            after[pid].update(x=e[4], y=e[5], g=e[8] if len(e) > 8 and e[8] else pc['g'])
            dist = math.hypot(e[4] - pc['x'], e[5] - pc['y'])
            m0, r0 = matched(before, T_m), matched(before, T_r)
            gm = matched(after, T_m) - m0
            gr = matched(after, T_r) - r0
            gain = max(gm, gr)
            hits = 0
            if T_m and len(on) > 1:
                for _ in range(ADJ_NULLS):
                    for _try in range(20):
                        a = rnd.random() * 2 * math.pi
                        x, y = pc['x'] + dist * math.cos(a), pc['y'] + dist * math.sin(a)
                        if math.hypot(x, y) <= R_VALID:
                            break
                    fake = {k: dict(v) for k, v in before.items()}
                    fake[pid].update(x=x, y=y)
                    hits += matched(fake, T_m) > m0 or matched(fake, T_r) > r0
            others = [nn(before, k) for k in before if k != pid] if len(before) > 2 else []
            med = statistics.median([v for v in others if v is not None]) if others else None
            nb, na = nn(before, pid), nn(after, pid)
            spacing = 0 if med is None or nb is None else (1 if abs(na - med) < abs(nb - med) - 0.01 else -1 if abs(na - med) > abs(nb - med) + 0.01 else 0)
            sb, sa = nn_same(before, pid), nn_same(after, pid)
            dsame = (sa - sb) if sb is not None else None
            dcon = contacts_of(after, pid) - contacts_of(before, pid) if len(before) > 1 else 0
            rb, ra = math.hypot(pc['x'], pc['y']), math.hypot(e[4], e[5])
            if gain > 0:
                reason = 'symmetry'
            elif dsame is not None and dsame < -0.05:
                reason = 'grouping'
            elif dsame is not None and dsame > 0.05:
                reason = 'spreading'
            elif spacing > 0:
                reason = 'spacing'
            elif dcon < 0:
                reason = 'unstacking'
            elif ra < rb - 0.05:
                reason = 'inward'
            elif ra > rb + 0.05:
                reason = 'outward'
            elif dist < NUDGE:
                reason = 'nudge'
            else:
                reason = 'other'
            rows.append({'t': e[0], 'piece_id': pid, 'ing': pc['ing'], 'kind': 'move', 'dist': dist, 'nudge': int(dist < NUDGE),
                         'sym_gain_mirror': gm, 'sym_gain_rot': gr, 'sym_gain': gain, 'sym_chance': hits / ADJ_NULLS if T_m and len(on) > 1 else None,
                         'spacing': spacing, 'same_topping_dist_change': dsame, 'contacts_change': dcon, 'r_before': rb, 'r_after': ra,
                         'g_before': pc['g'], 'g_after': after[pid]['g'], 'after_done': int(first_done is not None and e[0] > first_done), 'reason': reason})
            prev.setdefault(pid, []).append((pc['x'], pc['y'], pc['g']))
            on[pid] = after[pid]
    moves = [r for r in rows if r['kind'] == 'move']
    sym = [r for r in moves if r['sym_gain'] > 0]
    expected = sum(r['sym_chance'] or 0 for r in moves)
    reasons = Counter(r['reason'] for r in rows)
    out = {'n_adjustments': len(rows), 'n_adj_moves': len(moves), 'n_adj_resizes': len(rows) - len(moves),
           'n_adj_nudges': sum(r['nudge'] for r in moves), 'n_adj_symmetry': len(sym), 'n_adj_symmetry_loss': sum(r['sym_gain'] < 0 for r in moves),
           'adj_symmetry_expected': expected if moves else None, 'adj_symmetry_excess': (len(sym) - expected) / len(moves) if moves else None,
           'n_adj_after_done': sum(r['after_done'] for r in rows)}
    for k in ('grouping', 'spreading', 'spacing', 'unstacking', 'inward', 'outward', 'size match'):
        out['n_adj_' + k.replace(' ', '_')] = reasons.get(k, 0)
    out['adj_reasons'] = ' '.join('%s:%d' % kv for kv in sorted(reasons.items())) or None
    return out, rows


def action_measures(events, final):
    """Changes of mind and other actions, per pizza (see the Methods page)."""
    on, removals, moves = action_history(events)
    gone = [r for r in removals if not r['restored']]
    adds = [e for e in events if e[1] == 'add']
    added = Counter(e[2] for e in adds)
    final_ing = Counter(f[1] for f in final)
    dropped = sorted(k for k in added if not final_ing.get(k))
    first_add = adds[0][0] if adds else None
    first_done = next((e[0] for e in events if e[1] == 'done'), None)
    edits = ('add', 'remove', 'move', 'resize', 'undo', 'clear')
    hover, picked = Counter(), {e[2] for e in events if e[1] == 'pick'}
    for e in events:
        if e[1] == 'hover' and len(e) > 3:
            hover[e[2]] += e[3]
    considered = sorted(k for k, ms in hover.items() if ms >= CONSIDER_MS and k not in picked)
    rejected = Counter(e[2] for e in events if e[1] == 'reject')
    lst = lambda c: ' '.join('%s:%d' % kv for kv in sorted(c.items())) or None
    out = {'n_added_pieces': len(adds), 'n_removed_pieces': len(gone),
           'n_removed_dragged': sum(r['how'] == 'dragged off' for r in gone), 'n_removed_undo': sum(r['how'] == 'undo' for r in gone),
           'n_removed_start_over': sum(r['how'] == 'start over' for r in gone), 'n_restored': sum(r['restored'] for r in removals),
           'removed_list': lst(Counter(r['ing'] for r in gone)),
           'revision_rate': len(gone) / len(adds) if adds else None,
           'removal_ms_median': statistics.median([r['ms_on_pizza'] for r in gone if r['how'] != 'start over']) if any(r['how'] != 'start over' for r in gone) else None,
           'n_dropped_toppings': len(dropped), 'dropped_list': ' '.join(dropped) or None,
           'n_start_over': sum(e[1] == 'clear' for e in events), 'n_start_over_declined': sum(e[1] == 'clearno' for e in events),
           'n_moved_pieces': len({m['piece_id'] for m in moves}), 'move_dist_total': sum(m['dist'] for m in moves),
           'n_edits_after_done': sum(e[1] in edits for e in events if first_done is not None and e[0] > first_done),
           'n_sauce_changes': sum(e[1] == 'sauce' for e in events), 'n_cheese_changes': sum(e[1] == 'cheese' for e in events),
           'base_changed_after_toppings': int(any(e[1] in ('sauce', 'cheese') and first_add is not None and e[0] > first_add for e in events)),
           'hover_total_ms': sum(hover.values()), 'n_considered_not_picked': len(considered), 'considered_list': ' '.join(considered) or None,
           'rejected_list': lst(rejected), 'replay_matches_final': int(set(on) == {f[0] for f in final})}
    per = {'added': added, 'removed': Counter(r['ing'] for r in gone), 'moves': Counter(m['ing'] for m in moves),
           'resizes': Counter(e[2] for e in events if e[1] == 'resize'), 'considered': set(considered), 'dropped': set(dropped), 'hover': hover}
    return out, per, removals


AB_NEURO = ['autistic', 'adhd', 'dys', 'otherND', 'none', 'pnts']
AB_EATING = ['picky', 'arfid', 'ed', 'allergy', 'none', 'pnts']


def neurotype(neuro):
    """A grouping from the self-described neurotypes: AuDHD, Autistic, ADHD, Other ND, Not ND, or None (not asked / prefer not)."""
    if not neuro or 'pnts' in neuro:
        return None
    a, d = 'autistic' in neuro, 'adhd' in neuro
    if a and d:
        return 'AuDHD'
    if a:
        return 'Autistic'
    if d:
        return 'ADHD'
    if 'dys' in neuro or 'otherND' in neuro:
        return 'Other ND'
    return 'Not ND' if 'none' in neuro else None


def about_measures(about):
    """The 'About you' card of the follow-up: neurotype (self-described, and how it was identified), eating history,
    two 1-7 self-ratings and demographics. Every column is empty when the card was not shown."""
    if not about:
        return {}
    neuro, dx, eating = about.get('neuro') or [], about.get('dx') or {}, about.get('eating') or []
    out = {'neurotype': neurotype(neuro)}
    out['nd_any'] = None if out['neurotype'] is None else int(out['neurotype'] != 'Not ND')     # any neurodivergence, self-described
    for k in AB_NEURO:
        out['nd_' + k] = int(k in neuro) if neuro else None
    for c in ('autistic', 'adhd'):
        out['dx_' + c] = dx.get(c)
    ids = [dx.get(c) for c in ('autistic', 'adhd') if c in neuro]
    # how the autistic / ADHD identity was established, for checking whether patterns hold with formal diagnoses only
    out['nd_identified'] = None if not ids or 'pnts' in ids or None in ids else ('formal' if all(v == 'formal' for v in ids) else 'self or waiting')
    for k in AB_EATING:
        out['eat_' + k] = int(k in eating) if eating else None
    out['eat_any'] = int(any(k in eating for k in ('picky', 'arfid', 'ed', 'allergy'))) if eating and 'pnts' not in eating else None
    out['self_picky'] = about.get('picky')
    out['self_sensory_food'] = about.get('sensoryfood')
    out['age_band'] = None if about.get('age') in (None, 'pnts') else about.get('age')
    out['gender'] = None if about.get('gender') in (None, 'pnts') else about.get('gender')
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
        ratings = (follow or {}).get('style') != 'strong'     # the 1-7 ratings exist only in the 'ratings' follow-up
        for s in SCALES:
            r[s] = it.get(s) if ratings else None
        r['never_tasted'] = int(bool(it.get('never'))) if (it and ratings) else None
        if (follow or {}).get('style') == 'strong':
            r['strong'] = int(ing in (follow.get('strong') or []))
            r['feel'] = it.get('feel')
            for a in ABOUT:
                r['about_' + a] = (int(a in (it.get('about') or [])) if it else None)
            r['safe_food'], r['same_way'], r['crave'] = it.get('safe'), it.get('sameway'), it.get('crave')
        rs = it.get('reasons')
        for reason in REASONS:
            r['why_' + reason] = (int(reason in rs) if rs is not None else None)
        r['why_other_text'] = it.get('other') or None
        r['rating_ms'] = it.get('ms')
        rows.append(r)
    return rows


PIECE_COLUMNS = ['pid', 'build', 'piece_id', 'ing', 'place_order', 'x', 'y', 'r', 'angle_deg', 'rot', 'g', 's', 'zone',
                 'touching', 'on_top', 'covered', 'pile_depth', 'mirror_matched', 'rot_matched']


def piece_rows(pid, prefix, final, pieces, rec):
    """pieces_long.csv: one row per piece on the finished pizza, with where it is, its size, when it was placed,
    its zone, its contacts, and whether it has a partner at the pizza's best mirror axis / rotation."""
    if not pieces:
        return []
    zones = border_measures(pieces)[1]
    per = contact_measures(pieces)[1] if len(pieces) > 1 else {}
    mm = rm = set()
    if rec.get('mirror_axis_deg') is not None:
        mm = {i for i, _, _ in sym_match(pieces, mirror_about(rec['mirror_cx'], rec['mirror_cy'], math.radians(rec['mirror_axis_deg'])))[1]}
        rm = {i for i, _, _ in sym_match(pieces, rotate_about(rec['rot_cx'], rec['rot_cy'], 2 * math.pi / rec['rot_k']))[1]}
    rows = []
    for i, (f, p) in enumerate(zip(final, pieces)):
        rows.append({'pid': pid, 'build': prefix.rstrip('_'), 'piece_id': f[0], 'ing': p['ing'], 'place_order': f[7] if len(f) > 7 else None,
                     'x': p['x'], 'y': p['y'], 'r': math.hypot(p['x'], p['y']), 'angle_deg': math.degrees(math.atan2(p['y'], p['x'])) % 360,
                     'rot': p['rot'], 'g': p['g'], 's': p['s'], 'zone': zones[i],
                     'touching': int(i in per.get('touching', ())), 'on_top': int(i in per.get('on_top', ())),
                     'covered': int(i in per.get('under', ())), 'pile_depth': per['depth'][i] if per else 1,
                     'mirror_matched': int(i in mm) if len(pieces) > 1 else None, 'rot_matched': int(i in rm) if len(pieces) > 1 else None})
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
          'oni': '#93357a', 'oli': '#25231f', 'crn': '#f2c63a', 'pin': '#f3cf55', 'jal': '#6ea548', 'bas': '#2f7d32', 'tom': '#d8432c',
          'shr': '#ef8a5f', 'egg': '#f6f1df', 'gor': '#d9d6c6', 'nor': '#1f2a1d', 'kim': '#d4542b', 'par': '#e8e2b8', 'ban': '#f5eab8',
          'wal': '#9a6a3c', 'tun': '#bf7a64', 'kan': '#7a2e24', 'fig': '#6b2f5c'}
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


def ghost_panel(pieces, transform, guides):
    """Pizza with, for every piece, a ring where its symmetric partner would have to be: green when sym_match found a
    partner there (the piece counts as matched), red when not."""
    _, pairs = sym_match(pieces, transform)
    matched = {i for i, _, _ in pairs}
    s = ['<svg viewBox="-106 -106 212 212" role="img">', '<circle r="100" class="crust"/><circle r="86" class="sauce"/>', guides]
    s += [glyph(p, ' opacity=".9"') for p in pieces]
    for i, p in enumerate(pieces):
        tx, ty = transform(p['x'], p['y'])
        s.append('<circle class="ghost %s" cx="%.1f" cy="%.1f" r="%.1f"/>' % ('ok' if i in matched else 'miss', tx * 100, -ty * 100, max(capsule(p)[2] * 100 * 0.75, 3)))
    return ''.join(s) + '</svg>'


def mirror_panel(pieces, rec):
    cx, cy, phi = rec.get('mirror_cx') or 0, rec.get('mirror_cy') or 0, math.radians(rec.get('mirror_axis_deg') or 0)
    ex, ey = math.cos(phi) * 150, math.sin(phi) * 150
    guide = ('<clipPath id="cl"><circle r="104"/></clipPath><line class="axis" clip-path="url(#cl)" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>'
             % ((cx - ex / 100) * 100, -(cy - ey / 100) * 100, (cx + ex / 100) * 100, -(cy + ey / 100) * 100))
    return ghost_panel(pieces, mirror_about(cx, cy, phi), guide)


def rotation_panel(pieces, rec):
    k, cx, cy = rec.get('rot_k') or 2, rec.get('rot_cx') or 0, rec.get('rot_cy') or 0
    a = 2 * math.pi / k
    guide = ''.join('<line class="spoke" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (cx * 100, -cy * 100, (cx + math.cos(i * a + math.pi / 2)) * 100,
                                                                                      -(cy + math.sin(i * a + math.pi / 2)) * 100) for i in range(k))
    return ghost_panel(pieces, rotate_about(cx, cy, a), '<clipPath id="cr"><circle r="104"/></clipPath><g clip-path="url(#cr)">%s</g>' % guide)


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


SMALL_N = 5          # groups smaller than this are drawn, but not summarised (no median or quartiles, no percentages)


def quartiles(v):
    """(25th percentile, median, 75th percentile), linear interpolation between order statistics (as R's default, type 7)."""
    v = sorted(v)
    def q(p):
        h = (len(v) - 1) * p
        lo_i = math.floor(h)
        return v[lo_i] + (h - lo_i) * (v[min(lo_i + 1, len(v) - 1)] - v[lo_i])
    return q(.25), q(.5), q(.75)


def dot_plot(title, values, ref=None, ref_label='', lo=0.0, hi=None, fmt='%.2f', unit=''):
    """values: {group: [numbers]}. One row of dots per group (every participant is a dot). Groups of SMALL_N or more
    also get their median (line) and interquartile range (band), written out on the right; smaller groups are only
    drawn. unit names the axis."""
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
    if hi - lo <= 1e-9:                 # every value the same (e.g. all 0): give the axis some width
        lo, hi, step = (lo - 1, lo + 1, None) if lo != 0 else (0.0, 1.0, None)
    W, right, row = 760, 150, 34
    left = min(300, 24 + 7 * max(len(str(g)) + 5 for g in groups))
    H = 44 + row * len(groups) + (16 if unit else 0)
    base = 44 + row * len(groups)
    X = lambda v: left + (min(max(v, lo), hi) - lo) / (hi - lo) * (W - left - right)
    s = ['<svg viewBox="0 0 %d %d" class="dots" role="img" aria-label="%s">' % (W, H, esc(title))]
    n_ticks = max(1, round((hi - lo) / step)) if step else 5
    for t in range(n_ticks + 1):
        v = lo + (hi - lo) * t / n_ticks
        s.append('<line class="grid" x1="%.1f" x2="%.1f" y1="18" y2="%d"/><text class="tick" x="%.1f" y="%d">%s</text>' % (X(v), X(v), base - 20, X(v), base - 6, fmt % v))
    if unit:
        s.append('<text class="tick" x="%.1f" y="%d">%s</text>' % ((left + W - right) / 2, H - 2, esc(unit)))
    if ref is not None:
        s.append('<line class="ref" x1="%.1f" x2="%.1f" y1="14" y2="%d"/><text class="reflabel" x="%.1f" y="12">%s</text>' % (X(ref), X(ref), base - 20, X(ref), esc(ref_label)))
    s.append('<text class="stathead" x="%d" y="12">median (IQR)</text>' % (W - right + 12))
    rnd = random.Random(7)
    for gi, g in enumerate(groups):
        y, v = 34 + gi * row, values[g]
        small = len(v) < SMALL_N
        s.append('<text class="glabel%s" x="%d" y="%.1f">%s <tspan class="n">n=%d</tspan></text>' % (' small' if small else '', left - 10, y + 4, esc(g), len(v)))
        if not small:
            q1, m, q3 = quartiles(v)
            s.append('<rect class="iqr" x="%.1f" y="%.1f" width="%.1f" height="18" rx="3"/>' % (X(q1), y - 9, max(X(q3) - X(q1), 1.5)))
        for x in v:
            s.append('<circle class="dot g0%s" cx="%.1f" cy="%.1f" r="4.5"><title>%s</title></circle>' % (' faint' if small else '', X(x), y + rnd.uniform(-7, 7), fmt % x))
        if small:
            s.append('<text class="stat muted" x="%d" y="%.1f">too few to summarise</text>' % (W - right + 12, y + 4))
        else:
            s.append('<line class="median" x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f"/>' % (X(m), X(m), y - 12, y + 12))
            s.append('<text class="stat" x="%d" y="%.1f">%s (%s–%s)</text>' % (W - right + 12, y + 4, fmt % m, fmt % q1, fmt % q3))
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
.check .ok { color: var(--ok); font-weight: 600; } .check .bad { color: #b3261e; font-weight: 600; } .check li { margin: 4px 0; }
.key .ok { border-color: var(--ok); } .key .near { border-color: var(--near); } .key .miss { border-color: var(--miss); }
.key .ln { width: 18px; height: 0; border-radius: 0; border-width: 2px 0 0; }
figure { margin: 0 0 14px; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; overflow-x: auto; }
figcaption { font-weight: 600; margin-bottom: 4px; }
.dots { width: 100%; min-width: 480px; height: auto; display: block; }
.dots .grid { stroke: var(--line); } .dots .tick { fill: var(--muted); font-size: 11px; text-anchor: middle; font-variant-numeric: tabular-nums; }
.dots .ref { stroke: var(--fg); stroke-dasharray: 4 3; } .dots .reflabel { fill: var(--fg); font-size: 11px; text-anchor: middle; }
.dots .glabel { fill: var(--fg); font-size: 13px; text-anchor: end; } .dots .n { fill: var(--muted); font-size: 11px; }
.dots .dot { fill-opacity: .7; } .g0 { fill: var(--g0); } .g1 { fill: var(--g1); } .g2 { fill: var(--g2); } .g3 { fill: var(--g3); }
.dots .dot.faint { fill-opacity: .35; } .dots .glabel.small { fill: var(--muted); }
.dots .iqr { fill: var(--g0); opacity: .14; }
.dots .median { stroke: var(--fg); stroke-width: 2.5; }
.dots .stat { fill: var(--fg); font-size: 12px; font-variant-numeric: tabular-nums; } .dots .stat.muted { fill: var(--muted); font-size: 11px; }
.dots .stathead { fill: var(--muted); font-size: 11px; }
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
.nv-rev { fill: var(--d-vegan); background: var(--d-vegan); } .nv-done { fill: var(--d-fish); background: var(--d-fish); } .nv-none { fill: var(--line); background: var(--line); }
.dir-lighter { fill: var(--d-vegan); background: var(--d-vegan); } .dir-same { fill: var(--d-veg); background: var(--d-veg); }
.dir-heavier { fill: var(--d-meat); background: var(--d-meat); } .dir-unchanged { fill: var(--line); background: var(--line); }
.toc { position: sticky; top: 0; z-index: 5; background: var(--bg); display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 8px 0; border-bottom: 1px solid var(--line); font-size: .9rem; }
.toc a { color: var(--fg); }
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
        small = n < SMALL_N * 2           # under 10: counts, not percentages
        s.append('<text class="lab" x="%d" y="%d" text-anchor="end">%s <tspan class="val">n=%d</tspan></text>' % (left - 8, y + 15, esc(label), n))
        x = left
        for k, _ in classes:
            w = (W - left - right) * cnt.get(k, 0) / n if n else 0
            if w <= 0:
                continue
            s.append('<rect class="%s" x="%.1f" y="%d" width="%.1f" height="20" rx="2"><title>%s: %d of %d (%d%%)</title></rect>'
                     % (k, x, y, w, dict(classes).get(k, k), cnt[k], n, round(100 * cnt[k] / n)))
            if w > 34:
                s.append('<text class="inbar" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x + w / 2, y + 14, ('%d' % cnt[k]) if small else '%d%%' % round(100 * cnt[k] / n)))
            x += w
    note = '<p class="note">Bars of fewer than %d pizzas show counts instead of percentages. Hover a bar for both.</p>' % (SMALL_N * 2) \
        if any(sum(c.values()) < SMALL_N * 2 for _, c in rows) else ''
    return '<figure><figcaption>%s</figcaption>%s</svg>%s</figure>' % (esc(title), ''.join(s), note)


def strong_feelings_chart(entries, groups):
    """For each ingredient: the share of participants with strong negative (left) and positive (right) feelings about
    it, over everyone who answered; the counts per group are written beside it (only groups that named it)."""
    recs = [r for r, _ in entries if r.get('strong_list') is not None or r.get('strong_none') is not None]
    if not recs:
        return ''
    pos, neg = Counter(), Counter()
    for r in recs:
        for kv in (r.get('strong_list') or '').split():
            k, f = kv.split(':', 1)
            if f in FEEL_POS:
                pos[(r['_group'], k)] += 1
            elif f in FEEL_NEG:
                neg[(r['_group'], k)] += 1
    tot = lambda c, k: sum(c[(g, k)] for g in groups)
    ings = sorted({k for _, k in list(pos) + list(neg)}, key=lambda k: (-(tot(pos, k) + tot(neg, k)), k))
    if not ings:
        return '<p class="note">Nobody reported strong feelings about any ingredient.</p>'
    n = len(recs)
    size = Counter(r['_group'] for r in recs)
    W, left, half, rowh = 900, 150, 140, 22
    top = max(max(tot(pos, k), tot(neg, k)) for k in ings) / n
    X = lambda v: half * v / max(top, 1e-9)
    mid = left + half
    H = 30 + rowh * len(ings)
    s = ['<svg viewBox="0 0 %d %d" class="dots" role="img" aria-label="Strong feelings by ingredient">' % (W, H),
         '<text class="val" x="%.1f" y="12" text-anchor="end">negative &larr;</text>' % (mid - 6),
         '<text class="val" x="%.1f" y="12">&rarr; positive</text>' % (mid + 6),
         '<text class="val" x="%.1f" y="12">by group: negative / positive (group size)</text>' % (mid + half + 70),
         '<line class="grid" x1="%.1f" x2="%.1f" y1="18" y2="%d"/>' % (mid, mid, H)]
    for i, k in enumerate(ings):
        y = 22 + i * rowh
        tn, tp = tot(neg, k), tot(pos, k)
        s.append('<text class="lab" x="%d" y="%.1f" text-anchor="end">%s</text>' % (left - 26, y + 12, esc(NAMES.get(k, k))))
        if tn:
            s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="14" rx="2" class="meat"><title>%d of %d negative</title></rect>' % (mid - X(tn / n), y + 1, X(tn / n), tn, n))
            s.append('<text class="val" x="%.1f" y="%.1f" text-anchor="end">%d</text>' % (mid - X(tn / n) - 4, y + 12, tn))
        if tp:
            s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="14" rx="2" class="vegan"><title>%d of %d positive</title></rect>' % (mid, y + 1, X(tp / n), tp, n))
            s.append('<text class="val" x="%.1f" y="%.1f">%d</text>' % (mid + X(tp / n) + 4, y + 12, tp))
        if len(groups) > 1:
            parts = ['%s %d/%d (%d)' % (g, neg[(g, k)], pos[(g, k)], size[g]) for g in groups if neg[(g, k)] or pos[(g, k)]]
            if len(parts) > 3:
                parts = parts[:3] + ['+%d more' % (len(parts) - 3)]
            s.append('<text class="val" x="%.1f" y="%.1f">%s</text>' % (mid + half + 70, y + 12, esc(' · '.join(parts))))
    return ('<figure><figcaption>Strong feelings about each ingredient (bars: share of the %d participants who answered; numbers: people)</figcaption>%s</svg></figure>'
            % (n, ''.join(s)))


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
    ('mirror_match', 'Mirror match', 'space', '%.2f'), ('mirror_score', 'Mirror score', 'space', '%.2f'), ('rot_score', 'Rotation score', 'space', '%.2f'), ('clark_evans', 'Spread (CE)', 'space', '%.2f'),
    ('coverage', 'Coverage', 'space', '%.2f'), ('prop_touching', 'Touching', 'space', '%.2f'), ('max_stack_depth', 'Pile', 'space', '%d'),
    ('topping_area_cm2', 'Area cm²', 'size', '%.0f'), ('n_grown', 'Enlarged', 'size', '%d'), ('n_shrunk', 'Shrunk', 'size', '%d'), ('size_max', 'Max size', 'size', '%.1f'),
    ('t_first_pick', 'First pick s', 'time', 's'), ('decision_median', 'Decision s', 'time', 's'), ('t_submit', 'Done s', 'time', 's'),
    ('n_strong', 'Strong feelings', 'follow-up', '%d'), ('n_safe_foods', 'Safe foods', 'follow-up', '%d'),
    ('n_on_crust', 'On crust', 'space', '%d'), ('n_over_edge', 'Over edge', 'space', '%d'), ('face_detected', 'Face', 'figurative', '%d'),
]


def nutrition_section(recs, groups):
    """The dashboard's nutrition section: energy of every pizza, and where the nutrition information was offered
    (nutrition_reveal), who looked, who changed their mind, and which way the pizza changed after they first saw it."""
    num = lambda r, k: r.get(k) if isinstance(r.get(k), (int, float)) else None
    vals = lambda k, rs: {g: [num(r, k) for r in rs if r['_group'] == g and num(r, k) is not None] for g in groups}
    out = [dot_plot('Energy of the finished pizza (whole pizza with its base; shown to the participant or not)', vals('nut_kcal', recs), lo=0.0, fmt='%.0f', unit='kcal')]
    offered = [r for r in recs if num(r, 'nutrition_reveal') == 1]
    if not offered:
        return ('<p class="muted">Nutrition information was not offered to anyone here (study setting <code>nutrition_reveal</code>), so there is '
                'nothing on looking or changing; the energy of every pizza is computed anyway.</p>' + ''.join(out))
    gl = [g for g in groups if any(r['_group'] == g for r in offered)]
    rows = [('All', Counter())] + ([(g, Counter()) for g in gl] if len(gl) > 1 else [])
    for r in offered:
        k = 'nv-rev' if num(r, 'nutri_revealed') == 1 else 'nv-done' if (num(r, 'n_nutri_done_seen') or 0) > 0 else 'nv-none'
        for label, c in rows:
            if label in ('All', r['_group']):
                c[k] += 1
    looked = stacked_bars('Did they look? (people offered the nutrition information)', rows,
                          [('nv-rev', 'revealed it while building'), ('nv-done', 'saw it only at "I\'m done"'), ('nv-none', 'never saw it')])
    seen = [r for r in offered if num(r, 'nutri_seen') == 1]
    dirs = [('dir-lighter', 'lighter'), ('dir-same', 'same energy'), ('dir-heavier', 'heavier'), ('dir-unchanged', 'unchanged')]
    drows = [('All', Counter('dir-' + str(r.get('post_nutri_direction')).replace(' energy', '') for r in seen))]
    drows += [(g, Counter('dir-' + str(r.get('post_nutri_direction')).replace(' energy', '') for r in seen if r['_group'] == g)) for g in gl] if len(gl) > 1 else []
    changed = stacked_bars('After first seeing it: what happened to the pizza? (lighter / heavier = more than 10 kcal less / more)', drows, dirs) if seen else ''
    cm = sum(1 for r in offered if (num(r, 'n_changed_mind') or 0) > 0)
    legend = '<div class="legend">%s</div>' % ''.join('<span><i class="%s"></i>%s</span>' % (k, l) for k, l in
                                                      [('nv-rev', 'revealed while building'), ('nv-done', 'saw it only at "I\'m done"'), ('nv-none', 'never saw it')] + dirs)
    out.append(legend + looked + changed)
    if seen:
        out.append(dot_plot('Change in energy after first seeing the nutrition (final pizza minus the pizza at that moment)', vals('post_nutri_d_kcal', seen), fmt='%.0f',
                            unit='kcal', lo=min([0.0] + [num(r, 'post_nutri_d_kcal') or 0 for r in seen])))
    return ('<p class="muted">Offered to %d of %d participants. %d chose "I changed my mind" at the end at least once; %d rebuilt after the end dialog. '
            'Measures and their formulas are on the Methods page (nutri_*, post_nutri_*); explore.html compares people who revealed it with those who did not.</p>'
            % (len(offered), len(recs), cm, sum(1 for r in offered if num(r, 'rebuilt_after_done') == 1)) + ''.join(out))


EXCLUDED_COLUMNS = ['pid', 'build', 'reason', 'stage', 'n_pieces', 'last_saved', 'study']
LATER_STAGES = ('typical', 'followup', 'done')      # a session at one of these has pressed "I'm done" on its own pizza
STAGE_LABELS = [('intro', 'reading the intro'), ('practice', 'practice'), ('build', 'building'), ('typical', 'typical pizza'),
                ('followup', 'questions'), ('done', 'finished')]


def inclusion_choice(row):
    """'include' or 'exclude' when a researcher chose it for this session on the Sessions tab, else '' (automatic)."""
    v = (field(row, 'inclusion') or '').strip()
    return v if v in ('include', 'exclude') else ''


def synthetic_banner(entries):
    """A function that puts a banner under a report's title when synthetic pizzas (analysis/synthetic.py) are in it."""
    n_syn = sum(1 for r, _ in entries if r.get('synthetic'))
    if not n_syn:
        return lambda html: html
    note = ('<p class="verdict" style="border-left-color:#7b3fa0;background:color-mix(in srgb,#7b3fa0 8%%,transparent)"><b>Includes %d synthetic pizzas</b> '
            '(simulated, ids SYN-…) and %d real ones. The synthetic people have known, built-in differences (autistic: fewer and more familiar '
            'toppings, kept apart, in order, more sensory reasons; ADHD: quicker, more changes of mind, more unusual toppings; analysis/synthetic.py), '
            'so the reports should find those: a check that the analysis works, and a preview of what each comparison looks like. '
            'Nothing here describes real people.</p>' % (n_syn, len(entries) - n_syn))
    def add(html):
        i = html.find('</h1>')
        return html if i < 0 else html[:i + 5] + note + html[i + 5:]
    return add


def data_check(rows, builds, people, left_out):
    """Do the sessions and the analysed pizzas add up? Counts for the Data check section and the researcher page."""
    own, typ = builds[0].rstrip('_'), (builds[1].rstrip('_') if len(builds) > 1 else None)
    mine = [p for p in people if p['build'] == own]
    staged = [r for r in rows if r.get('stage')]            # study-server sessions know where the participant got to
    stages = Counter(r['stage'] for r in staged)
    choices = {r['_pid']: inclusion_choice(r) for r in rows}
    out = {'sessions': len(rows), 'own': len(mine), 'typical': sum(p['build'] == typ for p in people),
           'left_out': sum(x['build'] == own for x in left_out), 'left_out_typical': sum(x['build'] == typ for x in left_out),
           'researcher_excluded': sorted(p for p, c in choices.items() if c == 'exclude'),
           'left_out_unfinished': sum(x['build'] == own and x['reason'] == 'not finished' for x in left_out),
           'left_out_researcher': sum(x['build'] == own and x['reason'] != 'not finished' for x in left_out),
           'researcher_included': sorted(p for p, c in choices.items() if c == 'include'),
           'no_pizza': sum(1 for r in rows if loads(field(r, builds[0] + 'final')) is None),
           'stages': {k: stages.get(k, 0) for k, _ in STAGE_LABELS if stages.get(k)},
           'flags': {k: sorted(p['pid'] for p in mine if p.get(k)) for k in ('flag_fast', 'flag_empty', 'flag_tab_away')},
           'restarted': sorted(p['pid'] for p in mine if p.get('restarts')),
           'versions': dict(Counter(str(p.get('task_version') or '?') for p in mine)),
           'test_sessions': sum((r.get('study') or '') == 'tests' for r in rows),
           'synthetic': sum(1 for p in mine if p.get('synthetic'))}
    if staged:
        # the sessions whose own pizza should be in the analysis: past the build, or kept in by the researcher; less those
        # the researcher left out
        has_pizza = {r['_pid'] for r in rows if loads(field(r, builds[0] + 'final')) is not None}
        expected = {r['_pid'] for r in staged if choices[r['_pid']] != 'exclude' and (r['stage'] in LATER_STAGES or (choices[r['_pid']] == 'include' and r['_pid'] in has_pizza))}
        mine_ids = {p['pid'] for p in mine}
        out['built_sessions'] = len(expected)
        out['ok'] = expected == mine_ids and len(staged) == len(rows)
        out['built_without_pizza'] = sorted(expected - mine_ids)
        out['pizza_without_built'] = sorted(mine_ids - expected)
    return out


def data_check_html(c):
    """The Data check section of the overview: where every session went, and what to look at before excluding anything."""
    if not c:
        return ''
    li = lambda s: '<li>%s</li>' % s
    st = ', '.join('%s %d' % (l, c['stages'][k]) for k, l in STAGE_LABELS if c['stages'].get(k))
    items = [li('<b>%d sessions</b> in this data%s.' % (c['sessions'], ('. Where each one is now: ' + esc(st)) if st else ''))] + (
        [li('<b>%d of the analysed pizzas are synthetic</b> (simulated test data, ids SYN-…), %d are real.' % (c['synthetic'], c['own'] - c['synthetic']))]
        if c.get('synthetic') else []) + [
             li('<b>%d own pizzas analysed</b>: everyone who pressed "I\'m done" on their own pizza. Every chart, test and download uses these.' % c['own'])]
    if c['left_out']:
        parts = []
        if c['left_out_unfinished']:
            parts.append('%d saved part-way, but the participant stopped before "I\'m done", so the pizza is not a finished choice' % c['left_out_unfinished'])
        if c['left_out_researcher']:
            parts.append('%d left out by the researcher (%s)' % (c['left_out_researcher'], esc(', '.join(c['researcher_excluded']))))
        items.append(li('<b>%d builds left out</b>: %s. They are listed in <code>excluded.csv</code>; change this per session on the Sessions tab of '
                        'the researcher page.' % (c['left_out'], '; '.join(parts))))
    if c['researcher_included']:
        items.append(li('Kept in by the researcher (overriding the automatic rule): %s.' % esc(', '.join(c['researcher_included']))))
    if c['no_pizza']:
        items.append(li('%d sessions never placed a topping on their own pizza (stopped in the intro or practice, or just opened the link).' % c['no_pizza']))
    if c['typical'] or c['left_out_typical']:
        items.append(li('%d "typical participant" pizzas, analysed as a separate build (column <code>build</code> = pzt), not counted above%s.'
                        % (c['typical'], ('; %d unfinished left out' % c['left_out_typical']) if c['left_out_typical'] else '')))
    if 'ok' in c:
        if c['ok']:
            items.append(li('<span class="ok">✓ Consistent:</span> the analysed own pizzas match the %d sessions that got past the build.' % c['built_sessions']))
        else:
            bad = []
            if c['built_without_pizza']:
                bad.append('past the build but no finished pizza: ' + esc(', '.join(c['built_without_pizza'])))
            if c['pizza_without_built']:
                bad.append('finished pizza but the session is still at an earlier stage: ' + esc(', '.join(c['pizza_without_built'])))
            items.append(li('<span class="bad">✗ Check:</span> %d own pizzas analysed, %d sessions got past the build. %s'
                            % (c['own'], c['built_sessions'], '; '.join(bad))))
    flags = [(k, l) for k, l in (('flag_fast', 'finished in under 15 s'), ('flag_empty', 'no toppings'), ('flag_tab_away', 'tab hidden for over 30 s while building')) if c['flags'][k]]
    review = ['%s: %s' % (l, esc(', '.join(c['flags'][k]))) for k, l in flags]
    if c['restarted']:
        review.append('came back mid-study (reload or new visit), so their build started again: ' + esc(', '.join(c['restarted'])))
    if len(c['versions']) > 1:
        review.append('pizzas from different task versions (%s); see the Changelog for what changed between them'
                      % esc(', '.join('%s: %d' % kv for kv in sorted(c['versions'].items()))))
    if c['test_sessions'] and c['test_sessions'] < c['sessions']:
        review.append('%d sessions from the <code>tests</code> study are mixed in with real ones' % c['test_sessions'])
    if review:
        items.append(li('<b>To review</b> (kept in; decide before the confirmatory analysis whether to exclude, ideally in the preregistration): <ul>%s</ul>'
                        % ''.join(li(r) for r in review)))
    return '<h2 id="check">Data check</h2><ul class="check">%s</ul>' % ''.join(items)


def dashboard_report(entries, ref_info, group_label, check=None):
    recs = [r for r, _ in entries]
    if not recs:
        return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Pizza Data Preview</title></head><body style="font:16px system-ui,sans-serif;max-width:640px;margin:0 auto;padding:24px 16px">'
                '<h1>Pizza data preview</h1><p>No finished pizzas yet.</p>%s</body></html>' % data_check_html(check))
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
    if not unusual:
        bands = ('<p class="note">Percentiles and bands need a reference of at least %d pizzas (here %d): with fewer, "above the 95th percentile" cannot '
                 'be told apart from chance. The surprise in bits above is still shown.</p>' % (NORM_MIN_REF, ref_info['n'] - (0 if ref_info['external'] else 1)))
    examples = ''.join('<div class="card" style="display:flex;gap:12px;align-items:center"><div style="width:90px;flex:none">%s</div><div><b>%s</b> <span class="chip %s">%s · %.0fth percentile</span><div class="note">%s</div></div></div>'
                       % (thumb(p, {}), esc(r['pid']), r['normality_band'], r['normality_band'], r['atypicality_pct'], esc(r.get('unusual_elements') or 'common toppings only'))
                       for r, p in unusual)
    vals = lambda k, scale=1: {g: [r[k] / scale for r in recs if r['_group'] == g and isinstance(r.get(k), (int, float))] for g in groups}
    space = (dot_plot('Mirror symmetry score (0 = chance, 1 = every piece has a mirror partner)', vals('mirror_score'), 0.0, 'chance', lo=-0.5, hi=1.0, unit='score (0 = chance level)') +
             dot_plot('Spread: Clark-Evans ratio (<1 clustered, >1 evenly spaced)', vals('clark_evans'), 1.0, 'random', unit='ratio') +
             dot_plot('Share of the pizza covered by toppings', vals('coverage'), lo=0.0, hi=1.0, unit='share of the pizza (0–1)') +
             dot_plot('Share of pieces touching another piece', vals('prop_touching'), lo=0.0, hi=1.0, unit='share of pieces (0–1)'))
    size = (dot_plot('Total topping area (cm² on a 30 cm pizza)', vals('topping_area_cm2'), lo=0.0, fmt='%.0f', unit='cm²') +
            dot_plot('Number of pieces', vals('n_pieces'), lo=0.0, fmt='%.0f', unit='pieces') +
            dot_plot('Size matching: share of resized pieces sized like another piece of the same topping', vals('size_match_same'), lo=0.0, hi=1.0, unit='share of resized pieces (0–1)') +
            dot_plot('Mean piece size (1 = normal; holding a topping pulses it between 0.5 and 2.5)', vals('size_mean'), lo=0.5, hi=2.5, fmt='%.1f', unit='size (1 = normal)'))
    time_ = (dot_plot('Median decision time, seconds (end of one action to picking up the next topping)', vals('decision_median', 1000), lo=0.0, fmt='%.1f', unit='seconds') +
             dot_plot('Total build time, seconds (time on other tabs removed)', vals('t_active', 1000), lo=0.0, fmt='%.0f', unit='seconds') +
             dot_plot('Time to first topping, seconds', vals('t_first_pick', 1000), lo=0.0, fmt='%.1f', unit='seconds') +
             dot_plot('Time to completion: confirmed "I\'m done", seconds', vals('t_submit', 1000), lo=0.0, fmt='%.0f', unit='seconds'))
    feel_plots = (dot_plot('Ingredients with strong feelings, per participant', vals('n_strong'), lo=0.0, fmt='%.0f', unit='ingredients') +
                  dot_plot('Sensory reasons given (texture, smell, taste, look, touching other food)', vals('n_sensory_reasons'), lo=0.0, fmt='%.0f', unit='reasons') +
                  dot_plot('"Safe foods" among them', vals('n_safe_foods'), lo=0.0, fmt='%.0f', unit='ingredients'))
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
            '<h1>Overview</h1><p class="muted">%d pizzas, compared by <code>%s</code>. Every number comes from the recorded coordinates, sizes and timestamps; '
            'formulas are on the Methods page. Charts are descriptive: every participant is a dot, groups of 5 or more get a median and interquartile range '
            '(the middle half). Tests between groups are on the Explore page.</p><div class="kpis">%s</div>'
            '<nav class="toc"><a href="#check">Data check</a><a href="#diet">Diet</a><a href="#nutrition">Nutrition</a><a href="#normal">How normal</a><a href="#feelings">Strong feelings</a>'
            '<a href="#space">Space</a><a href="#size">Size and amount</a><a href="#time">Time</a><a href="#people">Every participant</a></nav>%s'
            '<h2 id="diet">Diet: vegan, vegetarian, pescatarian or meat</h2><p class="muted">Each topping has a diet class; cheese and white sauce count as dairy, so a vegan '
            'pizza needs no cheese. A pizza is classed by the strictest diet it fits.</p>%s%s%s%s'
            '<h2 id="nutrition">Nutrition</h2>%s'
            '<h2 id="normal">How normal is each pizza?</h2><p class="muted">Two things are compared with the reference (%s). <b>Which toppings</b>: how surprising '
            'the set of toppings is given how often each topping appears; adding a rare topping or leaving off a near-universal one both add surprise (in bits, plotted below). '
            '<b>How many</b>: how extreme the number of different toppings is, in either direction, so a plain pizza or one with everything stands out. '
            'Each becomes a percentile of the reference, and the band uses the more extreme of the two: under 75 is <b>typical</b>, 75-95 <b>uncommon</b>, above 95 <b>unusual</b>.</p>'
            '<figure><figcaption>Which toppings: surprise of the topping set in bits (bars = reference, dots = this sample, line = median)</figcaption>%s</figure>%s'
            '<h3>Most unusual pizzas</h3><div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))">%s</div>'
            '<h2 id="feelings">Strong feelings</h2><p class="muted">From the follow-up: which ingredients people have strong feelings about, and why '
            '(texture, smell, taste, look, touching other food), whether they are safe foods, must be a certain way, or are craved.</p>%s%s'
            '<h2 id="space">Space</h2>%s<h2 id="size">Size and amount</h2>%s<h2 id="time">Time</h2>%s'
            '<h2 id="people">Every participant</h2><p class="muted">Click a column to sort.</p><div class="tablewrap"><table class="people"><thead>%s</thead><tbody>%s</tbody></table></div>'
            '</div>%s</body></html>'
            % (REPORT_CSS, DASH_TOKENS, DASH_CSS, len(recs), esc(group_label), kpis, data_check_html(check), legend, diet, pieces, cross, nutrition_section(recs, groups),
               esc(ref_txt), hist, bands, examples, strong_feelings_chart(entries, groups), feel_plots, space, size, time_, head, ''.join(body), sort_js))


def fmtv(v, f='%.2f'):
    return '-' if v is None else (f % v if isinstance(v, float) else str(v))


def arrangement_report(entries, group_label):
    """entries: list of (record, pieces). Returns the HTML of the symmetry and contact report."""
    by_group = {}
    for rec, _ in entries:
        by_group.setdefault(str(rec.get('_group') or 'all'), []).append(rec)
    def vals(key):
        return {g: [r[key] for r in rs if isinstance(r.get(key), (int, float))] for g, rs in by_group.items()}
    plots = (dot_plot('Mirror symmetry score (0 = chance, 1 = every piece has a mirror partner)', vals('mirror_score'), 0.0, 'chance', lo=-0.5, hi=1.0, unit='score (0 = chance level)') +
             dot_plot('Pieces with a mirror partner (share)', vals('mirror_match'), lo=0.0, hi=1.0, unit='share of pieces (0–1)') +
             dot_plot('Rotational symmetry score (best of 2- to 8-fold; 0 = chance, 1 = every piece matched)', vals('rot_score'), 0.0, 'chance', lo=-0.5, hi=1.0, unit='score (0 = chance level)') +
             dot_plot('Share of pieces touching another piece', vals('prop_touching'), lo=0.0, hi=1.0, unit='share of pieces (0–1)') +
             dot_plot('Share of pieces stacked on or under another piece', vals('prop_stacked'), lo=0.0, hi=1.0, unit='share of pieces (0–1)') +
             dot_plot('Tallest pile (layers; 1 = nothing stacked)', vals('max_stack_depth'), lo=1.0, fmt='%.1f', unit='layers'))
    cards = []
    for rec, pieces in sorted(entries, key=lambda e: (e[0].get('mirror_score') is None, -(e[0].get('mirror_score') or 0))):
        if len(pieces) < 2:
            continue
        head = '<h3>%s <span>%s · %s · %d pieces</span></h3>' % (esc(rec['pid']), esc(rec['build']), esc(rec.get('_group') or ''), rec['n_pieces'])
        n = rec['n_pieces']
        p1 = ('<div class="panel">%s<b>Mirror: %d of %d pieces matched (%.0f%%)</b><div class="v">chance %.0f%% · score %s · axis %.1f°</div></div>'
              % (mirror_panel(pieces, rec), round(rec['mirror_match'] * n), n, 100 * rec['mirror_match'], 100 * rec['mirror_chance'], fmtv(rec.get('mirror_score')), rec['mirror_axis_deg']))
        p2 = ('<div class="panel">%s<b>%d-fold rotation: %d of %d matched (%.0f%%)</b><div class="v">chance %.0f%% · score %s</div></div>'
              % (rotation_panel(pieces, rec), rec['rot_k'], round(rec['rot_match'] * n), n, 100 * rec['rot_match'], 100 * rec['rot_chance'], fmtv(rec.get('rot_score'))))
        p3 = ('<div class="panel">%s<b>Contact and stacking</b><div class="v">%s touching pairs · %s stacked pairs · tallest pile %s · median gap %s mm</div></div>'
              % (contact_panel(pieces), fmtv(rec.get('n_touch_pairs')), fmtv(rec.get('n_stack_pairs')), fmtv(rec.get('max_stack_depth')), fmtv(rec.get('nn_gap_mm'), '%.1f')))
        cards.append('<section class="card">%s<div class="panels">%s%s%s</div></section>' % (head, p1, p2, p3))
    key = ('<div class="key"><span><i class="ok"></i>a piece of the same topping is there (matched)</span>'
           '<span><i class="miss"></i>none there (not matched)</span><span><i class="ok ln" style="border-color:var(--axis)"></i>mirror axis / rotation spokes</span>'
           '<span><i class="ln" style="border-color:var(--near)"></i>touching</span><span><i class="ln" style="border-color:var(--miss);border-top-width:3px"></i>stacked (dashed ring = piece on top)</span></div>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<title>Pizza Arrangement Report</title><style>%s</style></head><body><div class="wrap">'
            '<h1>Pizza arrangement: symmetry and contact</h1>'
            '<p class="muted">Each ring marks where a topping would have to be for the pizza to be perfectly symmetric: reflected across the best mirror axis, '
            'or turned by the best rotation. Green: a piece of the same topping lies there (within half the two pieces\' combined radius; each piece '
            'partners one other), so the piece counts as matched. The share of green rings is the match; chance is the share the same pieces get at random '
            'positions with the same search; score = (match − chance) / (1 − chance), so 0 is no more symmetric than chance and 1 is every piece matched. '
            'Full definitions are on the Methods page. The contact panel joins pieces whose outlines touch or overlap; faded pieces touch nothing, and a number gives the '
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


NORM_MIN_REF = 20      # reference pizzas before percentiles and bands are given: "above the 95th percentile" needs 20+


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
        n_ref = len(ref) if ref_sets_external else len(ref) - 1
        below = sum(x < bits for x in ref_scores) + 0.5 * sum(x == bits for x in ref_scores)
        comp = 100 * below / len(ref_scores) if ref_scores and n_ref >= NORM_MIN_REF else None
        sizes = [len(r) for r in ref] if ref_sets_external else [len(r) for j, r in enumerate(ref) if j != i]
        cnt, same = count_extremeness(len(sets[i]), sizes) if n_ref >= NORM_MIN_REF else (None, None)
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
# trait (e.g. even spacing uses -nn_cv, because a lower variation is more even). 'log' = log(1 + x) first.
PROFILE_FEATURES = [
    ('Composition', 'n_pieces', 'Pieces', 'log', 1), ('Composition', 'n_distinct', 'Different toppings', None, 1),
    ('Composition', 'shannon', 'Variety', None, 1), ('Composition', 'prop_unusual_distinct', 'Unusual toppings', None, 1),
    ('Composition', 'diet_rank', 'Animal products', None, 1),
    ('Normality', 'atypicality_bits', 'Unusual combination', None, 1),
    ('Space', 'mirror_score', 'Mirror symmetry', None, 1), ('Space', 'rot_score', 'Rotational symmetry', None, 1),
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
    ('Feelings', 'n_strong', 'Strong feelings about toppings', None, 1), ('Feelings', 'n_sensory_reasons', 'Sensory reasons given', None, 1),
    ('Process', 'revision_rate', 'Changes of mind', None, 1), ('Process', 'adj_symmetry_excess', 'Moves for symmetry (beyond chance)', None, 1),
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


CLUSTER_MIN_N = 20         # types are searched for only with this many pizzas


def null_cloud(Z, vals, vecs, rnd):
    """One dataset with no types but the profiles' own correlations and each measure's own values (a Gaussian copula):
    correlated normal scores Y = Σ √λ g v, then each column takes the observed values of that measure in the order of
    its scores. Skewed, capped or zero-heavy measures split more easily than a bell-shaped cloud, so a plain normal null
    would let such data pass as "clustered"."""
    n, p = len(Z), len(Z[0])
    g = [[rnd.gauss(0, 1) for _ in range(p)] for _ in range(n)]
    Y = [[sum(math.sqrt(max(vals[c], 0)) * g[i][c] * vecs[c][a] for c in range(p)) for a in range(p)] for i in range(n)]
    for a in range(p):
        obs = sorted(Z[i][a] for i in range(n))
        for rank, i in enumerate(sorted(range(n), key=lambda i: Y[i][a])):
            Y[i][a] = obs[rank]
    return Y


# Cluster discovery: are there types of pizza-makers, in all the measures together or in one family of them? Each
# family is searched the same way and must beat CLUSTER_NULLS no-types datasets; the threshold is divided by the number
# of families tried (Bonferroni), so trying four searches does not make finding something four times easier.
CLUSTER_FAMILIES = [('all', 'All measures', None),
                    ('behaviour', 'Build behaviour (order, timing, changes of mind)', ('Order', 'Time', 'Process')),
                    ('preferences', 'Preferences (toppings, unusualness, feelings)', ('Composition', 'Normality', 'Feelings')),
                    ('arrangement', 'Arrangement (space, size, faces)', ('Space', 'Size', 'Figurative'))]
CLUSTER_ALPHA = 0.05
CLUSTER_NULLS = round(len(CLUSTER_FAMILIES) / CLUSTER_ALPHA) - 1     # 79: p = 1 / 80 = .0125 = .05 / 4 when no null split is as good
CLUSTER_TEST_MAX = 200     # larger samples are tested on a random 200 (the null splits take n³ time); everyone is still clustered


def search_types(Z, cols, rnd, ks):
    """One family: Ward clusters of the profile columns cols, the best k by silhouette, and the test against no-types
    datasets (null_cloud). Stops drawing nulls as soon as the family can no longer pass. Returns a dict."""
    n = len(Z)
    X = [[row[c] for c in cols] for row in Z]
    merges = ward(X)
    dist = [[euclid(X[i], X[j]) for j in range(n)] for i in range(n)]
    sil = {k: silhouette(X, cut(merges, n, k), dist) for k in ks}
    k = max(sil, key=lambda kk: (sil[kk] or -1))
    idx = sorted(rnd.sample(range(n), CLUSTER_TEST_MAX)) if n > CLUSTER_TEST_MAX else list(range(n))
    T = [X[i] for i in idx]
    m = len(T)
    if len(idx) < n:                                      # the observed split of the tested sample, for a fair comparison
        dT = [[euclid(T[i], T[j]) for j in range(m)] for i in range(m)]
        mT = ward(T)
        best = max((silhouette(T, cut(mT, m, kk), dT) or -1) for kk in ks)
    else:
        best = sil[k] if sil[k] is not None else -1
    p = len(cols)
    C = [[sum(T[i][a] * T[i][b] for i in range(m)) / (m - 1) for b in range(p)] for a in range(p)]
    vals, vecs = jacobi_eig(C)
    alpha = CLUSTER_ALPHA / len(CLUSTER_FAMILIES)
    nulls, hits = [], 0
    for _ in range(CLUSTER_NULLS):
        Y = null_cloud(T, vals, vecs, rnd)
        dY, mY = [[euclid(Y[i], Y[j]) for j in range(m)] for i in range(m)], ward(Y)
        v = max((silhouette(Y, cut(mY, m, kk), dY) or -1) for kk in ks)
        nulls.append(v)
        hits += v >= best
        if (1 + hits) / (1 + CLUSTER_NULLS) > alpha:      # cannot pass any more
            break
    pv = (1 + hits) / (1 + len(nulls))
    found = hits == 0 and len(nulls) == CLUSTER_NULLS
    return {'cols': cols, 'k': k, 'sil': sil, 'best_sil': sil[k], 'labels': cut(merges, n, k), 'merges': merges, 'dist': dist,
            'nulls': nulls, 'p': pv, 'found': found, 'early': len(nulls) < CLUSTER_NULLS, 'tested': m}


def discover_types(Z, ks):
    """Every family of CLUSTER_FAMILIES searched for types: {family id: search_types result}."""
    out = {}
    for fid, label, areas in CLUSTER_FAMILIES:
        cols = [i for i, f in enumerate(PROFILE_FEATURES) if areas is None or f[0] in areas]
        if len(cols) >= 2:
            out[fid] = dict(search_types(Z, cols, random.Random('types:' + fid), ks), label=label)
    return out


def profile_analysis(entries, k_force=None):
    """Profiles, distances, Ward clusters, PCA, and the search for types (discover_types). Clusters of all the measures
    are 'valid' (reported as types) only when that family passes its test; --clusters forces a number, shown as such."""
    recs = [r for r, _ in entries]
    Z = build_profiles(recs)
    n = len(Z)
    out = {'Z': Z, 'labels': [0] * n, 'k': 1, 'sil': {}, 'order': list(range(n)), 'merges': [], 'pcs': None, 'valid': False, 'best_sil': None,
           'families': {}, 'forced': bool(k_force)}
    if n < 4:
        return out
    ks = range(2, min(6, n - 1) + 1)
    if n >= CLUSTER_MIN_N:
        out['families'] = discover_types(Z, ks)
        al = out['families']['all']
        merges, dist, sil = al['merges'], al['dist'], al['sil']
    else:
        merges = ward(Z)
        dist = [[euclid(Z[i], Z[j]) for j in range(n)] for i in range(n)]
        sil = {k: silhouette(Z, cut(merges, n, k), dist) for k in ks}
    k = k_force or max(sil, key=lambda kk: (sil[kk] or -1))
    valid = bool(k_force) or bool(out['families'] and out['families']['all']['found'])
    out.update({'labels': cut(merges, n, k) if valid else [0] * n, 'k': k if valid else 1, 'sil': sil, 'order': leaf_order(merges, n), 'merges': merges,
                'dist': dist, 'valid': valid, 'best_sil': sil.get(k), 'best_k': k})
    p = len(Z[0])
    C = [[sum(Z[i][a] * Z[i][b] for i in range(n)) / (n - 1) for b in range(p)] for a in range(p)]
    vals, vecs = jacobi_eig(C)
    tot = sum(v for v in vals if v > 0) or 1
    out['pcs'] = {'var': [vals[0] / tot, vals[1] / tot], 'vecs': vecs[:2],
                  'xy': [[sum(Z[i][a] * vecs[c][a] for a in range(p)) for c in range(2)] for i in range(n)]}
    return out


def null_words(prof):
    """The test of the clusters of all the measures, in words."""
    f = (prof.get('families') or {}).get('all')
    if not f:
        return 'no test was run'
    return ('the best split (k = %d, silhouette %.2f) %s the best split of %s %d datasets with no types but the same measures and correlations '
            '(theirs: %.2f to %.2f; p = %.3f, needed ≤ %.4f)' % (f['k'], f['best_sil'] or 0, 'beats' if f['found'] else 'does not beat',
                                                               'each of' if f['found'] else 'all', len(f['nulls']), min(f['nulls']), max(f['nulls']), f['p'],
                                                               CLUSTER_ALPHA / len(CLUSTER_FAMILIES)))


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


# total time is left out: it mostly counts the pieces (more toppings take longer), so it would only re-find the amount
BEHAVIOUR_KEYS = [f[1] for f in PROFILE_FEATURES if f[0] in ('Order', 'Time', 'Process') and f[1] != 't_submit']
PREFERENCE_KEYS = [f[1] for f in PROFILE_FEATURES if f[0] in ('Composition', 'Normality', 'Feelings')]


def discovery_html(recs, prof):
    """profiles.html: the search for types in each family of measures, the types found (with how neurodivergent and not
    neurodivergent people spread across them), and how build behaviour goes with preferences."""
    fams = prof.get('families') or {}
    n = len(recs)
    names = {f[1]: f[2] for f in PROFILE_FEATURES}
    alpha = CLUSTER_ALPHA / len(CLUSTER_FAMILIES)
    if not fams:
        table = '<p class="note">The search needs at least %d pizzas (here %d).</p>' % (CLUSTER_MIN_N, n)
    else:
        rows = []
        for fid, f in fams.items():
            verdict = ('<b class="ok">types found</b>' if f['found'] else
                       'no types: a no-types dataset split %s' % ('at least as well (stopped after %d)' % len(f['nulls']) if f['early'] else 'as well'))
            rows.append('<tr><td class="l">%s<br><span class="muted">%d measures</span></td><td>%d</td><td>%.2f</td><td>%.2f – %.2f</td><td>%s</td><td class="l">%s</td></tr>'
                        % (esc(f['label']), len(f['cols']), f['k'], f['best_sil'] or 0, min(f['nulls']), max(f['nulls']),
                           ('%.3f' % f['p']) if not f['early'] else '&gt; %.4f' % alpha, verdict))
        table = ('<div class="tbl"><table class="leads"><tr><th class="l">Searched in</th><th>best k</th><th>silhouette</th><th>no-types datasets</th><th>p</th>'
                 '<th class="l">result</th></tr>%s</table></div>' % ''.join(rows))
    # the types found in each family (other than all the measures, whose clusters are shown below in full)
    found = []
    for fid, f in fams.items():
        if not f['found'] or fid == 'all':
            continue
        lab, k = f['labels'], f['k']
        cards = []
        for c in range(k):
            idx = [i for i in range(n) if lab[i] == c]
            means = [statistics.mean(prof['Z'][i][col] for i in idx) for col in f['cols']]
            top = sorted(range(len(f['cols'])), key=lambda j: -abs(means[j]))[:4]
            nd = Counter('ND' if recs[i].get('nd_any') else 'not ND' if recs[i].get('nd_any') == 0 else 'not stated' for i in idx)
            cards.append('<div class="cl-card"><h3><span class="sw" style="background:%s"></span>Type %d <span class="muted" style="font-weight:400">%d pizzas</span></h3>'
                         '<p style="margin:0 0 6px">%s.</p><p class="note">%s</p></div>'
                         % (CLUSTER_COLORS[c % 8], c + 1, len(idx), esc(', '.join('%s %s (%+.1f SD)' % ('more' if means[j] > 0 else 'less',
                                                                                                          PROFILE_FEATURES[f['cols'][j]][2].lower(), means[j]) for j in top)),
                            esc(' · '.join('%s: %d' % kv for kv in sorted(nd.items())))))
        res = cluster_group_test([l + 1 for l in lab], ['yes' if r.get('nd_any') else 'no' if r.get('nd_any') == 0 else None for r in recs], ['yes', 'no'], random.Random(2))
        nd_txt = ('Neurodivergent vs not: χ² = %.2f, permutation p = %s.' % (res[1], fmt_p(res[2]))) if res else 'Too few people with a stated neurotype to test.'
        found.append('<h3>%s: %d types</h3><div class="cl-cards">%s</div><p class="note">%s Types were found without using the groups.</p>'
                     % (esc(f['label']), k, ''.join(cards), nd_txt))
    # build behaviour × preferences
    pairs = []
    for b in BEHAVIOUR_KEYS:
        for pk in PREFERENCE_KEYS:
            xs = [r.get(b) if isinstance(r.get(b), (int, float)) else None for r in recs]
            ys = [r.get(pk) if isinstance(r.get(pk), (int, float)) else None for r in recs]
            rho, pv, m = spearman(xs, ys)
            if rho is not None:
                pairs.append((b, pk, rho, pv, m))
    for i, q in enumerate(bh([x[3] for x in pairs])):
        pairs[i] = pairs[i] + (q,)
    top = sorted(pairs, key=lambda x: (x[3], -abs(x[2])))[:10]
    corr = ('<div class="tbl"><table class="leads"><tr><th class="l">Build behaviour</th><th class="l">Preference</th><th>n</th><th>ρ</th><th>p</th><th>q</th></tr>%s</table></div>'
            % ''.join('<tr%s><td class="l">%s</td><td class="l">%s</td><td>%d</td><td><b>%+.2f</b></td><td>%s</td><td>%.3f%s</td></tr>'
                      % (' class="pass"' if q < 0.1 else '', esc(names[b]), esc(names[pk]), m, rho, fmt_p(pv), q, ' ✓' if q < 0.1 else '')
                      for b, pk, rho, pv, m, q in top)) if top else '<p class="note">Too few pizzas.</p>'
    return ('<h2 id="types">Searching for types</h2><p class="muted">Are there distinct <i>types</i> of pizza-makers, rather than people spread along '
            'continuous dimensions? Each family of measures is clustered (Ward\'s method, the number of clusters with the best average silhouette) and '
            'compared with %d datasets that have no types but the same values of each measure and the same correlations between them, clustered the '
            'same way (stopping early once a family cannot pass). Four searches are tried, so a family counts only at p ≤ %.4f (.05 / 4). Clustering '
            'always returns groups; this is what keeps it from inventing them.</p>%s%s'
            '<h2 id="behaviour-preferences">Build behaviour and preferences</h2><p class="muted">How the way people build goes with what they choose: '
            'Spearman ρ between each build-behaviour measure (%s) and each preference measure (%s), %d pairs, q = Benjamini-Hochberg over them. '
            'The ten best supported:</p>%s'
            % (CLUSTER_NULLS, alpha, table, ''.join(found), esc(', '.join(names[k].lower() for k in BEHAVIOUR_KEYS)),
               esc(', '.join(names[k].lower() for k in PREFERENCE_KEYS)), len(pairs), corr))


CLUSTER_COMPARE_JS = """<script>
var D = %s;
(function () {
  var sa = document.getElementById('ca'), sb = document.getElementById('cb');
  D.clusters.forEach(function (c, i) { var l = 'Cluster ' + c.id + ' (' + c.n + ' pizzas)'; sa.add(new Option(l, i)); sb.add(new Option(l, i)); });
  sb.selectedIndex = 1;
  function bar(z, cls) { var w = Math.min(50, Math.abs(z) / 3 * 50); return '<i class="' + cls + '" style="left:' + (z < 0 ? 50 - w : 50) + '%%;width:' + w + '%%"></i>'; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function show() {
    var A = D.clusters[sa.value], B = D.clusters[sb.value];
    var order = D.features.map(function (f, i) { return i; }).sort(function (i, j) { return Math.abs(B.mean[j] - A.mean[j]) - Math.abs(B.mean[i] - A.mean[i]); });
    document.getElementById('bars').innerHTML = order.map(function (i) {
      var d = A.mean[i] - B.mean[i];
      return '<tr><td class="lab">' + esc(D.features[i][1]) + ' <span class="muted">' + (d >= 0 ? '+' : '−') + Math.abs(d).toFixed(1) + '</span></td>'
        + '<td><div class="pbar">' + bar(A.mean[i], 'a') + bar(B.mean[i], 'b') + '</div></td></tr>';
    }).join('');
    document.getElementById('pzs').innerHTML = '<figure><div style="color:var(--g0);font-weight:600">Cluster ' + A.id + ' · ' + A.n + '</div><div class="thumbs">' + A.svg + '</div><div class="note">' + esc(A.groups) + '</div></figure>'
      + '<figure><div style="color:var(--g1);font-weight:600">Cluster ' + B.id + ' · ' + B.n + '</div><div class="thumbs">' + B.svg + '</div><div class="note">' + esc(B.groups) + '</div></figure>';
    var top = order.slice(0, 3).map(function (i) { return (A.mean[i] > B.mean[i] ? 'more ' : 'less ') + D.features[i][1].toLowerCase() + ' (' + Math.abs(A.mean[i] - B.mean[i]).toFixed(1) + ' SD)'; });
    document.getElementById('diff').textContent = sa.value === sb.value ? 'Pick two different clusters.' : 'Cluster ' + A.id + ', compared with cluster ' + B.id + ': ' + top.join(', ') + '.';
  }
  sa.onchange = show; sb.onchange = show; show();
})();
</script>"""


def profiles_report(entries, prof, group_label):
    recs = [r for r, _ in entries]
    n = len(recs)
    if n < 4:
        return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Pizza Profiles</title></head><body style="font:16px system-ui,sans-serif;max-width:640px;margin:0 auto;padding:24px 16px">'
                '<h1>Profiles and clusters</h1><p>These need at least 4 finished pizzas; there %s %d so far. The dashboard and the '
                'symmetry report already work.</p></body></html>' % ('is' if n == 1 else 'are', n))
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
    # cluster x group: a permutation test (the groups shuffled across people), only for real clusters
    cross = ''
    res = cluster_group_test([labels[i] + 1 for i in range(n)], [recs[i]['_group'] for i in range(n)], groups, random.Random(1)) if prof['valid'] and len(groups) > 1 else None
    if res:
        tab, chi, pval = res
        cross = ('<figure><figcaption>Clusters by %s</figcaption><table class="cross"><tr><th>Cluster</th>%s</tr>%s</table>'
                 '<p class="note">χ² = %.2f, permutation p = %s (2000 shuffles of the groups across people). This tests whether the groups spread differently '
                 'across the clusters; the clusters were found without using the groups.</p></figure>'
                 % (esc(group_label), ''.join('<th>%s</th>' % esc(g) for g in groups),
                    ''.join('<tr><td><span class="sw" style="background:%s"></span> %d</td>%s</tr>' % (CLUSTER_COLORS[c % 8], c + 1, ''.join('<td>%d</td>' % v for v in tab[c])) for c in range(k)),
                    chi, fmt_p(pval)))
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
    # data for the in-page comparison of two clusters
    clist = []
    for c in range(k):
        idx = [i for i in range(n) if labels[i] == c]
        means = [statistics.mean(Z[i][f] for i in idx) for f in range(len(PROFILE_FEATURES))]
        near = sorted(idx, key=lambda i: euclid(Z[i], means))[:3]
        gc = Counter(recs[i]['_group'] for i in idx)
        clist.append({'id': c + 1, 'n': len(idx), 'mean': [round(v, 3) for v in means], 'groups': ' · '.join('%s: %d' % (g, gc.get(g, 0)) for g in groups),
                      'svg': ''.join(thumb(entries[i][1], {}) for i in near)})
    data = {'features': [[f[0], f[2]] for f in PROFILE_FEATURES], 'clusters': clist, 'colors': CLUSTER_COLORS}
    script = '' if k < 2 else (CLUSTER_COMPARE_JS % json.dumps(data))
    compare = '' if k < 2 else ('<h2>Compare two clusters</h2><div class="compare"><div class="pick"><label for="ca"><b style="color:var(--g0)">Cluster A</b></label><select id="ca"></select>'
               '<label for="cb"><b style="color:var(--g1)">Cluster B</b></label><select id="cb"></select><div class="pz" id="pzs"></div><p class="note" id="diff"></p></div>'
               '<div><table class="pbars" id="bars"></table><p class="note">Each cluster\'s average profile, ordered by how much the two differ (the number: '
               'A − B, in standard deviations). Bars run from the sample average (centre line) towards less (left) or more (right) of each trait. The pizzas '
               'shown are the three closest to each cluster\'s average.</p></div></div>')
    if prof['valid'] and prof.get('forced'):
        intro_cl = ('Profiles are grouped with hierarchical clustering (Ward\'s method) into %d clusters, a number fixed by hand (--clusters). Mean silhouette %.2f; %s.'
                    % (k, prof['best_sil'] or 0, null_words(prof)))
        clusters_html = compare + '<h2>Clusters</h2><div class="cl-cards">%s</div>%s' % (''.join(cards), cross)
    elif prof['valid']:
        intro_cl = ('Profiles are grouped with hierarchical clustering (Ward\'s method) into %d clusters, the number with the best average silhouette (%s). '
                    'They are reported because %s.' % (k, esc(sil), null_words(prof)))
        clusters_html = compare + '<h2>Clusters</h2><div class="cl-cards">%s</div>%s' % (''.join(cards), cross)
    else:
        intro_cl = ''
        clusters_html = ('<h2>Clusters</h2><p class="verdict">No clear clusters: %s. Hierarchical clustering always splits people into groups, wanted or '
                         'not, so a split is reported only when it is better than the best split of %d datasets drawn from a single cloud of people with '
                         'the same correlations between the measures (no types), clustered the same way. People can still differ a lot along continuous '
                         'dimensions: the map and the table below show how.</p>' % (null_words(prof) if prof.get('families') else
                                                                                   'it takes at least %d pizzas (here %d)' % (CLUSTER_MIN_N, n), CLUSTER_NULLS))
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<title>Pizza Profiles</title><style>%s%s%s</style></head><body><div class="wrap">'
            '<h1>Pizza profiles and clusters</h1>'
            '<p class="muted">Each participant\'s pizza is summarised as a profile of %d measures in %d areas. Each score is standardised across these %d '
            'participants (0 = sample average, ±1 = one standard deviation) and signed so that higher always means <i>more</i> of the named trait. %s</p>'
            '%s%s%s'
            '<h2>All profiles</h2><p class="muted">One row per participant, ordered by the clustering tree; the coloured band is the cluster. '
            'Orange = above the sample average, blue = below.</p>%s'
            '</div>%s</body></html>'
            % (REPORT_CSS, DASH_CSS, PROFILE_CSS, len(PROFILE_FEATURES), len({f[0] for f in PROFILE_FEATURES}), n, intro_cl, discovery_html(recs, prof), clusters_html, scatter, heat, script))


def bar_style(z):
    w = min(50.0, abs(z) / 3 * 50)
    return 'left:%.1f%%;width:%.1f%%' % (50 - w if z < 0 else 50, w)


def r4(v):
    return round(v, 4) if isinstance(v, float) else v


# ------------------------------------------------------------------ exploration

# Measures screened in explore.html beyond the profile measures: (area, key, label).
EXPLORE_EXTRA = [
    ('Composition', 'meat_or_fish', 'Any meat or fish'), ('Composition', 'n_categories', 'Food categories'),
    ('Composition', 'evenness', 'Even amounts of each topping'), ('Normality', 'ingredient_rarity', 'Rare toppings (in this sample)'),
    ('Normality', 'profile_uniqueness', 'Unlike the other pizzas'), ('Space', 'angular_regularity', 'Even angles round the centre'),
    ('Figurative', 'face_detected', 'Made a face'),
    ('Process', 'n_ev_move', 'Moves'), ('Process', 'n_ev_remove', 'Removals'), ('Process', 'n_ev_undo', 'Undos'),
    ('Process', 'n_ev_reject', 'Dropped off the pizza'), ('Process', 'n_never_picked', 'Toppings never touched'),
    ('Process', 'n_picked_not_kept', 'Toppings tried, then left off'), ('Process', 'n_done_presses', "Presses of I'm done"),
    ('Process', 't_after_done', "Time between I'm done and submitting"),
    ('Process', 'n_removed_pieces', 'Pieces removed (not restored)'), ('Process', 'n_dropped_toppings', 'Toppings added, then left off'),
    ('Process', 'n_start_over', 'Start overs'), ('Process', 'n_start_over_declined', 'Start over opened, then declined'),
    ('Adjustments', 'n_adjustments', 'Adjustments (moves and resizes of placed pieces)'), ('Adjustments', 'n_adj_symmetry', 'Moves that made the pizza more symmetric'),
    ('Adjustments', 'adj_symmetry_excess', 'Symmetry-making moves beyond chance (per move)'), ('Adjustments', 'n_adj_nudges', 'Nudges (moves under 1.2 cm)'),
    ('Adjustments', 'n_adj_grouping', 'Moves towards the same topping'), ('Adjustments', 'n_adj_spacing', 'Moves that evened the spacing'),
    ('Adjustments', 'n_adj_unstacking', 'Moves that separated pieces'), ('Adjustments', 'n_adj_size_match', 'Resizes that matched another piece'),
    ('Adjustments', 'n_adj_after_done', "Adjustments after the first I'm done"),
    ('Process', 'n_moved_pieces', 'Pieces moved'), ('Process', 'move_dist_total', 'Distance pieces were moved'),
    ('Process', 'n_edits_after_done', "Edits after the first I'm done"), ('Process', 'base_changed_after_toppings', 'Sauce or cheese changed after toppings'),
    ('Nutrition', 'nut_kcal', 'Energy, whole pizza'), ('Nutrition', 'top_kcal', 'Energy from toppings'), ('Nutrition', 'top_grams', 'Weight of toppings'),
    ('Nutrition', 'top_kcal_share', 'Share of energy from toppings'), ('Nutrition', 'nut_protein_g', 'Protein'), ('Nutrition', 'nut_satfat_g', 'Saturated fat'),
    ('Nutrition', 'nut_sugars_g', 'Sugars'), ('Nutrition', 'nut_fibre_g', 'Fibre'), ('Nutrition', 'nut_salt_g', 'Salt'),
    ('Nutrition', 'nut_vitC_mg', 'Vitamin C'), ('Nutrition', 'nut_vitA_ug', 'Vitamin A'),
    ('Seeing nutrition', 'nutri_revealed', 'Revealed the nutrition while building'), ('Seeing nutrition', 'nutri_reveal_share', 'How far into building they revealed it'),
    ('Seeing nutrition', 'nutri_open_ms', 'Time the nutrition table was open'), ('Seeing nutrition', 'n_changed_mind', '"I changed my mind" at the end'),
    ('Seeing nutrition', 'post_nutri_changed', 'Pizza changed after seeing the nutrition'), ('Seeing nutrition', 'post_nutri_d_kcal', 'Energy change after seeing the nutrition'),
    ('Seeing nutrition', 'post_nutri_d_satfat_g', 'Saturated fat change after seeing it'), ('Seeing nutrition', 'post_nutri_d_meat_pieces', 'Meat pieces change after seeing it'),
    ('Seeing nutrition', 'post_nutri_removal_share', 'Removals per add after seeing it'), ('Seeing nutrition', 'rebuilt_after_done', 'Rebuilt after the end dialog'),
    ('Process', 'n_considered_not_picked', 'Toppings considered (hovered), never picked'), ('Process', 'hover_total_ms', 'Time resting on tray toppings'),
    ('Movement', 'mv_straight', 'Direct drags'), ('Movement', 'mv_pauses', 'Pauses per drag'), ('Movement', 'mv_paused_share', 'Drags with a pause'),
    ('Movement', 'mv_dwell', 'Dwell before letting go'), ('Movement', 'mv_hold', 'Hold before moving'),
    ('Movement', 'mv_crossings', 'Crossings of the pizza edge'), ('Movement', 'mv_path', 'Drag path length'),
    ('Feelings', 'n_strong_positive', 'Strong positive feelings'), ('Feelings', 'n_strong_negative', 'Strong negative feelings'),
    ('Feelings', 'n_safe_foods', 'Safe foods named'), ('Feelings', 'n_same_way', 'Foods that must be a certain way'),
    ('Feelings', 'n_crave_often', 'Foods often craved'), ('Feelings', 'n_about_texture', 'Texture reasons'),
    ('Feelings', 'n_about_smell', 'Smell reasons'), ('Feelings', 'n_about_touching', '"Touching other food" reasons'),
    ('Feelings', 'strong_neg_on_pizza', 'Disliked toppings still used'),
]
# Ways of grouping people that explore.html tries when present: (key, label).
EXPLORE_GROUPINGS = [
    ('neurotype', 'Neurotype (self-described)'), ('nd_any', 'Any neurodivergence (yes / no)'), ('nd_autistic', 'Autistic, incl. AuDHD (yes / no)'), ('nd_adhd', 'ADHD, incl. AuDHD (yes / no)'),
    ('nd_identified', 'Autism / ADHD: formally diagnosed or not'), ('eat_any', 'Any eating difficulty, allergy or intolerance (yes / no)'),
    ('eat_picky', 'Picky eating since childhood (yes / no)'), ('gender', 'Gender'), ('age_band', 'Age'),
    ('nutrition_panel', 'Nutrition panel shown (yes / no)'), ('nutri_revealed', 'Revealed the nutrition while building (yes / no)'), ('group', 'Recruitment group (study link)'), ('source', 'Recruitment source'), ('study', 'Study'), ('condition', 'Condition'),
]
EXPLORE_COVARIATES = [('self_picky', '"I am a picky eater" (1-7)'), ('self_sensory_food', '"Food textures, smells or looks bother me" (1-7)')]


def midranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def cliff_delta(x, y):
    """Cliff's delta: P(a value from x > one from y) - P(<). -1..1; 0 = no difference. For yes/no measures it is the
    difference in percentages (as a proportion)."""
    if not x or not y:
        return None
    ys = sorted(y)
    m = len(ys)
    return sum(bisect.bisect_left(ys, v) - (m - bisect.bisect_right(ys, v)) for v in x) / (len(x) * m)


_PERM_CACHE, _SUBSETS = {}, {}


def mw_p(r1, all_ranks, n1, tie_term, rnd):
    """Two-sided p for the rank sum of n1 values out of n (Mann-Whitney): a permutation test (4000 draws) when a group
    is small, otherwise the normal approximation with the tie correction."""
    n = len(all_ranks)
    n2 = n - n1
    mu = n1 * (n + 1) / 2
    if min(n1, n2) < 8:
        # the null distribution of the rank sum depends only on n1 and the ranks (without ties: 1..n), so it is drawn
        # once per (n1, ranks) and reused by every test that shares them
        # (|R - mu| is the same for a group and its complement, so the smaller side is summed; the random index subsets
        # are drawn once per (n, size) and shared by every measure)
        k = min(n1, n2)
        key = (k, tuple(sorted(all_ranks)))
        null = _PERM_CACHE.get(key)
        if null is None:
            subs = _SUBSETS.get((n, k))
            if subs is None:
                subs = _SUBSETS[(n, k)] = [rnd.sample(range(n), k) for _ in range(4000)]
            mu_k = k * (n + 1) / 2
            null = _PERM_CACHE[key] = sorted(abs(sum(all_ranks[i] for i in sub) - mu_k) for sub in subs)
        hits = len(null) - bisect.bisect_left(null, abs(r1 - mu) - 1e-9)
        return (hits + 1) / 4001
    var = n1 * n2 / 12 * ((n + 1) - tie_term / (n * (n - 1)))
    if var <= 0:
        return 1.0
    z = max(0.0, abs(r1 - mu) - 0.5) / math.sqrt(var)
    return math.erfc(z / math.sqrt(2))


def bh(ps):
    """Benjamini-Hochberg q-values (false discovery rate) for a list of p-values (None stays None)."""
    idx = sorted((i for i, p in enumerate(ps) if p is not None), key=lambda i: ps[i])
    q = [None] * len(ps)
    m, run = len(idx), 1.0
    for rank in range(m, 0, -1):
        i = idx[rank - 1]
        run = min(run, ps[i] * m / rank)
        q[i] = run
    return q


def boot_ci(x, y, rnd, B=600):
    """95% percentile bootstrap interval for Cliff's delta, resampling within each group."""
    if set(x) | set(y) <= {0, 1}:                     # yes/no: delta is the difference in proportions
        ds = sorted(sum(rnd.choice(x) for _ in x) / len(x) - sum(rnd.choice(y) for _ in y) / len(y) for _ in range(B))
    else:
        ds = sorted(cliff_delta([rnd.choice(x) for _ in x], [rnd.choice(y) for _ in y]) for _ in range(B))
    return ds[int(0.025 * B)], ds[int(0.975 * B) - 1]


def spearman(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if isinstance(x, (int, float)) and isinstance(y, (int, float))]
    if len(pairs) < 5:
        return None, None, len(pairs)
    rx, ry = midranks([p[0] for p in pairs]), midranks([p[1] for p in pairs])
    rho = corr(rx, ry)
    if rho is None:
        return None, None, len(pairs)
    n = len(pairs)
    if abs(rho) >= 1:
        return rho, 0.0, n
    t = rho * math.sqrt((n - 2) / (1 - rho * rho))
    return rho, t_sf2(abs(t), n - 2), n


def t_sf2(t, df):
    """Two-sided p of Student's t (regularised incomplete beta by continued fraction)."""
    x = df / (df + t * t)
    a, b = df / 2, 0.5
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a if 0 < x < 1 else (0.0 if x <= 0 else 1.0)
    if not 0 < x < 1:
        return front
    f, c, d = 1.0, 1.0, 1 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > 1e-30 else 1e-30)
    f = d
    for m in range(1, 200):
        for num in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)), -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1 + num * d
            d = 1 / (d if abs(d) > 1e-30 else 1e-30)
            c = 1 + num / c
            c = c if abs(c) > 1e-30 else 1e-30
            f *= d * c
        if abs(d * c - 1) < 1e-10:
            break
    return min(1.0, front * f)


TOPPING_AREAS = ('Toppings', 'Strong ', 'Changed mind', 'Considered')      # per-topping rows of explore.html
# the groupings the study is about; the others (demographics, recruitment) are shown folded away. The task is desktop
# only, so the device is not a grouping.
RESEARCH_GROUPINGS = ('neurotype', 'nd_any', 'nd_autistic', 'nd_adhd', 'nd_identified', 'eat_picky', 'eat_any', 'nutri_revealed', 'nutrition_panel', 'study', 'condition')
# measures that make a lead: not the per-topping indicators, base choices or the low-level process and movement
# timings (they stay in the full screen)
NOT_LEADS = TOPPING_AREAS + ('Base and diet', 'Process', 'Movement')
LEAD_MIN = SMALL_N      # people in each group before a difference is listed as a lead
# measures that define a grouping are not compared within it (people who revealed the nutrition "reveal it more often")
DEFINED_BY = {'nutri_revealed': ('Seeing nutrition',), 'nutrition_panel': ('Seeing nutrition',)}


# Kept in participants.csv but not screened for group differences: they mostly re-measure something already screened
# or measure the interface rather than the choice, and every extra test weakens the correction for the others.
SCREEN_DROP = {
    # mouse movement: depends on the mouse, the hand and the screen more than on the choice
    'mv_straight', 'mv_pauses', 'mv_paused_share', 'mv_dwell', 'mv_hold', 'mv_crossings', 'mv_path',
    # hovering is not considering (the cursor passes over the tray on its way)
    'n_considered_not_picked', 'hover_total_ms',
    # interface counters and duplicates of revision_rate / n_adjustments
    'n_ev_move', 'n_ev_remove', 'n_ev_undo', 'n_ev_reject', 'n_done_presses', 't_after_done', 'n_start_over_declined', 'move_dist_total',
    'n_moved_pieces', 'n_removed_pieces', 'n_adj_after_done', 'base_changed_after_toppings', 'n_edits_after_done',
    # reasons for adjustments: an arbitrary first-match rule; adj_symmetry_excess (with its chance baseline) stays
    'n_adj_symmetry', 'n_adj_nudges', 'n_adj_grouping', 'n_adj_spacing', 'n_adj_unstacking', 'n_adj_size_match',
    # nutrient totals mostly re-measure the amount and rest on estimated piece weights; the energy of the toppings stays
    'nut_kcal', 'top_grams', 'top_kcal_share', 'nut_protein_g', 'nut_satfat_g', 'nut_sugars_g', 'nut_fibre_g', 'nut_salt_g', 'nut_vitC_mg', 'nut_vitA_ug',
    # seeing the nutrition: the primary measures stay (revealed, changed, energy change, changed my mind)
    'nutri_reveal_share', 'nutri_open_ms', 'post_nutri_d_satfat_g', 'post_nutri_d_meat_pieces', 'post_nutri_removal_share', 'rebuilt_after_done',
    # parts of other measures (n_strong, n_sensory_reasons, shannon)
    'n_strong_positive', 'n_strong_negative', 'n_about_texture', 'n_about_smell', 'n_about_touching', 'n_crave_often', 'evenness', 'profile_uniqueness',
}


def explore_measures(recs, tray):
    """Every measure screened: the profile measures, EXPLORE_EXTRA, base choices, diet class, and per-topping
    indicators (on the pizza; named with strong positive / negative feelings). Returns [(area, key, label)], {key: [values]}."""
    defs, seen = [], set(SCREEN_DROP)
    for dom, key, label, _tf, _sign in PROFILE_FEATURES:
        if key not in seen:
            defs.append((dom, key, label)); seen.add(key)
    for d in EXPLORE_EXTRA:
        if d[1] not in seen:
            defs.append(d); seen.add(d[1])
    vals = {k: [r.get(k) if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool) else None for r in recs] for _, k, _ in defs}
    for field_, label in (('sauce', 'Sauce'), ('cheese', 'Cheese'), ('diet_class', 'Diet class')):
        levels = sorted({r.get(field_) for r in recs if r.get(field_)})
        if len(levels) > 1:
            for lv in levels:
                k = '%s=%s' % (field_, lv)
                defs.append(('Base and diet', k, '%s: %s' % (label, lv)))
                vals[k] = [None if not r.get(field_) else int(r.get(field_) == lv) for r in recs]
    strong_known = [r.get('n_strong') is not None for r in recs]
    for ing in tray:
        k = 'inc_' + ing
        defs.append(('Toppings used', k, NAMES.get(ing, ing)))
        vals[k] = [int((r.get('n_' + ing) or 0) > 0) for r in recs]
    for sign, word in (('neg', 'negative'), ('pos', 'positive')):
        for ing in tray:
            k = '%s_%s' % (sign, ing)
            feel = FEEL_NEG if sign == 'neg' else FEEL_POS
            v = []
            for r, known in zip(recs, strong_known):
                if not known:
                    v.append(None)
                    continue
                lst = dict(x.split(':', 1) for x in (r.get('strong_list') or '').split() if ':' in x)
                v.append(int(lst.get(ing) in feel))
            defs.append(('Strong %s feelings' % word, k, NAMES.get(ing, ing)))
            vals[k] = v
    keep = []
    for d in defs:
        present = [v for v in vals[d[1]] if v is not None]
        if len(present) >= 4 and len(set(present)) > 1:
            keep.append(d)
    return keep, vals


def group_labels(recs, key):
    """Each pizza's group in a grouping, as text (yes / no for the yes/no groupings), None when unknown."""
    raw = [r.get(key) for r in recs]
    if key in ('nd_any', 'nd_autistic', 'nd_adhd', 'eat_any', 'eat_picky', 'nutrition_panel', 'nutri_revealed'):
        raw = [None if v is None else ('yes' if v else 'no') for v in raw]
    return [None if v in (None, '') else str(v) for v in raw]


def grouping_levels(recs, key, min_n=3):
    raw = group_labels(recs, key)
    cnt = Counter(v for v in raw if v is not None)
    levels = [lv for lv, c in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0])) if c >= min_n]
    return (levels, [v if v in levels else None for v in raw], {lv: c for lv, c in cnt.items() if lv not in levels}) if len(levels) >= 2 else (None, None, None)


# groupings with a natural reference group: each other group is compared with it, not with everyone else (pooling
# autistic, ADHD and AuDHD people into "the rest" mixes the groups the study compares)
GROUPING_REF = {'neurotype': 'Not ND', 'nd_any': 'no', 'nd_autistic': 'no', 'nd_adhd': 'no', 'eat_any': 'no', 'eat_picky': 'no',
                'nutri_revealed': 'no', 'nutrition_panel': 'no'}       # yes/no groupings read "yes vs no"


def min_n_to_pass(m, fdr=0.05):
    """The smallest group size (two equal groups) at which even a perfect separation can pass a correction over m
    tests: the exact Mann-Whitney p of a perfect separation, 2 / C(2n, n), must reach fdr / m (the Benjamini-Hochberg
    threshold for the best of m tests)."""
    n = 2
    while 2 / math.comb(2 * n, n) > fdr / max(m, 1):
        n += 1
    return n


def fam_words(research, n_research, n_other):
    """Which family a grouping's q-values were corrected over, in words."""
    return ('the %d tests of the study\'s groupings and self-reports' % n_research) if research else ('the %d tests of the demographic and recruitment groupings' % n_other)


def cluster_group_test(clusters, labels, levels, rnd, draws=2000, min_n=20):
    """Clusters x groups: the table, χ² and a permutation p (the groups shuffled across people). None with fewer
    than min_n people in both: then the expected counts are too small for any test."""
    pairs = [(c, g) for c, g in zip(clusters, labels) if c and g in levels]
    if len(pairs) < min_n:
        return None
    ks = sorted({c for c, _ in pairs})
    def chi(ps):
        tab = [[sum(1 for c, g in ps if c == k and g == lv) for lv in levels] for k in ks]
        rt, ct, tot = [sum(r) for r in tab], [sum(col) for col in zip(*tab)], len(ps)
        return tab, sum((tab[i][j] - rt[i] * ct[j] / tot) ** 2 / (rt[i] * ct[j] / tot) for i in range(len(ks)) for j in range(len(levels)) if rt[i] and ct[j])
    tab, obs = chi(pairs)
    cs, gs = [c for c, _ in pairs], [g for _, g in pairs]
    hits = 0
    for _ in range(draws):
        rnd.shuffle(gs)
        hits += chi(list(zip(cs, gs)))[1] >= obs - 1e-12
    return tab, obs, (hits + 1) / (draws + 1)


def explore_grouping(defs, vals, labels, levels, rnd, ref=None):
    """Each measure compared between the levels of one grouping: with two levels, the first against the second;
    with more, each level against all the others. Returns a list of test dicts with BH q-values over the grouping."""
    tests = []
    pairs = ([(lv, ref) for lv in levels if lv != ref] if ref else [(levels[0], levels[1])] if len(levels) == 2 else [(lv, None) for lv in levels])
    for dom, key, label in defs:
        idx = [i for i, (v, g) in enumerate(zip(vals[key], labels)) if v is not None and g is not None]
        if len(idx) < 6:
            continue
        xs = [vals[key][i] for i in idx]
        if len(set(xs)) < 2:
            continue
        r = midranks(xs)
        tie = sum(c ** 3 - c for c in Counter(xs).values())
        for a, b in pairs:
            ia = [j for j, i in enumerate(idx) if labels[i] == a]
            ib = [j for j, i in enumerate(idx) if (labels[i] == b if b else labels[i] != a)]
            if len(ia) < 3 or len(ib) < 3:
                continue
            if b:  # two levels: rank within just these two
                xs2 = [xs[j] for j in ia + ib]
                if len(set(xs2)) < 2:
                    continue
                rr, tie2 = midranks(xs2), sum(c ** 3 - c for c in Counter(xs2).values())
                r1 = sum(rr[:len(ia)])
            else:
                rr, tie2, r1 = r, tie, sum(r[j] for j in ia)
            x, y = [xs[j] for j in ia], [xs[j] for j in ib]
            u = r1 - len(ia) * (len(ia) + 1) / 2
            delta = 2 * u / (len(ia) * len(ib)) - 1
            binary = set(xs) <= {0, 1}
            tests.append({'area': dom, 'key': key, 'label': label, 'level': a, 'vs': b or 'the rest', 'n1': len(x), 'n0': len(y),
                          'm1': statistics.mean(x) if binary else statistics.median(x), 'm0': statistics.mean(y) if binary else statistics.median(y),
                          'binary': binary, 'delta': delta, 'p': mw_p(r1, rr, len(ia), tie2, rnd), 'x': x, 'y': y})
    for t, q in zip(tests, bh([t['p'] for t in tests])):
        t['q'] = q
    return tests


def delta_cell(d, q):
    if d is None:
        return '<td class="dc na">·</td>'
    mark = ' sig' if q is not None and q < 0.1 else ''
    return '<td class="dc%s" style="background:%s" title="delta %.2f, q %.3f">%s</td>' % (mark, heat_color(d * 2.5), d, q if q is not None else 1, ('%.2f' % d).replace('0.', '.').replace('-.', '−.'))


def strip_svg(x, y, binary, la, lb):
    """Two rows of dots (group, comparison) on a shared axis, medians marked; for yes/no measures, two bars."""
    W, H, L, R = 260, 44, 4, 4
    if binary:
        pa, pb = statistics.mean(x), statistics.mean(y)
        return ('<svg class="strip" viewBox="0 0 %d %d" role="img" aria-label="%s %.0f%%, %s %.0f%%">'
                '<rect x="%d" y="6" width="%.1f" height="12" class="ba"/><rect x="%d" y="24" width="%.1f" height="12" class="bb"/>'
                '<text x="%.1f" y="16" class="sv">%.0f%%</text><text x="%.1f" y="34" class="sv">%.0f%%</text></svg>'
                % (W, H, esc(la), 100 * pa, esc(lb), 100 * pb, L, max(1, pa * 200), L, max(1, pb * 200), L + pa * 200 + 4, 100 * pa, L + pb * 200 + 4, 100 * pb))
    allv = x + y
    lo, hi = min(allv), max(allv)
    if hi - lo < 1e-12:
        hi = lo + 1
    X = lambda v: L + (W - L - R) * (v - lo) / (hi - lo)
    s = ['<svg class="strip" viewBox="0 0 %d %d" role="img" aria-label="medians %s %.3g, %s %.3g">' % (W, H, esc(la), statistics.median(x), esc(lb), statistics.median(y))]
    for row, vs, cls in ((12, x, 'da'), (32, y, 'db')):
        for i, v in enumerate(vs):
            s.append('<circle cx="%.1f" cy="%.1f" r="2.6" class="%s"/>' % (X(v), row + ((i * 7) % 9 - 4) * 0.7, cls))
        m = statistics.median(vs)
        s.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" class="md"/>' % (X(m), X(m), row - 8, row + 8))
    s.append('</svg>')
    return ''.join(s)


def is_ms(key):
    """Measures recorded in milliseconds (times and durations), shown in seconds."""
    return key.endswith('_ms') or key.startswith(('t_', 'mv_dwell', 'mv_hold')) or key in ('decision_median', 'decision_mean', 'hover_ms', 'tray_rest_ms')


def fmt_m(v, binary, key=''):
    """A typical value for the tables: % for yes/no measures, seconds for times, otherwise 2 decimals or whole numbers."""
    if v is None:
        return ''
    if binary:
        return '%.0f%%' % (100 * v)
    if is_ms(key):
        return '%.1f s' % (v / 1000)
    return ('%.0f' % v) if abs(v) >= 100 else ('%.2f' % v)


def delta_size(d):
    """Conventional size of a Cliff's delta (Romano et al. 2006): negligible < .147 <= small < .33 <= medium < .474 <= large."""
    a = abs(d)
    return 'negligible' if a < .147 else 'small' if a < .33 else 'medium' if a < .474 else 'large'


def fmt_p(p):
    return '&lt;0.001' if p < 0.001 else '%.3f' % p


EXPLORE_CSS = """
.hyp { border: 1px solid var(--line); border-left: 4px solid var(--line); border-radius: 10px; padding: 10px 14px; margin: 12px 0; background: var(--panel, transparent); }
.hyp.yes { border-left-color: #2f7d4f; } .hyp.no { border-left-color: #b3261e; } .hyp.wait { border-left-color: #9a6a00; }
.hyp h3 { margin: 2px 0 4px; } .hyp .verdict { font-weight: 600; margin: 4px 0 8px; }
.hyp .ok { color: #2f7d4f; font-weight: 600; } .hyp .bad { color: #b3261e; font-weight: 600; } .hyp tr.na td { color: var(--muted, #6e635b); }
.ready { display: flex; align-items: center; gap: 10px; margin: 0 0 8px; font-size: .85rem; color: var(--muted, #6e635b); }
.ready .track { width: 160px; height: 8px; border-radius: 4px; background: rgba(128,128,128,.25); overflow: hidden; }
.ready .track i { display: block; height: 100%; background: #9a6a00; }
.verdict { background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--muted); border-radius: 8px; padding: 6px 10px; max-width: 90ch; }
.verdict.pass { border-left-color: var(--ok); } tr.pass td:first-child { box-shadow: inset 3px 0 0 var(--ok); }
.lead { background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--near); border-radius: 12px; padding: 10px 14px; }
.tbl { overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 6px 8px; margin-bottom: 14px; }
.tbl table { border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; width: 100%; }
.tbl th, .tbl td { padding: 4px 6px; text-align: right; border-bottom: 1px solid var(--line); vertical-align: middle; }
.tbl th { color: var(--muted); font-weight: 600; } .tbl .l { text-align: left; }
.tbl td.ci { white-space: nowrap; color: var(--muted); }
.tbl table.leads { min-width: 900px; } .tbl table.leads td { white-space: nowrap; } .tbl table.small { width: auto; min-width: 280px; }
.tbl tr.dom td { text-align: left; font-weight: 600; background: var(--bg); }
.dc { text-align: center !important; min-width: 44px; font-size: 12px; } .dc.sig { font-weight: 700; outline: 2px solid var(--fg); outline-offset: -2px; }
.dc.na { color: var(--muted); }
.strip { width: 260px; height: 44px; display: block; }
.strip .da { fill: var(--g1); fill-opacity: .75; } .strip .db { fill: var(--g0); fill-opacity: .6; } .strip .md { stroke: var(--fg); stroke-width: 2; }
.strip .ba { fill: var(--g1); } .strip .bb { fill: var(--g0); } .strip .sv { fill: var(--fg); font-size: 11px; }
details.more { margin: 8px 0 14px; } details.more summary { cursor: pointer; font-weight: 600; }
.corr td.c { width: 16px; min-width: 16px; height: 16px; padding: 0; border: 0; }
.corr th { font-weight: 400; color: var(--muted); font-size: 11px; white-space: nowrap; text-align: right; padding: 0 6px 0 0; border: 0; }
.corr th.v { height: 150px; vertical-align: bottom; padding: 0 0 4px; } .corr th.v div { writing-mode: vertical-rl; transform: rotate(180deg); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; } .chips span { background: var(--bg); border: 1px solid var(--line); border-radius: 999px; padding: 2px 10px; font-size: 13px; }
"""


Z_A, Z_B = 1.959964, 0.841621          # two-sided alpha .05, power .80


def z_alpha(alpha):
    """Two-sided critical z for this alpha (1.96 at .05)."""
    return Z_A if alpha == 0.05 else statistics.NormalDist().inv_cdf(1 - alpha / 2)


def n_per_group(delta, alpha=0.05):
    """People per group a two-group study needs for 80% power at this alpha (two-sided Mann-Whitney), if the true
    Cliff's delta is this (Noether 1987, equal groups): n = 2 (z_a + z_b)^2 / (3 delta^2)."""
    return math.ceil(2 * (z_alpha(alpha) + Z_B) ** 2 / (3 * delta * delta)) if delta else None


def n_for_rho(rho, alpha=0.05):
    """People a correlational study needs for 80% power at this alpha (two-sided): n = ((z_a + z_b) / atanh(rho))^2 + 3."""
    return math.ceil(((z_alpha(alpha) + Z_B) / math.atanh(min(abs(rho), 0.999))) ** 2 + 3) if rho else None


def n_for_change(dom, alpha=0.05):
    """People needed to detect a within-person change with a sign test at 80% power, if the true dominance (share of
    people who rise minus share who fall) is this: with p = (1 + dom) / 2, n = (0.5 z_a + z_b sqrt(p (1 - p)))^2 / (p - 0.5)^2."""
    if not dom:
        return None
    p = (1 + min(abs(dom), 0.999)) / 2
    return math.ceil((0.5 * z_alpha(alpha) + Z_B * math.sqrt(p * (1 - p))) ** 2 / (p - 0.5) ** 2)


def chance_test(x, c, rnd, draws=4000):
    """One group against a chance level c: dominance = (#above - #below) / n, and a two-sided sign-flip permutation
    p on the differences from c, (hits + 1) / (draws + 1)."""
    d = [v - c for v in x if v != c]
    if not x:
        return None, None
    dom = (sum(v > c for v in x) - sum(v < c for v in x)) / len(x)
    if not d:
        return dom, 1.0
    obs = abs(sum(d)) - 1e-12
    hits = 0
    for _ in range(draws):                     # one random bit per difference decides its sign
        bits = rnd.getrandbits(len(d))
        hits += abs(sum(v if (bits >> i) & 1 else -v for i, v in enumerate(d))) >= obs
    return dom, (hits + 1) / (draws + 1)


# Ideas to test (docs/sample-sizes.md): leads with a reason to expect a difference. Not hypotheses: nothing is
# preregistered and some have no expected direction. They are tested as one small family, so the false discovery
# correction runs over a few dozen tests instead of the whole screen. Each: (id, title, why, [(grouping, level)],
# [(measure, expected sign: +1 higher in the group, -1 lower, 0 either way)]).
IDEAS = [
    ('Idea 1', 'Fewer, more familiar toppings', 'Food selectivity and a preference for the familiar are among the most replicated eating findings in autism.',
     [('nd_autistic', 'yes'), ('eat_picky', 'yes')],
     [('n_distinct', -1), ('shannon', -1), ('prop_unusual_distinct', -1), ('ingredient_rarity', -1)]),
    ('Idea 2', 'Foods kept apart', 'Many autistic people dislike foods touching.',
     [('nd_autistic', 'yes')], [('prop_touching', -1), ('prop_stacked', -1), ('clark_evans', 1)]),
    ('Idea 3', 'Order and symmetry', 'A preference for sameness and pattern.',
     [('nd_autistic', 'yes')], [('mirror_score', 1), ('rot_score', 1), ('size_match_index', 1), ('sweep_consistency', 1)]),
    ('Idea 4', 'Sensory reasons and safe foods', 'Sensory sensitivity drives food choice.',
     [('nd_autistic', 'yes'), ('self_sensory_food', None)], [('n_strong', 1), ('n_sensory_reasons', 1), ('n_safe_foods', 1)]),
    ('Idea 5', 'Quicker choices, more changes of mind', 'Impulsivity and novelty seeking in ADHD.',
     [('nd_adhd', 'yes')], [('decision_median', -1), ('n_adjustments', 1), ('revision_rate', 1), ('prop_unusual_distinct', 1)]),
    ('Idea 6', 'AuDHD: its own pattern', 'Autism (sameness) and ADHD (novelty) pull in opposite directions; AuDHD may sit between or differ from both.',
     [('neurotype', 'AuDHD')], [('n_distinct', 0), ('prop_unusual_distinct', 0), ('revision_rate', 0), ('prop_touching', 0)]),
    ('Idea 7', 'Seeing the nutrition changes the pizza', 'Interoception and attention to health information differ between people; the change is measured within each person.',
     [('revealers', None), ('nd_autistic', 'yes')], [('post_nutri_d_kcal', -1)]),
    ('Idea 8', 'My pizza vs a typical person\'s', 'Self-other differences: how far one\'s own choice is from what one expects of others.',
     [('nd_autistic', 'yes')], [('typical_jaccard', 0), ('typical_count_dev', 0)]),
    ('Idea 9', 'Neurodivergent people make more unusual pizzas',
     'Read either way: "are unusual pizzas more often made by neurodivergent people?" is the same rank comparison as "are neurodivergent people\'s pizzas '
     'more unusual?". ADHD novelty seeking points this way; autistic selectivity (idea 1) points the other way, so the two ideas compete. Unusual = the '
     'surprise of the topping set against the other pizzas (bits) and how rare the chosen toppings are.',
     [('nd_any', 'yes'), ('nd_autistic', 'yes'), ('nd_adhd', 'yes')], [('atypicality_bits', 1), ('ingredient_rarity', 1), ('prop_unusual_distinct', 1)]),
]
LARGE_DELTA = 0.474     # a large Cliff's δ (Romano et al. 2006): the effect the sample sizes below are planned for
SAMPLE_TIP = ('People per group for 80%% power, two-sided: n = 2 (z(α/2) + z(0.80))² / (3 δ²) (Noether 1987), with α = .05 / t for t tests '
              '(Bonferroni over the idea\'s tests). Correlations: n = ((z(α/2) + z(0.80)) / atanh ρ)² + 3. Change within a person (sign test, '
              'dominance d, p = (1 + d) / 2): n = (0.5 z(α/2) + z(0.80) √(p(1 − p)))² / (p − 0.5)². Details: Methods → Sample sizes.')


def planned_tests(recs, defs, groupings, covariates, rnd):
    """The ideas (IDEAS) tested on these pizzas: [(idea, [test dicts])], with q over all their tests together."""
    names = {k: lab for _, k, lab in defs}
    gnames = dict(list(groupings) + list(covariates))
    num = lambda k: [r.get(k) if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool) else None for r in recs]
    out, family = [], []
    for hid, title, why, comps, measures in IDEAS:
        tests = []
        for gkey, level in comps:
            for k, sign in measures:
                base = {'hyp': hid, 'key': k, 'label': names.get(k, k), 'sign': sign, 'grouping': gkey}
                if gkey == 'revealers':              # within each person: the change after seeing the nutrition, against no change
                    x = [v for v, r in zip(num(k), recs) if v is not None and r.get('nutri_revealed')]
                    if len(x) < 5:
                        tests.append(dict(base, level='saw the nutrition', vs='no change', n1=len(x), n0=None, missing='needs 5+ people who saw the nutrition'))
                        continue
                    dom, pv = chance_test(x, 0.0, rnd)
                    tests.append(dict(base, level='saw the nutrition', vs='no change', n1=len(x), n0=None, m1=statistics.median(x), m0=0.0, delta=dom, p=pv,
                                      binary=False, kind='change'))
                    continue
                if level is None:                    # a continuous self-report: Spearman correlation
                    rho, pv, m = spearman(num(k), num(gkey))
                    if rho is None:
                        tests.append(dict(base, level=gnames.get(gkey, gkey), vs='', n1=m or 0, n0=None, missing='needs 6+ people with both answers'))
                        continue
                    tests.append(dict(base, level=gnames.get(gkey, gkey), vs='', n1=m, n0=None, m1=None, m0=None, delta=rho, p=pv, binary=False, kind='rho'))
                    continue
                levels, labels, _ = grouping_levels(recs, gkey)
                cnt = Counter(v for v in group_labels(recs, gkey) if v is not None)
                if not levels or level not in levels:
                    have = cnt.get(level, 0)
                    tests.append(dict(base, level=level, vs='the rest', n1=have, n0=sum(cnt.values()) - have, missing='needs 3+ in each group'))
                    continue
                order = [level] + [lv for lv in levels if lv != level]
                got = [t for t in explore_grouping([('Planned', k, names.get(k, k))], {k: num(k)}, labels, order, rnd) if t['level'] == level]
                if not got:
                    tests.append(dict(base, level=level, vs='the rest', n1=cnt.get(level, 0), n0=sum(cnt.values()) - cnt.get(level, 0), missing='no variation yet'))
                    continue
                t = got[0]
                tests.append(dict(base, level=level, vs=t['vs'], n1=t['n1'], n0=t['n0'], m1=t['m1'], m0=t['m0'], delta=t['delta'], p=t['p'], binary=t['binary'],
                                  kind='groups', x=t['x'], y=t['y']))
        out.append(((hid, title, why), tests))
        family += [t for t in tests if 'p' in t]
    for t, q in zip(family, bh([t['p'] for t in family])):
        t['q'] = q
        t['right_way'] = None if not t['sign'] or not t['delta'] else (t['delta'] > 0) == (t['sign'] > 0)
    return out


def planned_html(planned, groupings, covariates):
    """The Ideas to test section of explore.html."""
    gnames = dict(list(groupings) + list(covariates) + [('revealers', 'Within each person')])
    n_all = sum(len(ts) for _, ts in planned)                       # every planned test, run or not yet
    cards, n_run = [], sum(1 for _, ts in planned for t in ts if 'p' in t)
    for (hid, title, why), tests in planned:
        rows, done = [], [t for t in tests if 'p' in t]
        for t in tests:
            exp = {1: 'higher', -1: 'lower', 0: 'either way', None: 'either way'}[t['sign']]
            if t['grouping'] == 'revealers':
                exp = {1: 'rises', -1: 'falls', 0: 'changes'}[t['sign']]
            who = ('%s: %s' % (gnames.get(t['grouping'], t['grouping']), t['level'])) if t.get('kind') != 'rho' else 'correlation with %s' % t['level']
            if 'p' not in t:
                rows.append('<tr class="na"><td class="l">%s</td><td class="l">%s</td><td>%s</td><td>%s</td><td colspan="5" class="l muted">%s</td></tr>'
                            % (esc(t['label']), esc(who), esc(exp), '%d / %d' % (t['n1'], t['n0']) if t.get('n0') is not None else t['n1'], esc(t['missing'])))
                continue
            way = '' if t['right_way'] is None else ('<span class="ok">✓ as expected</span>' if t['right_way'] else '<span class="bad">✗ opposite</span>')
            mm = ('%s / %s' % (fmt_m(t['m1'], t['binary'], t['key']), fmt_m(t['m0'], t['binary'], t['key']))) if t.get('m1') is not None else ''
            rows.append('<tr%s><td class="l">%s</td><td class="l">%s</td><td>%s</td><td>%s</td><td>%s</td><td><b>%+.2f</b><br><span class="muted">%s</span></td>'
                        '<td>%s</td><td>%.3f%s</td><td>%s</td></tr>'
                        % (' class="pass"' if t['q'] < 0.1 and t['right_way'] is not False else '', esc(t['label']), esc(who), esc(exp),
                           '%d / %d' % (t['n1'], t['n0']) if t.get('n0') is not None else t['n1'], mm, t['delta'],
                           'ρ' if t.get('kind') == 'rho' else 'dominance' if t.get('kind') == 'change' else delta_size(t['delta']),
                           fmt_p(t['p']), t['q'], ' ✓' if t['q'] < 0.1 else '', way))
        groups = [t for t in done if t.get('kind') == 'groups']
        smallest = min([min(t['n1'], t['n0']) for t in groups] or [0])
        lead = [t for t in done if t['q'] < 0.1 and t['right_way'] is not False]
        directional = [t for t in done if t['right_way'] is not None]
        as_expected = sum(1 for t in directional if t['right_way'])
        if not done:
            verdict, cls = 'Cannot be tested yet: too few people in the groups it compares.', 'wait'
        elif lead:
            verdict, cls = ('Strong lead: %d of %d tests differ after the correction%s. Worth preregistering.'
                            % (len(lead), len(done), ', the expected way' if any(t['right_way'] for t in lead) else '')), 'yes'
        elif groups and smallest < min_n_to_pass(n_all):
            need = min_n_to_pass(n_all)
            verdict, cls = ('Too few to pass the correction yet (smallest group %d; over %d tests it takes at least %d). So far %d of %d tests with an expected direction point that way.'
                            % (smallest, n_all, need, as_expected, len(directional))) if directional else ('Too few to pass the correction yet (smallest group %d; it takes at least %d).' % (smallest, need)), 'wait'
        else:
            verdict, cls = ('No sign yet. %d of %d tests with an expected direction point that way.' % (as_expected, len(directional))
                            if directional else 'No sign yet.'), 'no'
        # how many tests the idea runs, and what that costs in people
        n_meas, n_comp = len({t['key'] for t in tests}), len({(t['grouping'], t['level']) for t in tests})
        need_alone, need_all, need_plain = n_per_group(LARGE_DELTA, 0.05 / len(tests)), n_per_group(LARGE_DELTA, 0.05 / n_all), n_per_group(LARGE_DELTA)
        cost = ('<p class="cost" title="%s">%d measure%s × %d comparison%s = <b>%d tests</b>. For a large effect (δ = %.2f) with 80%% power: <b>%d per group</b> if this idea '
                'alone is preregistered (α = .05 / %d), %d per group as part of all %d tests here (α = .05 / %d), %d per group for one test without correction.</p>'
                % (SAMPLE_TIP, n_meas, '' if n_meas == 1 else 's', n_comp, '' if n_comp == 1 else 's', len(tests), LARGE_DELTA, need_alone, len(tests), need_all, n_all, n_all, need_plain))
        bar = ''
        if groups:
            pct = min(100, round(100 * smallest / need_alone))
            bar = ('<div class="ready"><div class="track"><i style="width:%d%%"></i></div><span>%d of %d people in the smaller group (the number above for this idea '
                   'alone)</span></div>' % (pct, smallest, need_alone))
        cards.append('<div class="hyp %s"><h3>%s. %s</h3><p class="muted">%s</p><p class="verdict">%s</p>%s%s<div class="tbl"><table class="leads"><tr><th class="l">Measure</th>'
                     '<th class="l">Compared</th><th>Expected</th><th>n</th><th>median or %%</th><th>effect</th><th>p</th><th>q</th><th>Direction</th>'
                     '</tr>%s</table></div></div>'
                     % (cls, esc(hid), esc(title), esc(why), esc(verdict), cost, bar, ''.join(rows)))
    return ('<h2 id="planned">Ideas to test</h2><p class="muted">Leads worth checking, from what is known about eating in autism and ADHD '
            '(docs/sample-sizes.md). They are <b>not hypotheses</b>: nothing here is preregistered, and some have no expected direction. They are tested '
            'as one family of %d tests (%d can run on these data), so q is corrected over these only, not over the whole screen below: this is where a '
            'real difference can show first. A test is a strong lead when q &lt; 0.10 and, where a direction is expected, it goes that way. Every test '
            'adds to the correction, so each idea shows how many tests it runs and how many people that takes. To confirm, pick 3-5 ideas, state their '
            'direction in a preregistration, and test them in a new sample. How every sample size here is worked out, with the formulas and worked examples: '
            '<a href="methods.html#sample-sizes" onclick="if (window.parent !== window) { parent.location.hash = \'methods\'; return false; }">Methods → Sample sizes</a> (hover a number for the formula).</p>%s' % (n_all, n_run, ''.join(cards)))


def explore_report(recs, tray, groupings, covariates, seed=1):
    """explore.html: screens every measure for differences between the groups of every grouping available, and for
    links with continuous self-reports, to find patterns worth following up. Writes the tests to explore.csv too."""
    rnd = random.Random(seed)
    n = len(recs)
    head = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<title>Pizza Explorer</title><style>%s%s</style></head><body><div class="wrap"><h1>Exploring patterns</h1>' % (REPORT_CSS, EXPLORE_CSS))
    if n < 6:
        return head + '<p>This needs at least 6 finished pizzas; there %s %d so far.</p></div></body></html>' % ('is' if n == 1 else 'are', n), []
    defs, vals = explore_measures(recs, tray)
    body, other_body, all_tests, used = [], [], [], []
    research = set(RESEARCH_GROUPINGS) | {k for k, _ in groupings if k not in dict(EXPLORE_GROUPINGS)}     # + --group columns
    # 1. every test of the screen: each grouping, and each continuous self-report
    for key, glabel in groupings:
        levels, labels, dropped = grouping_levels(recs, key)
        if not levels:
            continue
        gdefs = [d for d in defs if d[0] not in DEFINED_BY.get(key, ())]
        ref = GROUPING_REF.get(key) if GROUPING_REF.get(key) in levels else None
        tests = explore_grouping(gdefs, vals, labels, levels, rnd, ref)
        if tests:
            used.append((key, glabel, levels, labels, dropped, tests, ref))
            all_tests += [dict(t, grouping=key) for t in tests]
    cov_res = []
    for ckey, clabel in covariates:
        cv = [r.get(ckey) if isinstance(r.get(ckey), (int, float)) else None for r in recs]
        if sum(v is not None for v in cv) < 6:
            continue
        res = []
        for dom, k, label in defs:
            if k != ckey:
                rho, pv, m = spearman(vals[k], cv)
                if rho is not None:
                    res.append({'grouping': ckey, 'area': dom, 'key': k, 'label': label, 'level': 'Spearman rho', 'vs': '', 'n1': m, 'n0': None,
                                'm1': None, 'm0': None, 'delta': rho, 'p': pv})
        cov_res.append((clabel, res))
        all_tests += res
    # 2. the false discovery correction over a whole family of questions, not one grouping at a time: the study's
    # groupings and the self-reports are one family; the demographic and recruitment groupings are another (they would
    # otherwise dilute the study's questions with hundreds of tests nobody asked)
    is_research = lambda t: t.get('grouping') in research or t.get('level') == 'Spearman rho'
    screen = [t for t in all_tests if 'p' in t and is_research(t)]
    others = [t for t in all_tests if 'p' in t and not is_research(t)]
    for fam in (screen, others):
        for t, q in zip(fam, bh([t['p'] for t in fam])):
            t['q'] = q
    for key, glabel, levels, labels, dropped, tests, ref in used:     # the per-grouping lists share the q-values
        qs = {(t['key'], t['level'], t['vs']): t['q'] for t in all_tests if t.get('grouping') == key}
        for t in tests:
            t['q'] = qs[(t['key'], t['level'], t['vs'])]
    n_screen = len(screen)
    need_n = min_n_to_pass(n_screen)
    # 3. each grouping
    for key, glabel, levels, labels, dropped, tests, ref in used:
        cols = ([lv + ' vs ' + ref for lv in levels if lv != ref] if ref else [levels[0] + ' vs ' + levels[1]] if len(levels) == 2 else levels)
        col_levels = [lv for lv in levels if lv != ref] if ref else (levels[:1] if len(levels) == 2 else levels)
        sig = sum(1 for t in tests if t['q'] < 0.1)
        # the strongest evidence first (p, then size), main measures only; the per-topping rows are in the folded tables
        top = sorted((t for t in tests if not t['area'].startswith(TOPPING_AREAS + ('Base and diet',))), key=lambda t: (t['p'], -abs(t['delta'])))[:10]
        rows = []
        for t in top:
            ci = boot_ci(t['x'], t['y'], rnd) if min(t['n1'], t['n0']) >= SMALL_N else None    # a bootstrap of 3 values says nothing
            rows.append('<tr%s><td class="l">%s<br><span class="muted">%s</span></td><td class="l">%s<br><span class="muted">vs %s</span></td><td>%d / %d</td>'
                        '<td>%s / %s</td><td><b>%+.2f</b><br><span class="muted">%s</span></td><td class="ci">%s</td><td>%s</td><td>%s%s</td><td class="l">%s</td></tr>'
                        % (' class="pass"' if t['q'] < 0.1 else '', esc(t['label']), esc(t['area']), esc(t['level']), esc(t['vs']), t['n1'], t['n0'],
                           fmt_m(t['m1'], t['binary'], t['key']), fmt_m(t['m0'], t['binary'], t['key']),
                           t['delta'], delta_size(t['delta']), ('%+.2f to %+.2f' % ci) if ci else '<span class="muted">groups under %d</span>' % SMALL_N,
                           fmt_p(t['p']), '%.3f' % t['q'], ' ✓' if t['q'] < 0.1 else '', strip_svg(t['x'], t['y'], t['binary'], t['level'], t['vs'])))
        by = {(t['key'], t['level']): t for t in tests}
        main = [d for d in defs if not d[0].startswith(TOPPING_AREAS)]
        tops = [d for d in defs if d[0].startswith(TOPPING_AREAS)]
        def heat_rows(ds):
            out, last = [], None
            for dom, k, label in ds:
                cells = [by.get((k, lv)) for lv in col_levels]
                if not any(cells):
                    continue
                if dom != last:
                    out.append('<tr class="dom"><td colspan="%d">%s</td></tr>' % (len(cols) + 1, esc(dom)))
                    last = dom
                out.append('<tr><td class="l">%s</td>%s</tr>' % (esc(label), ''.join(delta_cell(c['delta'], c['q']) if c else delta_cell(None, None) for c in cells)))
            return ''.join(out)
        thead = '<tr><th class="l">Measure</th>%s</tr>' % ''.join('<th class="dc">%s</th>' % esc(c) for c in cols)
        counts = ''.join('<span>%s: %d</span>' % (esc(lv), sum(1 for g in labels if g == lv)) for lv in levels)
        if dropped:
            counts += '<span class="muted">left out (fewer than 3): %s</span>' % esc(', '.join('%s %d' % kv for kv in dropped.items()))
        smallest = min(sum(1 for g in labels if g == lv) for lv in levels)
        (body if key in research else other_body).append('<h2 id="g-%s">%s</h2><div class="chips">%s</div>'
                    '%s'
                    '<div class="tbl"><table class="leads"><tr><th class="l">Measure</th><th class="l">Group</th><th>n</th><th>median or %%<br>%s</th><th>Cliff\'s δ</th><th>95%% CI of δ</th><th>p</th><th>q (FDR)</th><th class="l">Data (orange = group)</th></tr>%s</table></div>'
                    '<details class="more"><summary>Every measure (Cliff\'s δ; orange = higher in %s; outlined = q &lt; 0.10)</summary><div class="tbl"><table>%s%s</table></div></details>'
                    '<details class="more"><summary>Every topping: on the pizza, named with strong feelings</summary><div class="tbl"><table>%s%s</table></div></details>'
                    % (esc(key), esc(glabel), counts,
                       ('<p class="verdict pass">%d of %d comparisons pass the false discovery rate (q &lt; 0.10, ✓ below; corrected over %s). Strongest evidence first:</p>'
                        % (sig, len(tests), fam_words(key in research, n_screen, len(others))) if sig else
                        '<p class="verdict">None of the %d comparisons passes the false discovery rate (q &lt; 0.10, corrected over %s). The strongest are '
                        'listed as leads for a new sample, not as findings%s:</p>' % (len(tests), fam_words(key in research, n_screen, len(others)),
                                                                                       '; with groups this small they describe these people only' if smallest < LEAD_MIN else '')),
                       ('group / %s' % esc(ref)) if ref else 'group / rest' if len(levels) > 2 else '%s / %s' % (esc(levels[0]), esc(levels[1])),
                       ''.join(rows), 'the group' if len(levels) > 2 or ref else esc(levels[0]), thead, heat_rows(main), thead, heat_rows(tops)))
    # links with continuous self-reports
    cov_html = []
    for clabel, res in cov_res:
        top = sorted(res, key=lambda t: (t['p'], -abs(t['delta'])))[:10]
        cov_html.append('<h3>%s</h3><p class="muted">%d measures; %d with q &lt; 0.10 (corrected with the study\'s groupings).</p><div class="tbl"><table><tr><th class="l">Measure</th><th>n</th><th>ρ</th><th>p</th><th>q</th></tr>%s</table></div>'
                        % (esc(clabel), len(res), sum(1 for t in res if t['q'] < 0.1),
                           ''.join('<tr><td class="l">%s <span class="muted">· %s</span></td><td>%d</td><td><b>%+.2f</b></td><td>%.3f</td><td>%.3f</td></tr>'
                                   % (esc(t['label']), esc(t['area']), t['n1'], t['delta'], t['p'], t['q']) for t in top)))
    # how the measures go together
    cm = [d for d in defs if not d[0].startswith(TOPPING_AREAS + ('Base and diet',))]
    M = len(cm)
    grid = [[spearman(vals[a[1]], vals[b[1]])[0] if i != j else 1.0 for j, b in enumerate(cm)] for i, a in enumerate(cm)]
    corr_html = ('<div class="tbl corr"><table><tr><th></th>%s</tr>%s</table></div>'
                 % (''.join('<th class="v"><div>%s</div></th>' % esc(d[2]) for d in cm),
                    ''.join('<tr><th>%s</th>%s</tr>' % (esc(cm[i][2]), ''.join(
                        '<td class="c" style="background:%s" title="%s × %s: ρ = %s"></td>' % (heat_color((grid[i][j] or 0) * 2.5) if grid[i][j] is not None else 'transparent',
                                                                                               esc(cm[i][2]), esc(cm[j][2]), '%.2f' % grid[i][j] if grid[i][j] is not None else 'n/a')
                        for j in range(M))) for i in range(M))))
    # clusters (found from the profiles without any grouping) against each grouping: only when the clusters are real
    # (profiles.html: enough pizzas and a clear structure), with a permutation test instead of χ² tables of tiny counts
    cl_html = []
    clusters = [r.get('cluster') for r in recs]
    if len({c for c in clusters if c}) > 1:
        for key, glabel, levels, labels, *_ in used:
            res = cluster_group_test(clusters, labels, levels, rnd)
            if res:
                tab, chi, pv = res
                cl_html.append('<h3>%s</h3><div class="tbl"><table class="small"><tr><th class="l">Cluster</th>%s</tr>%s</table></div><p class="muted">χ² = %.2f, '
                               'permutation p = %s (2000 shuffles of the groups).</p>'
                               % (esc(glabel), ''.join('<th>%s</th>' % esc(lv) for lv in levels),
                                  ''.join('<tr><td class="l">%d</td>%s</tr>' % (c + 1, ''.join('<td>%d</td>' % v for v in row)) for c, row in enumerate(tab)), chi, fmt_p(pv)))
    # leads for a larger study: the best-supported group differences, one per measure
    for t in all_tests:
        if t.get('level') != 'Spearman rho' and t.get('delta'):
            t['n_per_group_80_half'] = n_per_group(t['delta'] / 2)
        elif t.get('level') == 'Spearman rho' and t.get('delta'):
            t['n_per_group_80_half'] = n_for_rho(t['delta'] / 2)
    seen, leads = set(), []
    for t in sorted((t for t in all_tests if t.get('grouping') in research and t.get('level') != 'Spearman rho' and min(t['n1'], t['n0'] or 0) >= LEAD_MIN
                     and not t['area'].startswith(NOT_LEADS)), key=lambda t: (t['p'], -abs(t['delta']))):
        if t['key'] in seen:
            continue
        seen.add(t['key'])
        leads.append(t)
        if len(leads) == 8:
            break
    lead_rows = []
    for t in leads:
        word = ('more often' if t['binary'] else 'higher') if t['delta'] > 0 else ('less often' if t['binary'] else 'lower')
        lead_rows.append('<tr%s><td class="l"><b>%s</b> %s: %s %s than %s</td><td>%d / %d</td><td><b>%+.2f</b><br><span class="muted">%s</span></td><td>%s</td><td>%.3f%s</td><td>%s</td></tr>'
                         % (' class="pass"' if t['q'] < 0.1 else '', esc(t['level']), esc(dict(groupings).get(t['grouping'], t['grouping'])), esc(t['label']), word, esc(t['vs']),
                            t['n1'], t['n0'], t['delta'], delta_size(t['delta']), fmt_p(t['p']), t['q'], ' ✓' if t['q'] < 0.1 else '', t['n_per_group_80_half'] or ''))
    leads_html = ('<h2 id="leads">Leads for a larger study</h2><p class="muted">The best-supported group differences in these data (lowest p), one per measure, '
                  'from the study\'s own groupings (neurotype, eating, nutrition, study, condition), groups of %d or more, and measures of the pizza and its '
                  'choices (not single toppings or low-level timings). Each could become an idea to test. They are the best of %d comparisons, so their effects '
                  'are overestimated (the winner\'s curse): the last column plans a new study for <b>half</b> the δ seen, at 80%% power and α = .05. δ size words '
                  'follow Romano et al. (2006): negligible &lt; .15, small &lt; .33, medium &lt; .47, large.</p><div class="tbl"><table class="leads"><tr><th class="l">Pattern</th><th>n</th>'
                  '<th>δ</th><th>p</th><th>q</th><th title="%s">n/group to confirm (δ halved) ⓘ</th></tr>%s</table></div>'
                  % (LEAD_MIN, n_screen, SAMPLE_TIP, ''.join(lead_rows))) if lead_rows else (
        '<h2 id="leads">Leads for a larger study</h2><p class="muted">None yet: a lead needs two groups of %d or more in one of the study\'s groupings '
        '(neurotype, eating, nutrition, study, condition). Until then, the tables below describe these people; they are not evidence.</p>' % LEAD_MIN)
    planned = planned_tests(recs, defs, groupings, covariates, rnd)
    for (hid, title, _), ts in planned:
        for t in ts:
            if 'p' in t:
                all_tests.append({'grouping': 'planned', 'area': '%s %s' % (hid, title), 'key': t['key'], 'label': t['label'],
                                  'level': '%s: %s' % (t['grouping'], t['level']), 'vs': t['vs'], 'n1': t['n1'], 'n0': t['n0'], 'm1': t.get('m1'),
                                  'm0': t.get('m0'), 'delta': t['delta'], 'p': t['p'], 'q': t['q'], 'n_per_group_80_half': None})
    nav = '<span><a href="#planned"><b>Ideas to test</b></a></span><span><a href="#leads">Leads</a></span>' + ''.join(
        '<span><a href="#g-%s">%s</a></span>' % (esc(u[0]), esc(u[1])) for u in used if u[0] in research) + (
        '<span><a href="#other">Other groupings</a></span>' if other_body else '')
    # what these data can say: the largest smaller group among the study's groupings
    sizes = [(min(sum(1 for g in u[3] if g == lv) for lv in u[2]), u[1]) for u in used if u[0] in research]
    best = max(sizes) if sizes else (0, '')
    can = ('<b>Nothing can be tested yet</b>: none of the study\'s groupings (neurotype, eating, nutrition, study, condition) has two groups of 3 or more. '
           'The page describes these %d pizzas.' % n if not sizes else
           '<b>Description only</b>: the best grouping (%s) has %d in its smaller group. A difference can reach p &lt; .05 from 4 per group, pass the '
           'correction over this page\'s %d tests from %d per group, and a large effect needs about 24 per group (Methods → Sample sizes).'
           % (esc(best[1]), best[0], n_screen, need_n) if best[0] < need_n else
           '<b>Screening</b>: the best grouping (%s) has %d in its smaller group, enough for a strong difference to pass the correction over this page\'s tests. A large effect needs '
           'about 24 per group for 80%% power.' % (esc(best[1]), best[0]) if best[0] < 24 else
           '<b>Testing</b>: the best grouping (%s) has %d in its smaller group, enough to detect large effects (80%% power).' % (esc(best[1]), best[0]))
    readiness = '<p class="verdict%s">%d pizzas. %s</p>' % (' pass' if best[0] >= 24 else '', n, can)
    html = (head + readiness + '<p class="lead"><b>For exploring, not confirming.</b> First the ideas worth testing, then the best-supported leads, then each '
            'grouping in full (%d measures, %d of them per topping). Effects are Cliff\'s δ (−1 to 1: how often a value from the group is higher than one from '
            'the comparison, minus how often lower; for yes/no measures, the difference in percentages); p from a Mann-Whitney test (by permutation under 8 '
            'per group); q the Benjamini-Hochberg false discovery rate over a family of questions (the study\'s groupings with the self-reports; demographics '
            'apart; the ideas apart); bootstrap 95%% intervals for groups of 5 or more.</p><div class="chips">%s</div>'
            % (len(defs), len([d for d in defs if d[0].startswith(TOPPING_AREAS)]), nav)
            + planned_html(planned, groupings, covariates) + leads_html
            + ''.join(body)
            + ('<details class="more" id="other"><summary>Other groupings: demographics and recruitment (%d)</summary>%s</details>' % (len(other_body), ''.join(other_body))
               if other_body else '')

            + ('<h2>Links with self-reports</h2><p class="muted">Spearman correlations (ρ) of each measure with each continuous self-report.</p>' + ''.join(cov_html) if cov_html else '')
            + '<details class="more"><summary>How the measures go together (correlations)</summary><p class="muted">Spearman correlations between the main measures '
              'across all participants (orange = rise together, blue = one rises as the other falls; hover for the value). Strongly linked measures tell the same story '
              'twice.</p>' + corr_html + '</details>'
            + ('<details class="more"><summary>Clusters and groups</summary><p class="muted">The clusters from the profiles page, found without using any grouping, '
               'against each grouping.</p>' + ''.join(cl_html) + '</details>' if cl_html else '')
            + '</div></body></html>')
    return html, all_tests


def analyse(rows, builds, out_dir, seed, group_cols=None, ref_rows=None, k_force=None, covariates=None):
    rnd = random.Random(seed)
    people, ing_long, ev_long, svgs, arrangement, piece_long, rem_long, adj_long = [], [], [], [], [], [], [], []
    left_out = []      # builds saved part-way (the task saves while building) but never finished: not a choice, so not analysed
    for row in rows:
        pid = row['_pid']
        follow = loads(field(row, 'pzf_data'), {}) or {}
        diet = [d for d in (follow.get('diet') or []) if d != 'pnts']      # 'prefer not to say' = unknown
        p_sum = loads(field(row, 'pzp_summary'), {})
        p_ev = loads(field(row, 'pzp_events'), [])
        for prefix in builds:
            final = loads(field(row, prefix + 'final'))
            if final is None:
                continue
            summary = loads(field(row, prefix + 'summary'), {}) or {}
            choice = inclusion_choice(row)                # the researcher's choice on the Sessions tab, if any
            reason = 'excluded by the researcher' if choice == 'exclude' else 'not finished' if summary.get('finished') is False and choice != 'include' else None
            if reason:
                left_out.append({'pid': pid, 'build': prefix.rstrip('_'), 'reason': reason, 'stage': row.get('stage') or None,
                                 'n_pieces': len(final), 'last_saved': row.get('updated') or None, 'study': row.get('study') or None})
                continue
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
            for k in ('pick', 'add', 'reject', 'tap', 'grab', 'move', 'remove', 'resize', 'abort', 'undo', 'clear', 'hover'):
                rec['n_ev_' + k] = nev.get(k, 0)
            prnd = random.Random('%s:%s:%s' % (seed, pid, prefix))   # per pizza: its chance levels do not depend on the other pizzas
            rec.update(cached_spatial(pieces, prnd, (seed, pid, prefix)))
            rec.update(order_measures(events))
            rec.update(timing(events, summary))
            rec.update(movement_measures(events))
            rec.update(nutrition_measures(pieces, summary))
            rec.update(reveal_measures(events, final, summary))
            acts, act_per, removals = action_measures(events, final)
            rec.update(acts)
            adj, adj_rows = adjustment_measures(events, final, rec, random.Random('%s:%s:%s:adj' % (seed, pid, prefix)))
            rec.update(adj)
            for r in adj_rows:
                adj_long.append(dict({'pid': pid, 'build': prefix.rstrip('_')}, **r))
            for r in removals:
                rem_long.append(dict({'pid': pid, 'build': prefix.rstrip('_')}, **r))
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
            if follow.get('style') == 'strong':
                items = follow.get('items') or {}
                strong = follow.get('strong') or []
                rec['strong_none'] = int(bool(follow.get('none')))
                rec['n_strong'] = len(strong)
                rec['n_strong_positive'] = sum((items.get(k) or {}).get('feel') in FEEL_POS for k in strong)
                rec['n_strong_negative'] = sum((items.get(k) or {}).get('feel') in FEEL_NEG for k in strong)
                rec['n_safe_foods'] = sum((items.get(k) or {}).get('safe') == 'yes' for k in strong)
                rec['n_same_way'] = sum((items.get(k) or {}).get('sameway') == 'yes' for k in strong)
                rec['n_crave_often'] = sum((items.get(k) or {}).get('crave') == 'often' for k in strong)
                for a in ABOUT:
                    rec['n_about_' + a] = sum(a in ((items.get(k) or {}).get('about') or []) for k in strong)
                rec['n_sensory_reasons'] = sum(rec['n_about_' + a] for a in ('texture', 'smell', 'taste', 'look', 'touching'))
                pos = [k for k in strong if (items.get(k) or {}).get('feel') in FEEL_POS]
                neg = [k for k in strong if (items.get(k) or {}).get('feel') in FEEL_NEG]
                rec['strong_pos_on_pizza'] = (sum(counts.get(k, 0) > 0 for k in pos) / len(pos)) if pos else None
                rec['strong_neg_on_pizza'] = (sum(counts.get(k, 0) > 0 for k in neg) / len(neg)) if neg else None
                rec['strong_list'] = ' '.join('%s:%s' % (k, (items.get(k) or {}).get('feel') or '?') for k in strong) or None
            pz = follow.get('pizza') or {}
            for k in PIZZA_ITEMS:
                rec['pz_' + k] = pz.get(k)
            rec['pizza_freq'] = follow.get('freq')
            rec.update(about_measures(follow.get('about')))
            rec['flag_tab_away'] = int((summary.get('hiddenMs') or 0) > 30000)
            rec['flag_fast'] = int(rec['t_finish'] is not None and rec['t_finish'] < 15000)
            rec['flag_empty'] = int(n == 0)
            rec['task_version'] = summary.get('v')
            rec['synthetic'] = int(str(pid).startswith('SYN-') or field(row, 'synthetic') == '1')   # analysis/synthetic.py
            rec['inclusion'] = 'researcher' if choice == 'include' else 'auto'
            try:                                   # study server: times the participant came back and restarted a part
                rec['restarts'] = int(field(row, 'restarts') or 0)
            except ValueError:
                rec['restarts'] = None
            ings = ingredient_rows(pid, prefix, summary, events, counts, follow, diet, pieces)
            for r in ings:
                k = r['ing']
                grams = sum(piece_grams(p) for p in pieces if p['ing'] == k)
                food = NUTRITION['toppings'].get(k) or {}
                r['grams'] = grams
                r['kcal'] = grams * (food.get('per100') or {}).get('kcal', 0) / 100
                r.update({'added_pieces': act_per['added'][k], 'removed_pieces': act_per['removed'][k], 'dropped': int(k in act_per['dropped']),
                          'moves': act_per['moves'][k], 'resizes': act_per['resizes'][k], 'considered_not_picked': int(k in act_per['considered'])})
            if follow.get('items') and follow.get('style') != 'strong':
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
                                'drag_ms': e[6] if len(e) > 6 else None, 'snapped': e[7] if len(e) > 7 else None,
                                **dict(zip(('mv_path', 'mv_straight', 'mv_pauses', 'mv_longest_pause', 'mv_dwell', 'mv_crossings', 'mv_hold'),
                                           e[9] if len(e) > 9 and isinstance(e[9], list) else [None] * 7))})
            svgs.append((pid, prefix, pizza_svg(pieces, summary, '%s %s (%d)' % (pid, prefix.rstrip('_'), n))))
            piece_long.extend(piece_rows(pid, prefix, final, pieces, rec))
            for c in (group_cols or []) + ['study', 'source', 'group']:     # grouping columns from the export / study server
                if c not in rec:
                    rec[c] = field(row, c) or row.get(c) or None
            if rec['study'] is None and 'study' in row:       # study server sessions outside any named study
                rec['study'] = 'main'
            for c in covariates or []:                        # numeric columns from the export (e.g. questionnaire scores)
                if c not in rec:
                    try:
                        rec[c] = float(field(row, c))
                    except (TypeError, ValueError):
                        rec[c] = None
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
    write_csv(os.path.join(out_dir, 'pieces_long.csv'), piece_long, PIECE_COLUMNS)
    write_csv(os.path.join(out_dir, 'adjustments_long.csv'), adj_long, ADJ_COLUMNS)
    write_csv(os.path.join(out_dir, 'excluded.csv'), left_out, EXCLUDED_COLUMNS)
    check = data_check(rows, builds, people, left_out)
    with open(os.path.join(out_dir, 'data_check.json'), 'w', encoding='utf-8') as f:
        json.dump(check, f, indent=1)
    write_csv(os.path.join(out_dir, 'removals_long.csv'), rem_long, ['pid', 'build', 'piece_id', 'ing', 'how', 't_added', 't_removed', 'ms_on_pizza', 'x', 'y', 'restored'])
    cells = []
    for pid, prefix, svg in svgs:
        name = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in '%s_%s' % (pid, prefix.rstrip('_')))
        with open(os.path.join(out_dir, 'pizzas', name + '.svg'), 'w', encoding='utf-8') as f:
            f.write(svg)
        cells.append(svg)
    # the grouping the dashboard, symmetry and profile reports compare: the first --group column, else the
    # self-described neurotype, the study link's group or the condition, whichever first has two or more values
    own_entries = [e for e in arrangement if e[0]['build'] == builds[0].rstrip('_')]
    def n_levels(c):
        return len({r.get(c) for r, _ in own_entries if r.get(c) not in (None, '')})
    primary = (group_cols or [None])[0] or next((c for c in ('neurotype', 'group', 'condition') if n_levels(c) > 1), 'condition')
    group_label = dict(EXPLORE_GROUPINGS).get(primary, primary)
    for rec, _ in arrangement:
        v = rec.get(primary)
        rec['_group'] = str(v) if v not in (None, '') else ('not stated' if primary == 'neurotype' else 'all')
    flag = synthetic_banner(own_entries)          # on every report when synthetic pizzas are in it
    with open(os.path.join(out_dir, 'arrangement.html'), 'w', encoding='utf-8') as f:
        f.write(flag(arrangement_report(arrangement, group_label)))
    with open(os.path.join(out_dir, 'dashboard.html'), 'w', encoding='utf-8') as f:
        f.write(flag(dashboard_report(own_entries, ref_info, group_label, check)))
    prof = profile_analysis(own_entries, k_force)
    for (rec, _), z, lab in zip(own_entries, prof['Z'], prof['labels']):
        rec['cluster'] = lab + 1 if prof['k'] > 1 else None
    with open(os.path.join(out_dir, 'profiles.html'), 'w', encoding='utf-8') as f:
        f.write(flag(profiles_report(own_entries, prof, group_label)))
    write_csv(os.path.join(out_dir, 'profiles.csv'), [
        dict([('pid', r['pid']), ('group', r['_group']), ('cluster', r.get('cluster'))] + [('z_' + f[1], round(v, 4)) for f, v in zip(PROFILE_FEATURES, z)])
        for (r, _), z in zip(own_entries, prof['Z'])])
    # explore.html: every measure screened across every way of grouping people the data allow
    groupings = [(c, dict(EXPLORE_GROUPINGS).get(c, c)) for c in (group_cols or [])]
    groupings += [g for g in EXPLORE_GROUPINGS if g[0] not in dict(groupings)]
    covs = EXPLORE_COVARIATES + [(c, c) for c in covariates or [] if c not in dict(EXPLORE_COVARIATES)]
    html, tests = explore_report([r for r, _ in own_entries], toppings, groupings, covs, seed)
    with open(os.path.join(out_dir, 'explore.html'), 'w', encoding='utf-8') as f:
        f.write(flag(html))
    write_csv(os.path.join(out_dir, 'explore.csv'), [
        dict({k: t.get(k) for k in ('grouping', 'level', 'vs', 'area', 'key', 'label', 'n1', 'n0', 'm1', 'm0', 'delta', 'n_per_group_80_half')},
             p='%.3g' % t['p'], q='%.3g' % t['q']) for t in tests]
        or [{'grouping': None}])
    for rec, _ in arrangement:
        rec.pop('_group', None)
    write_csv(os.path.join(out_dir, 'participants.csv'), people)
    import methods                                    # the Methods page: how every number above is counted
    write_methods(methods, os.path.join(out_dir, 'methods.html'))
    import r_export                                   # data dictionary and loader for R
    r_export.write(out_dir)
    with open(os.path.join(out_dir, 'gallery.html'), 'w', encoding='utf-8') as f:
        f.write('<!doctype html><meta charset="utf-8"><title>Pizza gallery</title>'
                '<body style="font-family:sans-serif;display:flex;flex-wrap:wrap;gap:8px">' + ''.join(cells) + '</body>')
    return people


def csv_value(v):
    """How a value is written for R (and any other reader): missing = NA, yes/no = 1/0, numbers to 6 decimals."""
    if v is None or v == '':
        return 'NA'
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, float):
        return 'NA' if v != v else round(v, 6)
    return v


def write_csv(path, rows, columns=()):
    """UTF-8, one header row, every row with every column; missing values are NA (R's read.csv reads them as NA)."""
    keys = list(columns)
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, restval='NA')
        w.writeheader()
        for r in rows:
            w.writerow({k: csv_value(v) for k, v in r.items()})


def main():
    if sys.version_info < (3, 10):
        sys.exit('The analysis needs Python 3.10 or newer (this is %d.%d).' % sys.version_info[:2])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('inputs', nargs='+', help='Qualtrics CSV export(s), demo or server JSON files, and/or the study server\'s database (study.db)')
    ap.add_argument('--out', default='pizza_results')
    ap.add_argument('--id', default='PROLIFIC_PID', help='column identifying participants (default PROLIFIC_PID, then ResponseId)')
    ap.add_argument('--builds', default='pz_,pzt_', help='field prefixes of the builds; the first is the participant\'s own pizza')
    ap.add_argument('--seed', type=int, default=1, help='seed for the random layouts behind the symmetry ratios')
    ap.add_argument('--group', default=None, help='column(s) to compare groups by, comma-separated (e.g. a diagnosis column); the first is used by the '
                    'dashboard, symmetry and profile reports, and explore.html tries all of them as well as the "About you" answers. '
                    'Default: the self-described neurotype, else the study link\'s group, else the condition')
    ap.add_argument('--covariates', default=None, help='numeric columns, comma-separated (e.g. food neophobia and disgust sensitivity scores), '
                    'correlated with every measure in explore.html')
    ap.add_argument('--clusters', type=int, default=None, help='number of clusters (default: chosen by silhouette)')
    ap.add_argument('--reference', nargs='+', default=None, help='pizzas that define "normal" (e.g. a pilot export or demo JSON files); '
                    'default: each pizza is compared with all the others in the sample')
    ap.add_argument('--study', default=None, help='analyse one study only (its id, or "main" for sessions without a study)')
    a = ap.parse_args()
    rows = read_inputs(a.inputs, a.id)
    if a.study is not None:
        rows = [r for r in rows if (r.get('study') or 'main') == a.study]
    ref_rows = read_inputs(a.reference, a.id) if a.reference else None
    split = lambda v: [c.strip() for c in (v or '').split(',') if c.strip()]
    people = analyse(rows, [b if b.endswith('_') else b + '_' for b in a.builds.split(',') if b], a.out, a.seed, split(a.group), ref_rows, a.clusters,
                     split(a.covariates))
    print('%d responses, %d pizzas scored -> %s/' % (len(rows), len(people), a.out))
    if not people:
        print('No pizza fields found. Check that pz_final / __js_pz_final are declared in the survey flow.', file=sys.stderr)


if __name__ == '__main__':
    main()
