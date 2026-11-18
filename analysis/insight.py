"""Reading the pizzas in plain words, for the reports (dashboard.html, explore.html, profiles.html).

What a behavioural scientist needs from these data before any test: who took part, how the study ran, whether each
measure can tell people apart, and which differences are really one difference. Everything here is computed from the
analysed own pizzas (one row per person: the person is the unit, never the piece) and from the sessions.

- Piece count. Many measures of a pizza rise or fall with how many pieces are on it (more pieces touch, stack and cover
  more of the pizza). When groups differ in pieces, a difference in such a measure can just repeat that difference.
  piece_adjusted() compares groups on what is left of a measure once the number of pieces is taken into account: the
  ranks of the measure regressed on the ranks of log(pieces), compared on the residuals (rank-based, so one huge pizza
  does not decide it).
- Effect sizes in words. Cliff's delta d becomes the chance that a person from one group is higher than a person from
  the other (the common-language effect size, (d + 1) / 2; ties count half), and a size word (Romano et al. 2006).
- The measure check: spread, floor / ceiling, link with piece count, and a plain verdict for each key measure.

No significance tests here: with pilot-sized groups they say little; Explore has them, labelled as exploration.
"""
import math
import statistics
from collections import Counter

# The measures a reader most needs, in plain words: (key, label, what it captures, unit). The order is the order shown.
KEY_MEASURES = [
    ('n_pieces', 'Pieces placed', 'how much they put on the pizza', 'pieces'),
    ('n_distinct', 'Different toppings', 'how many kinds of topping they chose', 'toppings'),
    ('diet_rank', 'Animal products', '0 = vegan, 1 = vegetarian, 2 = fish, 3 = meat', ''),
    ('nut_kcal', 'Energy', 'kcal of the whole pizza, base included', 'kcal'),
    ('atypicality_bits', 'Unusual combination', 'how surprising the set of toppings is, against the other pizzas', 'bits'),
    ('prop_touching', 'Touching', 'share of pieces that touch another piece', 'share'),
    ('prop_stacked', 'Stacking', 'share of pieces on top of another', 'share'),
    ('coverage', 'Coverage', 'share of the pizza covered by toppings', 'share'),
    ('clark_evans', 'Spread', 'below 1 clumped together, about 1 random, above 1 evenly spread', 'ratio'),
    ('mirror_score', 'Mirror symmetry', '0 = no more than chance, 1 = every piece has a mirror partner', 'score'),
    ('blockiness', 'Placed topping by topping', 'whether they put on one topping at a time rather than switching (0 = as random)', 'score'),
    ('resized_share', 'Pieces resized', 'share of pieces made bigger or smaller', 'share'),
    ('decision_median', 'Decision time', 'typical pause between one action and picking up the next topping', 'ms'),
    ('t_active', 'Time on the pizza', 'time spent building (time on other tabs removed)', 'ms'),
    ('revision_rate', 'Changes of mind', 'pieces taken off again, per piece added (0 = nothing taken back)', 'share'),
]
LABELS = {k: lab for k, lab, _, _ in KEY_MEASURES}
# measures that are about amount by definition: not "explained by the number of pieces"
AMOUNT = ('n_pieces', 'topping_area_cm2', 't_active', 't_submit')

# The comparison the reports lead with: the first of these with 3 or more people on each side.
CONTRASTS = [('nd_any', 'Neurodivergent', 'Not neurodivergent'), ('nd_autistic', 'Autistic (incl. AuDHD)', 'Not autistic'),
             ('nd_adhd', 'ADHD (incl. AuDHD)', 'No ADHD')]
MIN_GROUP = 3
TIED_STRONG, TIED_SOME = 0.7, 0.45      # |rho| with the number of pieces: mostly / partly a matter of how many pieces
TANGLED = 0.9      # groups this far apart in pieces (|Cliff's delta|) overlap too little to take the pieces into account


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and not (isinstance(v, float) and math.isnan(v)) else None


def ranks(vals):
    """Mid-ranks (ties share the mean rank), 1-based."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out, i = [0.0] * len(vals), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(a, b):
    """Spearman's rho over the pairs where both are numbers (None with fewer than 5 pairs or no spread)."""
    pairs = [(x, y) for x, y in zip(a, b) if num(x) is not None and num(y) is not None]
    if len(pairs) < 5:
        return None
    ra, rb = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    sa = math.sqrt(sum((x - ma) ** 2 for x in ra))
    sb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    if sa == 0 or sb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (sa * sb)


def cliff(x, y):
    """Cliff's delta: P(X > Y) - P(X < Y) over all pairs."""
    if not x or not y:
        return None
    gt = sum(1 for a in x for b in y if a > b)
    lt = sum(1 for a in x for b in y if a < b)
    return (gt - lt) / (len(x) * len(y))


def chance_higher(d):
    """The common-language effect size: the chance that a person from the first group is higher (ties count half)."""
    return None if d is None else (d + 1) / 2


def size_word(d):
    """Romano et al. (2006) for Cliff's delta, in everyday words."""
    a = abs(d or 0)
    return 'no real difference' if a < .147 else 'a small difference' if a < .33 else 'a medium difference' if a < .474 else 'a large difference'


def residuals_on_pieces(values, pieces):
    """What is left of a measure once the number of pieces is taken into account: the ranks of the measure minus their
    least-squares line on the ranks of log(pieces). None where either is missing; None overall with fewer than 6."""
    idx = [i for i, (v, p) in enumerate(zip(values, pieces)) if num(v) is not None and num(p) is not None and p > 0]
    if len(idx) < 6:
        return None
    rv = ranks([values[i] for i in idx])
    rp = ranks([math.log(pieces[i]) for i in idx])
    mp, mv = statistics.mean(rp), statistics.mean(rv)
    sxx = sum((x - mp) ** 2 for x in rp)
    b = sum((x - mp) * (y - mv) for x, y in zip(rp, rv)) / sxx if sxx else 0.0
    out = [None] * len(values)
    for i, x, y in zip(idx, rp, rv):
        out[i] = y - (mv + b * (x - mp))
    return out


def compare(recs, key, in_a, in_b, adjust=True):
    """One measure between two groups of people (in_a / in_b: functions of a record): medians, Cliff's delta, and the
    delta once the number of pieces is taken into account (None for amount measures, or with too few people)."""
    vals = [num(r.get(key)) for r in recs]
    a = [v for r, v in zip(recs, vals) if v is not None and in_a(r)]
    b = [v for r, v in zip(recs, vals) if v is not None and in_b(r)]
    if len(a) < MIN_GROUP or len(b) < MIN_GROUP:
        return None
    out = {'key': key, 'n_a': len(a), 'n_b': len(b), 'med_a': statistics.median(a), 'med_b': statistics.median(b), 'a': a, 'b': b,
           'd': cliff(a, b), 'd_adj': None, 'tangled': False}
    # when the groups barely overlap in the number of pieces, nothing can separate a difference from the pieces: say so
    pa = [num(r.get('n_pieces')) for r in recs if in_a(r) and num(r.get('n_pieces')) is not None]
    pb = [num(r.get('n_pieces')) for r in recs if in_b(r) and num(r.get('n_pieces')) is not None]
    if adjust and key not in AMOUNT and pa and pb and abs(cliff(pa, pb)) >= TANGLED:
        out['tangled'] = True
        return out
    have = [v for v in vals if v is not None]
    flat = len(set(have)) <= 2 or Counter(have).most_common(1)[0][1] >= 0.8 * len(have)     # ranks of a near-constant measure are mostly ties
    if adjust and key not in AMOUNT and not flat:
        res = residuals_on_pieces(vals, [num(r.get('n_pieces')) for r in recs])
        if res:
            ra = [v for r, v in zip(recs, res) if v is not None and in_a(r)]
            rb = [v for r, v in zip(recs, res) if v is not None and in_b(r)]
            if len(ra) >= MIN_GROUP and len(rb) >= MIN_GROUP:
                out['d_adj'] = cliff(ra, rb)
    return out


def pieces_explain(c):
    """True when a clear raw difference mostly disappears once the number of pieces is taken into account."""
    return bool(c and c.get('d_adj') is not None and abs(c['d']) >= 0.33 and abs(c['d_adj']) < abs(c['d']) / 2)


def contrast(recs):
    """The comparison to lead with: (key, label for 1, label for 0), or None when no grouping has 3+ on each side."""
    for key, la, lb in CONTRASTS:
        vals = [r.get(key) for r in recs]
        if sum(1 for v in vals if v == 1) >= MIN_GROUP and sum(1 for v in vals if v == 0) >= MIN_GROUP:
            return key, la, lb
    return None


def measure_check(recs, measures=KEY_MEASURES):
    """For each key measure: how many have it, its median and range, how many share its most common value (a floor or
    ceiling hides differences), its link with the number of pieces, and a verdict in words."""
    pieces = [num(r.get('n_pieces')) for r in recs]
    out = []
    for key, label, what, unit in measures:
        vals = [num(r.get(key)) for r in recs]
        have = [v for v in vals if v is not None]
        row = {'key': key, 'label': label, 'what': what, 'unit': unit, 'n': len(have), 'values': have}
        if len(have) < 5:
            row.update(verdict='few', words='too few pizzas with this measure yet')
            out.append(row)
            continue
        top_v, top_n = Counter(round(v, 6) for v in have).most_common(1)[0]
        rho = None if key == 'n_pieces' else spearman(vals, pieces)
        row.update(median=statistics.median(have), lo=min(have), hi=max(have), top_share=top_n / len(have), top_value=top_v, rho=rho)
        if len(set(round(v, 6) for v in have)) <= 1:
            row.update(verdict='flat', words='the same for everyone: it cannot tell people apart here')
        elif top_n / len(have) >= 0.8:
            row.update(verdict='flat', words='%d of %d pizzas have the same value (%s): it hardly tells people apart here' % (top_n, len(have), fmt_value(top_v, unit)))
        elif rho is not None and abs(rho) >= TIED_STRONG and key not in AMOUNT:
            row.update(verdict='pieces', words='rises and falls with the number of pieces (ρ = %+.2f): mostly a measure of how much is on the pizza' % rho)
        elif rho is not None and abs(rho) >= TIED_SOME and key not in AMOUNT:
            row.update(verdict='partly', words='partly follows the number of pieces (ρ = %+.2f): compare groups with the pieces taken into account' % rho)
        else:
            row.update(verdict='ok', words='varies between people' + (' and does not just follow the number of pieces (ρ = %+.2f)' % rho if rho is not None and key not in AMOUNT else ''))
        out.append(row)
    return out


def fmt_value(v, unit):
    """A value in its unit, for sentences: seconds for ms, % for shares."""
    if v is None:
        return '–'
    if unit == 'ms':
        s = v / 1000
        return ('%.1f s' % s) if s < 60 else ('%.1f min' % (s / 60))
    if unit == 'share':
        return '%.0f%%' % (100 * v)
    if unit in ('kcal', 'pieces', 'toppings') or abs(v) >= 100:
        return '%.0f%s' % (v, (' ' + unit) if unit else '')
    return '%.2f' % v


def times_out_of_ten(d):
    """'9 times out of 10' for the chance that the first group is higher."""
    p = chance_higher(d)
    return None if p is None else int(round(p * 10))
