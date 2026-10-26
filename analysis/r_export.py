#!/usr/bin/env python3
"""Everything R needs next to the analysis tables: variables.csv (the data dictionary: type, factor levels, unit and
description of every column of every table) and load_pizza.R (reads the tables with those types and levels).

    python3 analysis/r_export.py <analysis output folder>      # analyse.py also runs this

Descriptions come from the Methods page (methods.py), so they stay in step with the code. Standard library only.
"""
import csv
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse as A  # noqa: E402
import methods  # noqa: E402

TABLES = [('participants', 'one row per pizza (pid + build): every measure'),
          ('ingredients_long', 'one row per participant x build x tray topping'),
          ('pieces_long', 'one row per piece on a finished pizza'),
          ('events_long', 'one row per logged event'),
          ('profiles', 'one row per participant: standardised profile scores and cluster'),
          ('explore', 'one row per comparison in explore.html')]

# Factors and their level order (the first level is the reference level in models). 'ordered' = an ordered factor.
# A factor listed with levels None takes its levels from the data, in order of first appearance.
TOPPINGS = list(A.CATS)
FACTORS = {
    'build': (['pz', 'pzt'], False),
    'neurotype': (['Not ND', 'Autistic', 'ADHD', 'AuDHD', 'Other ND'], False),
    'nd_identified': (['formal', 'self or waiting'], False),
    'dx_autistic': (['formal', 'self', 'waiting', 'pnts'], False), 'dx_adhd': (['formal', 'self', 'waiting', 'pnts'], False),
    'age_band': (['18-24', '25-34', '35-44', '45-54', '55-64', '65+'], True),
    'gender': (['woman', 'man', 'nonbinary', 'other'], False),
    'diet_class': (['vegan', 'vegetarian', 'pescatarian', 'meat'], True),
    'normality_band': (['typical', 'uncommon', 'unusual'], True),
    'sauce': (['tomato', 'none', 'white', 'bbq'], False),
    'cheese': (['none', 'light', 'normal', 'extra'], True),
    'pizza_freq': (['never', 'lt1m', '1-3m', '1w', 'gt1w'], True),
    'pointer': (['mouse', 'pen', 'touch'], False),
    'tier': (['common', 'mid', 'unusual'], True),
    'zone': (['inside', 'crust', 'over'], True),
    'feel': (['cant', 'dislike', 'mixed', 'like', 'love'], True),
    'safe_food': (['no', 'sometimes', 'yes'], True), 'same_way': (['no', 'sometimes', 'yes'], True),
    'crave': (['never', 'sometimes', 'often'], True),
    'ing': (TOPPINGS, False), 'first_topping': (TOPPINGS, False),
    'cat': (None, False), 'group': (None, False), 'condition': (None, False), 'cluster': (None, False),
    'type': (None, False), 'layout': (None, False), 'grouping': (None, False), 'area': (None, False),
    'face_mouth': (None, False), 'face_eyes': (None, False),
}
# the explore table's own 'level' column holds group names of different groupings: left as text
TEXT_ALWAYS = {'pid', 'a', 'b', 'level', 'vs', 'key', 'label', 'strong_list', 'unusual_elements', 'diet', 'diet_other',
               'health_other', 'why_other_text', 'name'}


def unit(col):
    if col in ('x', 'y', 'r', 'mean_r', 'sd_r', 'centroid_offset', 'mirror_cx', 'mirror_cy', 'rot_cx', 'rot_cy'):
        return 'pizza radii (crust edge = 1 = 15 cm)'
    if col.endswith('_deg') or col == 'rot':
        return 'degrees'
    if col.endswith('_mm'):
        return 'mm'
    if col.endswith('_cm2'):
        return 'cm2'
    if col.endswith('_ms') or col.startswith('t_') or col in ('decision_median', 'add_gap_median', 'drag_median', 'hiddenMs', 'mv_dwell',
                                                              'mv_hold', 'mv_longest_pause', 'practice_ms', 'practice_drag_median'):
        return 'ms'
    if col.endswith('_pct') or col in ('composition_pct', 'count_pct'):
        return 'percentile (0-100)'
    if col == 'atypicality_bits':
        return 'bits'
    if col == 'mv_path':
        return 'pizza diameters'
    if col == 'pizzaPx' or col in ('vw', 'vh'):
        return 'px'
    return ''


def column_type(col, values):
    """integer / double / character / factor / ordered, from the declared factors and the values present."""
    if col in FACTORS:
        return 'ordered' if FACTORS[col][1] else 'factor'
    present = [v for v in values if v != 'NA']
    if col in TEXT_ALWAYS or not present:
        return 'character' if present or col in TEXT_ALWAYS else 'double'
    try:
        nums = [float(v) for v in present]
    except ValueError:
        return 'character'
    return 'integer' if all(re.fullmatch(r'-?\d+', v) for v in present) and all(abs(x) < 2 ** 31 for x in nums) else 'double'


def dictionary(out_dir):
    rows = []
    for table, _ in TABLES:
        path = os.path.join(out_dir, table + '.csv')
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8', newline='') as f:
            data = list(csv.reader(f))
        header, body = data[0], data[1:]
        for i, col in enumerate(header):
            values = [r[i] for r in body if i < len(r)]
            t = column_type(col, values)
            levels = ''
            if t in ('factor', 'ordered'):
                declared = FACTORS[col][0]
                seen = []
                for v in values:
                    if v != 'NA' and v not in seen:
                        seen.append(v)
                lv = list(declared) if declared else seen
                lv += [v for v in seen if v not in lv]          # values the declaration does not list are kept, at the end
                levels = '|'.join(lv)
            section, text = methods.describe(col, table)
            if col.startswith('z_'):
                _, base = methods.describe(col[2:], 'participants')
                text = 'Profile score (z, ±3) of %s: %s' % (col[2:], base or '')
            rows.append({'file': table, 'column': col, 'type': t, 'levels': levels, 'unit': unit(col),
                         'section': section or '', 'description': text or ''})
    return rows


def write(out_dir):
    rows = dictionary(out_dir)
    with open(os.path.join(out_dir, 'variables.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['file', 'column', 'type', 'levels', 'unit', 'section', 'description'])
        w.writeheader()
        w.writerows(rows)
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'load_pizza.R'), os.path.join(out_dir, 'load_pizza.R'))
    return rows


if __name__ == '__main__':
    write(sys.argv[1] if len(sys.argv) > 1 else 'pizza_results')
