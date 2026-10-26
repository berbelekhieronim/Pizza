#!/usr/bin/env python3
"""Benchmark for face detection: how often face_detect() finds drawn faces of many styles, and how often it flags
pizzas that are not faces. Every pizza is generated with a random rotation and some wobble, from a fixed seed.

    python3 tests/face_benchmark.py            # rates per kind of pizza
    python3 tests/face_benchmark.py --n 400    # more pizzas per kind (slower, steadier rates)
"""
import argparse
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'analysis'))
import analyse as A  # noqa: E402

ROUND = ['pep', 'oli', 'mus', 'jal', 'egg', 'tom', 'pin', 'ham', 'chk', 'kim', 'gor']
LONG = ['anc', 'grp', 'bas', 'oni']
SMALL = ['crn', 'oli', 'jal', 'gor']


def P(ing, x, y, rot=0, s=1.0, g=1.0):
    return {'ing': ing, 'x': x, 'y': y, 'rot': rot % 360, 's': s * g, 'g': g}


class Gen:
    def __init__(self, seed):
        self.R = random.Random(seed)

    def j(self, v, a=0.025):
        return v + self.R.uniform(-a, a)

    def rotate(self, pcs, shift=(0, 0)):
        a = self.R.uniform(0, 2 * math.pi)
        c, s = math.cos(a), math.sin(a)
        out = []
        for p in pcs:
            x, y = p['x'] + shift[0], p['y'] + shift[1]
            q = dict(p, x=c * x - s * y, y=s * x + c * y, rot=(p['rot'] - math.degrees(a)) % 360)
            r = math.hypot(q['x'], q['y'])
            if r > 0.95:
                q['x'], q['y'] = q['x'] * 0.95 / r, q['y'] * 0.95 / r
            out.append(q)
        return out

    def scatter_n(self, n, ings, rmax=0.85, rmin=0.0):
        out = []
        for _ in range(n):
            r = math.sqrt(self.R.uniform(rmin ** 2, rmax ** 2))
            t = self.R.uniform(0, 2 * math.pi)
            out.append(P(self.R.choice(ings), r * math.cos(t), r * math.sin(t), self.R.randrange(360), self.R.uniform(0.9, 1.1)))
        return out

    # ---- parts of a face, upright, eyes at y = ey and x = +-ex
    def eyes(self, ex, ey, kind='round'):
        R = self.R
        if kind == 'round':
            ing = R.choice(['pep', 'oli', 'mus', 'egg', 'tom', 'jal'])
            return [P(ing, self.j(-ex), self.j(ey)), P(ing, self.j(ex), self.j(ey))]
        if kind == 'pupils':
            ing, pup = R.choice([('pep', 'oli'), ('egg', 'oli'), ('tom', 'oli'), ('pep', 'jal')])
            out = []
            for sx in (-1, 1):
                x, y = self.j(sx * ex), self.j(ey)
                out += [P(ing, x, y), P(pup, x + R.uniform(-0.02, 0.02), y + R.uniform(-0.02, 0.02))]
            return out
        if kind == 'cluster':                      # each eye a small heap of touching pieces
            ing = R.choice(SMALL)
            out = []
            for sx in (-1, 1):
                for _ in range(R.randint(3, 5)):
                    out.append(P(ing, self.j(sx * ex, 0.04), self.j(ey, 0.04), R.randrange(360)))
            return out
        if kind == 'mixed':                        # two different toppings of similar size
            a, b = R.choice([('pep', 'tom'), ('mus', 'egg'), ('oli', 'jal'), ('ham', 'chk'), ('pin', 'kim')])
            return [P(a, self.j(-ex), self.j(ey)), P(b, self.j(ex), self.j(ey))]
        raise ValueError(kind)

    def mouth(self, my, half, kind='row'):
        R = self.R
        if kind == 'row':
            k, ing, curve = R.randint(3, 7), R.choice(['oli', 'pep', 'crn', 'mus', 'jal', 'shr']), R.uniform(0, 0.15)
            return [P(ing, self.j(t * half, 0.015), self.j(my + curve * t * t, 0.015)) for t in [-1 + 2 * i / (k - 1) for i in range(k)]]
        if kind == 'mixedrow':
            k, ings, curve = R.randint(4, 7), R.sample(['oli', 'crn', 'jal', 'mus'], 2), R.uniform(0, 0.15)
            return [P(ings[i % 2], self.j(t * half, 0.015), self.j(my + curve * t * t, 0.015)) for i, t in enumerate([-1 + 2 * i / (k - 1) for i in range(k)])]
        if kind == 'long':
            return [P(R.choice(LONG), self.j(0, 0.03), self.j(my), R.choice([0, 180]) + R.uniform(-15, 15), R.uniform(1.0, 1.4))]
        raise ValueError(kind)

    def face(self, eye_kind='round', mouth_kind='row', extras=(), scale=1.0, shift=(0, 0)):
        R = self.R
        ex, ey, my = R.uniform(0.2, 0.36) * scale, R.uniform(0.15, 0.35) * scale, -R.uniform(0.3, 0.5) * scale
        pcs = self.eyes(ex, ey, eye_kind) + self.mouth(my, max(0.18, ex * R.uniform(0.9, 1.3)), mouth_kind)
        if 'nose' in extras or R.random() < 0.4:
            pcs.append(P(R.choice(['mus', 'pin', 'tom', 'oli']), self.j(0, 0.03), self.j((ey + my) / 2 + 0.05, 0.04)))
        if 'brows' in extras:
            ing = R.choice(LONG)
            pcs += [P(ing, self.j(sx * ex), self.j(ey + R.uniform(0.13, 0.18) * scale), R.uniform(-20, 20) + (sx * 10), 0.8) for sx in (-1, 1)]
        if 'cheeks' in extras:
            ing = R.choice(['pep', 'tom', 'ham'])
            pcs += [P(ing, self.j(sx * ex * 1.35), self.j((ey + my) / 2), 0, 0.8) for sx in (-1, 1)]
        if 'hair' in extras:
            ing = R.choice(['bas', 'grp', 'oni', 'crn', 'oli'])
            for _ in range(R.randint(6, 14)):
                t = R.uniform(math.radians(20), math.radians(160))
                pcs.append(P(ing, 0.82 * math.cos(t), 0.82 * math.sin(t), R.randrange(360)))
        return self.rotate(pcs, shift)

    # ---- not faces
    def mirror(self):
        pcs, ings = [], self.R.sample(ROUND, self.R.randint(1, 4))
        for _ in range(self.R.randint(3, 12)):
            x, y, ing = self.R.uniform(0.05, 0.8), self.R.uniform(-0.8, 0.8), self.R.choice(ings)
            pcs += [P(ing, x, y), P(ing, -x, y)]
        return self.rotate(pcs)

    def ring(self):
        k, ing = self.R.randint(4, 12), self.R.choice(ROUND + SMALL)
        pcs = [P(ing, 0.6 * math.cos(2 * math.pi * i / k), 0.6 * math.sin(2 * math.pi * i / k)) for i in range(k)]
        if self.R.random() < 0.5:
            ing2 = self.R.choice(ROUND)
            pcs += [P(ing2, 0.3 * math.cos(2 * math.pi * i / k + 0.4), 0.3 * math.sin(2 * math.pi * i / k + 0.4)) for i in range(k)]
        if self.R.random() < 0.5:
            pcs.append(P(self.R.choice(ROUND), 0, 0))
        return self.rotate(pcs)

    def halves(self):
        a, b = self.R.sample(ROUND, 2)
        pcs = []
        for _ in range(self.R.randint(5, 12)):
            r, t = 0.8 * math.sqrt(self.R.random()), self.R.uniform(-1.4, 1.4)
            pcs.append(P(a, r * math.cos(t), r * math.sin(t)))
            r, t = 0.8 * math.sqrt(self.R.random()), self.R.uniform(1.75, 4.5)
            pcs.append(P(b, r * math.cos(t), r * math.sin(t)))
        return self.rotate(pcs)

    def piles(self):
        pcs = []
        for _ in range(self.R.randint(2, 4)):
            cx, cy, ing = self.R.uniform(-0.6, 0.6), self.R.uniform(-0.6, 0.6), self.R.choice(ROUND + SMALL)
            pcs += [P(ing, self.j(cx, 0.05), self.j(cy, 0.05)) for _ in range(self.R.randint(2, 5))]
        return self.rotate(pcs)

    def grid(self):
        step, ing = self.R.uniform(0.25, 0.4), self.R.choice(ROUND)
        pcs = [P(ing, self.j(i * step), self.j(k * step)) for i in range(-3, 4) for k in range(-3, 4) if math.hypot(i * step, k * step) < 0.82]
        return self.rotate(pcs)

    def slices(self):
        a, b = self.R.sample(ROUND, 2)
        pcs = []
        for s in range(8):
            t = s * math.pi / 4 + 0.39
            pcs += [P(a, 0.35 * math.cos(t), 0.35 * math.sin(t)), P(b, 0.68 * math.cos(t), 0.68 * math.sin(t))]
        return self.rotate(pcs)

    def smile_only(self):
        return self.rotate(self.mouth(-0.35, 0.3, self.R.choice(['row', 'long'])) + self.scatter_n(self.R.randint(0, 3), ROUND, 0.85, 0.7))

    def eyes_only(self):
        return self.rotate(self.eyes(0.3, 0.25, 'round') + self.scatter_n(self.R.randint(0, 3), ROUND, 0.85, 0.7))


FACES = [
    ('classic: round eyes, row smile', lambda g: g.face('round', 'row')),
    ('long-piece mouth', lambda g: g.face('round', 'long')),
    ('eyes with pupils', lambda g: g.face('pupils', g.R.choice(['row', 'long']))),
    ('eyes made of small clusters', lambda g: g.face('cluster', g.R.choice(['row', 'long']))),
    ('two different eye toppings', lambda g: g.face('mixed', g.R.choice(['row', 'long']))),
    ('with eyebrows', lambda g: g.face('round', g.R.choice(['row', 'long']), ('brows',))),
    ('with hair round the rim', lambda g: g.face(g.R.choice(['round', 'pupils']), g.R.choice(['row', 'long']), ('hair',))),
    ('mouth of mixed toppings', lambda g: g.face('round', 'mixedrow')),
    ('whole-pizza face', lambda g: g.face(g.R.choice(['round', 'pupils']), 'row', ('nose',), scale=1.7)),
    ('small face off-centre', lambda g: g.face('round', g.R.choice(['row', 'long']), (), 0.75, (g.R.uniform(-0.3, 0.3), g.R.uniform(-0.3, 0.3)))),
    ('with cheeks', lambda g: g.face('round', 'row', ('nose', 'cheeks'))),
]
NOT_FACES = [
    ('random scatter, 4-8 pieces', lambda g: g.scatter_n(g.R.randint(4, 8), g.R.sample(ROUND + LONG + SMALL, g.R.randint(1, 4)))),
    ('random scatter, 9-20 pieces', lambda g: g.scatter_n(g.R.randint(9, 20), g.R.sample(ROUND + LONG + SMALL, g.R.randint(1, 5)))),
    ('random scatter, 21-40 pieces', lambda g: g.scatter_n(g.R.randint(21, 40), g.R.sample(ROUND + LONG + SMALL, g.R.randint(2, 6)))),
    ('mirror-symmetric', lambda g: g.mirror()),
    ('rings of toppings', lambda g: g.ring()),
    ('half-and-half', lambda g: g.halves()),
    ('piles', lambda g: g.piles()),
    ('grid', lambda g: g.grid()),
    ('repeating slices', lambda g: g.slices()),
    ('a smile without eyes', lambda g: g.smile_only()),
    ('eyes without a mouth', lambda g: g.eyes_only()),
]


def run(n, seed=7, quiet=False):
    g = Gen(seed)
    res = {}
    for label, make in FACES + NOT_FACES:
        hits = sum(A.face_detect(make(g)) is not None for _ in range(n))
        res[label] = hits / n
    if not quiet:
        print('Faces (want high):')
        for label, _ in FACES:
            print('  %-34s %5.1f%%' % (label, 100 * res[label]))
        print('Not faces (want low):')
        for label, _ in NOT_FACES:
            print('  %-34s %5.1f%%' % (label, 100 * res[label]))
        hit = sum(res[l] for l, _ in FACES) / len(FACES)
        fp = sum(res[l] for l, _ in NOT_FACES) / len(NOT_FACES)
        print('\nAverage: faces found %.1f%%, non-faces flagged %.1f%% (worst %.1f%%)' % (100 * hit, 100 * fp, 100 * max(res[l] for l, _ in NOT_FACES)))
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--n', type=int, default=150, help='pizzas per kind')
    ap.add_argument('--seed', type=int, default=7)
    a = ap.parse_args()
    run(a.n, a.seed)
