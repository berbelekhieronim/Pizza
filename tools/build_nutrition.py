#!/usr/bin/env python3
"""Builds analysis/nutrition.json from the USDA National Nutrient Database for Standard Reference, Release 28
(public domain; the "abbreviated" table ABBREV.txt, which the npm package fda-nutrient-database also ships):

    python3 tools/build_nutrition.py path/to/ABBREV.txt

and copies the table into pizza-builder.js (between the NUTRITION-DATA markers), so the task and the analysis use the
same numbers. For each ingredient: the SR28 food used (NDB number and name; a stand-in where SR28 has no entry), the
grams one standard piece weighs, and the nutrients per 100 g. Reference intakes: EU Regulation 1169/2011, Annex XIII
(fibre: EFSA's adequate intake, 25 g).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# SR28 ABBREV columns (sr28_doc.pdf, p. 44), 0-based
COL = {'kcal': 3, 'protein': 4, 'fat': 5, 'carbs': 7, 'fibre': 8, 'sugars': 9, 'calcium': 10, 'iron': 11, 'potassium': 14,
       'sodium': 15, 'vitC': 20, 'folate': 29, 'vitB12': 31, 'vitA': 33, 'vitD': 41, 'satfat': 44}
# code: (NDB number, grams in one standard piece (size 1), note). Piece weights are typical weights of one piece of that
# size on a 30 cm pizza (e.g. a 4 cm pepperoni slice ~3 g); they are estimates, listed so they can be checked.
FOODS = {
    'pep': ('07057', 3.0, ''), 'ham': ('07029', 3.0, ''), 'chk': ('05064', 5.0, ''),
    'tun': ('15121', 3.0, ''), 'anc': ('15002', 3.0, ''), 'mus': ('11260', 3.0, ''), 'grp': ('11333', 3.0, ''),
    'oni': ('11282', 2.0, 'SR28 has onions, raw (no separate red onion)'), 'oli': ('09193', 1.0, ''),
    'crn': ('11172', 1.0, 'a pinch of 3 kernels'), 'pin': ('09266', 6.0, ''), 'jal': ('11632', 1.5, ''), 'bas': ('02044', 0.5, ''),
    'shr': ('15271', 6.0, ''), 'egg': ('01129', 8.0, 'one slice of a hard-boiled egg'), 'gor': ('01004', 2.0, ''),
    'nor': ('11446', 0.5, 'nori = laver; SR28 lists it raw'), 'kim': ('11118', 5.0, ''),
    'kan': ('17165', 6.0, 'stand-in: SR28 has no kangaroo; venison (deer, roasted) is the closest lean red game meat'),
    'fig': ('09089', 10.0, 'half a fig'), 'par': ('09252', 6.0, ''), 'ban': ('09040', 5.0, ''), 'wal': ('12155', 2.0, 'half a walnut'),
    'tom': ('11529', 12.0, 'practice only'),
}
# the base of a 30 cm pizza: grams for each choice
BASE = {
    'dough': ('18033', 250.0, 'stand-in: SR28 has no pizza crust; Italian bread is the same baked dough'),
    'sauce': {'tomato': ('06152', 80.0, ''), 'white': ('06264', 80.0, 'white sauce (bechamel)'), 'bbq': ('06150', 60.0, ''), 'none': (None, 0.0, '')},
    'cheese': {'none': (None, 0.0, ''), 'light': ('01028', 60.0, 'mozzarella, part-skim'), 'normal': ('01028', 100.0, 'mozzarella, part-skim'),
               'extra': ('01028', 150.0, 'mozzarella, part-skim')},
}
UNITS = {'kcal': 'kcal', 'protein': 'g', 'carbs': 'g', 'sugars': 'g', 'fat': 'g', 'satfat': 'g', 'fibre': 'g', 'salt': 'g',
         'vitA': 'µg', 'vitC': 'mg', 'vitD': 'µg', 'vitB12': 'µg', 'folate': 'µg', 'calcium': 'mg', 'iron': 'mg', 'potassium': 'mg'}
RI = {'kcal': 2000, 'protein': 50, 'carbs': 260, 'sugars': 90, 'fat': 70, 'satfat': 20, 'fibre': 25, 'salt': 6, 'vitA': 800, 'vitC': 80,
      'vitD': 5, 'vitB12': 2.5, 'folate': 200, 'calcium': 800, 'iron': 14, 'potassium': 2000}


def read_abbrev(path):
    out = {}
    with open(path, encoding='latin-1') as f:
        for line in f:
            p = [x.strip('~') for x in line.rstrip('\r\n').split('^')]
            out[p[0]] = p
    return out


def per100(row):
    v = {}
    for k, i in COL.items():
        v[k] = float(row[i]) if row[i] not in ('', None) else 0.0      # blank = not measured: counted as 0, see the note
    v['salt'] = round(v.pop('sodium') * 2.5 / 1000, 4)                 # salt = sodium x 2.5 (EU 1169/2011), mg -> g
    return {k: round(x, 4) for k, x in v.items()}


def entry(db, ndb, grams, note):
    if ndb is None:
        return {'ndb': None, 'food': None, 'grams': 0.0, 'note': note, 'per100': None}
    row = db[ndb]
    return {'ndb': ndb, 'food': row[1], 'grams': grams, 'note': note, 'per100': per100(row)}


def main(path):
    db = read_abbrev(path)
    data = {'source': 'USDA National Nutrient Database for Standard Reference, Release 28 (2015), ABBREV table; public domain',
            'reference_intakes': 'EU Regulation 1169/2011 Annex XIII; fibre: EFSA adequate intake 25 g', 'units': UNITS, 'ri': RI,
            'size_rule': 'grams of a piece = grams of a standard piece x s^2 (s = drawn size: random 0.9-1.1 x the hold-to-resize factor g)',
            'toppings': {k: entry(db, *v) for k, v in FOODS.items()},
            'base': {'dough': entry(db, *BASE['dough']),
                     'sauce': {k: entry(db, *v) for k, v in BASE['sauce'].items()},
                     'cheese': {k: entry(db, *v) for k, v in BASE['cheese'].items()}}}
    with open(os.path.join(ROOT, 'analysis', 'nutrition.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write('\n')
    js_path = os.path.join(ROOT, 'pizza-builder.js')
    js = open(js_path, encoding='utf-8').read()
    block = '  // NUTRITION-DATA (generated by tools/build_nutrition.py from analysis/nutrition.json; do not edit by hand)\n  var NUTRITION = %s;\n  // END NUTRITION-DATA\n' % json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    if '// NUTRITION-DATA' in js:
        js = re.sub(r'  // NUTRITION-DATA.*?// END NUTRITION-DATA\n', lambda m: block, js, flags=re.S)
    else:
        js = js.replace('  // ---------------------------------------------------------------- toppings\n', block + '\n  // ---------------------------------------------------------------- toppings\n', 1)
    open(js_path, 'w', encoding='utf-8').write(js)
    for k, e in data['toppings'].items():
        print('%-4s %-6s %-55s %5.1f g  %6.1f kcal/100g' % (k, e['ndb'], e['food'], e['grams'], e['per100']['kcal']))


if __name__ == '__main__':
    main(sys.argv[1])
