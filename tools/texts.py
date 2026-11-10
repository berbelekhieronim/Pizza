#!/usr/bin/env python3
"""Every text a participant sees in one study, as a spreadsheet to edit, and back into the study.

    python3 tools/texts.py export pilot-2026-11 teksty.xlsx      # or .csv
    python3 tools/texts.py import pilot-2026-11 teksty.xlsx      # writes server/study.json
    python3 tools/texts.py check                                 # every language and every study's texts (the smoke test runs it)
    python3 tools/texts.py diff pilot-2026-11 [other-study]      # texts that differ from another study (or the built-in ones)

The sheet has one row per text: key, where it is shown, the current text, and an empty column for the new text. Fill in
only the texts to change. Import puts the consent and end-page texts into the study's own settings (intro, consent,
decline_message, completion_title, completion_message) and everything else into its "texts", which the participant
page and the task (pizza-builder.js) use instead of their built-in wording. Then commit and push: the site updates
itself. Placeholders such as {x}, {s} or {n} must stay in the new text. .xlsx needs openpyxl (pip install openpyxl);
.csv needs nothing.
"""
import csv
import io
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDY_JSON = os.environ.get('PIZZA_STUDY_JSON') or os.path.join(ROOT, 'server', 'study.json')   # another file for tests
sys.path.insert(0, os.path.join(ROOT, 'server'))
HEAD = ['klucz', 'gdzie się wyświetla', 'obecny tekst', 'nowy tekst (wpisz tylko, jeśli zmieniasz)']

# (key, where it is shown). study.* are the study's own settings; page.* the participant page (participate.html);
# task.* the task (pizza-builder.js); names.* the toppings. Only texts the study's flow shows are listed.
STUDY_KEYS = [('study.consent', 'Zgoda: pytanie nad przyciskami'), ('study.decline_message', 'Po wybraniu NIE: tekst'),
              ('study.completion_title', 'Strona końcowa: nagłówek'), ('study.completion_message', 'Strona końcowa: tekst nad upieczoną pizzą')]
PAGE_KEYS = [('page.consentTitle', 'Zgoda: nagłówek'), ('page.yes', 'Zgoda: przycisk TAK'), ('page.no', 'Zgoda: przycisk NIE'),
             ('page.declinedTitle', 'Po wybraniu NIE: nagłówek'), ('page.welcome', 'Komunikat po powrocie do badania (np. po odświeżeniu strony)'),
             ('page.saveFail', 'Komunikat: nie udało się zapisać'), ('page.offline', 'Komunikat: brak połączenia z internetem'),
             ('page.moment', 'Sprawdzanie, czy to człowiek: nagłówek'), ('page.botCheck', 'Sprawdzanie, czy to człowiek: tekst'),
             ('page.retrying', 'Ponowne łączenie (brak połączenia lub dużo osób naraz): tekst'),
             ('page.botFailTitle', 'Sprawdzanie nieudane: nagłówek'), ('page.botFail', 'Sprawdzanie nieudane: tekst'),
             ('page.badLink', 'Zły link: nagłówek'), ('page.cantStart', 'Badanie nie może się rozpocząć (błąd połączenia)')]
PRACTICE = [('task.promptPractice', 'Instrukcja: tekst nad pizzą')] + [('task.steps.%d' % i, 'Instrukcja: krok %d' % i) for i in range(1, 6)] + [
    ('task.practiceDone', 'Instrukcja: przycisk na końcu'), ('task.tryAgain', 'Instrukcja: podpowiedź, gdy plaster nie trafił w kółko'),
    ('task.moveHint', 'Instrukcja: podpowiedź do kroku 3 (przesuwanie)'), ('task.growHint', 'Instrukcja: podpowiedź do kroku 4 (rozmiar)'),
    ('task.removeHint', 'Instrukcja: podpowiedź do kroku 5 (usuwanie)'), ('task.practiceReady', 'Instrukcja: komunikat po ukończeniu')]
BUILD = [('task.promptBuild', 'Robienie pizzy: instrukcja nad pizzą'), ('task.toppings', 'Robienie pizzy (i instrukcja): nagłówek nad składnikami'),
         ('task.sauce', 'Robienie pizzy: etykieta „Sos”'), ('task.cheese', 'Robienie pizzy: etykieta „Ser”')] + [
    ('task.sauceNames.%s' % k, 'Robienie pizzy: sos „%s”' % k) for k in ('none', 'tomato', 'white', 'bbq')] + [
    ('task.vegan', 'Robienie pizzy: znaczek „wegański” na przyciskach sosów pomidorowego i BBQ')] + [
    ('task.cheeseNames.%s' % k, 'Robienie pizzy: ser „%s”' % k) for k in ('none', 'light', 'normal', 'extra', 'vegan')] + [
    ('task.undo', 'Robienie pizzy: przycisk Cofnij'), ('task.clear', 'Robienie pizzy: przycisk Zacznij od nowa'), ('task.done', 'Robienie pizzy: przycisk Gotowe'),
    ('task.growTapHint', 'Podpowiedź po kliknięciu składnika na pizzy (jak zmienić rozmiar)'), ('task.holdTip', 'Dymek przy zmianie rozmiaru'),
    ('task.tapHint', 'Podpowiedź po kliknięciu składnika na tacy'), ('task.full', 'Komunikat: brak miejsca na pizzy'),
    ('task.clearTitle', 'Okno „Zacznij od nowa”: pytanie'), ('task.clearBody', 'Okno „Zacznij od nowa”: tekst'), ('task.clearYes', 'Okno „Zacznij od nowa”: przycisk tak'),
    ('task.cancel', 'Okno „Zacznij od nowa”: przycisk anuluj'), ('task.confirmTitle', 'Okno po „Gotowe”: pytanie'), ('task.confirmBody', 'Okno po „Gotowe”: tekst'),
    ('task.confirmYes', 'Okno po „Gotowe”: przycisk upiecz'), ('task.confirmNo', 'Okno po „Gotowe”: przycisk wróć'), ('task.baked', 'Komunikat po upieczeniu')]
NUTRI = [('task.nutri.title', 'Tabela wartości odżywczych: nagłówek'), ('task.nutri.ri', 'Tabela wartości odżywczych: objaśnienie %'),
         ('task.nutri.perSlice', 'Tabela wartości odżywczych: kcal na kawałek ({x} = liczba kcal)'), ('task.nutri.macroTitle', 'Tabela wartości odżywczych: opis paska energii')] + [
    ('task.nutri.names.%s' % k, 'Tabela wartości odżywczych: „%s”' % k)
    for k in ('kcal', 'protein', 'carbs', 'sugars', 'fat', 'satfat', 'fibre', 'salt', 'vitA', 'vitC', 'vitD', 'calcium', 'iron')]
MET = [('task.metTitle', 'Metryczka: nagłówek'), ('task.metSub', 'Metryczka: tekst pod nagłówkiem'), ('task.metAge', 'Metryczka: pytanie o wiek'),
       ('task.metAgePh', 'Metryczka: podpowiedź w polu wieku'), ('task.metAgeBad', 'Metryczka: komunikat przy złym wieku'),
       ('task.metAutism', 'Metryczka: pytanie o autyzm'), ('task.metAdhd', 'Metryczka: pytanie o ADHD')] + [
    ('task.metDx.%s' % k, 'Metryczka: odpowiedź (autyzm i ADHD)') for k in ('no', 'formal', 'self')] + [('task.metGender', 'Metryczka: pytanie o płeć')] + [
    ('task.metGenders.%s' % k, 'Metryczka: odpowiedź o płeć') for k in ('man', 'woman', 'nonbinary', 'pnts')] + [('task.metTrans', 'Metryczka: pytanie o transpłciowość')] + [
    ('task.metTransOpts.%s' % k, 'Metryczka: odpowiedź o transpłciowość') for k in ('yes', 'no', 'pnts')] + [('task.metDiet', 'Metryczka: pytanie o dietę')] + [
    ('task.metDiets.%s' % k, 'Metryczka: odpowiedź o dietę') for k in ('vegetarian', 'vegan', 'allergy', 'other')] + [
    ('task.metDietPh', 'Metryczka: podpowiedź w polu „inna”'), ('task.finish', 'Metryczka: przycisk Zakończ')]
DESKTOP = [('task.desktopTitle', 'Telefon lub tablet: nagłówek'), ('task.desktopBody', 'Telefon lub tablet: tekst')]
NAMES = ['pep', 'ham', 'chk', 'tun', 'anc', 'mus', 'grp', 'oni', 'oli', 'crn', 'pin', 'jal', 'bas', 'shr', 'egg', 'gor', 'nor', 'kim', 'kan', 'fig', 'tof', 'tom']


def load_all():
    return json.load(open(STUDY_JSON, encoding='utf-8'), object_pairs_hook=OrderedDict)


def study_settings(sid, data=None):
    """A study's settings over the main ones (as server.load_study, from STUDY_JSON)."""
    data = data or load_all()
    own = (data.get('studies') or {}).get(sid, {}) if sid else {}
    return OrderedDict(list(data.items()) + list(own.items()))


def current_texts(sid, st):
    """{key: text the participant sees now} for the study, from the page, the task and the study's settings."""
    lang, own = st.get('lang'), st.get('texts') or {}
    html = open(os.path.join(ROOT, 'server', 'participate.html'), encoding='utf-8').read()
    words = re.search(r'  var WORDS = (\{.*?\n  \});\n', html, re.S).group(1)
    js = ("global.window = global; global.document = undefined; require(%s);"
          "var WORDS = %s; var own = %s, lang = %s;"
          "var page = Object.assign({}, WORDS[lang] || WORDS.en); for (var k in own) if (k.indexOf('page.') === 0 && own[k]) page[k.slice(5)] = own[k];"
          "console.log(JSON.stringify({ page: page, task: PizzaBuilder.texts(lang, own), names: PizzaBuilder.names(lang, own),"
          " languages: PizzaBuilder.languages, pageLanguages: Object.keys(WORDS), pageKeys: Object.keys(WORDS[lang] || {}) }));"
          % (json.dumps(os.path.join(ROOT, 'pizza-builder.js')), words, json.dumps(own), json.dumps(lang)))
    out = subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True)
    d = json.loads(out.stdout)
    current_texts.info = d

    def task(path):
        obj = d['task']
        for part in path:
            if isinstance(obj, list):
                if obj and isinstance(obj[0], list):
                    obj = next((x[1] for x in obj if x[0] == part), None)
                else:
                    obj = obj[int(part) - 1] if 0 < int(part) <= len(obj) else None
            else:
                obj = obj.get(part) if isinstance(obj, dict) else None
            if obj is None:
                return None
        return obj
    rows = []
    if not getattr(st, 'no_study_rows', False):
        for i, p in enumerate(st.get('intro') or [], 1):
            rows.append(('study.intro.%d' % i, 'Zgoda: akapit %d' % i, p))
        fallback = {'study.completion_title': d['page'].get('thanks'), 'study.decline_message': d['page'].get('declined'), 'study.consent': d['page'].get('agree')}
        for k, where in STUDY_KEYS:
            if k == 'study.decline_message' and not st.get('consent_choice'):
                continue                           # only with consent as YES / NO
            rows.append((k, where, st.get(k[6:]) or fallback.get(k) or ''))
    choice = st.get('consent_choice') or getattr(st, 'no_study_rows', False)
    for k, where in PAGE_KEYS + ([] if choice else [('page.next', 'Zgoda: przycisk Dalej (zgoda jako pole do zaznaczenia)')]):
        if not choice and k in ('page.consentTitle', 'page.yes', 'page.no', 'page.declinedTitle'):
            continue                               # these belong to consent as YES / NO
        rows.append((k, where, d['page'].get(k[5:], '')))
    cheeses, sauces = st.get('cheeses') or ['none', 'light', 'normal', 'extra'], st.get('sauces') or ['none', 'tomato', 'white', 'bbq']
    for k, where in PRACTICE + BUILD + NUTRI + (MET if st.get('followup') == 'metryczka' else []) + DESKTOP:
        parts = k.split('.')[1:]
        if parts[0] == 'cheeseNames' and parts[1] not in cheeses or parts[0] == 'sauceNames' and parts[1] not in sauces:
            continue                               # not offered in this study
        rows.append((k, where, task(parts) or ''))
    for code in NAMES:
        rows.append(('names.' + code, 'Składnik: ' + ('plaster pomidora (tylko instrukcja)' if code == 'tom' else 'nazwa na tacy'), d['names'][code]))
    # the study's own post-pizza questions (study.json "survey"): the wording they bring themselves
    if st.get('followup') == 'metryczka':
        for q in st.get('survey') or []:
            if not isinstance(q, dict) or not q.get('id'):
                continue
            if q.get('text') is not None:
                rows.append(('survey.%s.text' % q['id'], 'Ankieta po pizzy: pytanie „%s”' % q['id'], survey_word(q['text'], lang)))
            for op in q.get('options') or []:
                if isinstance(op, list) and len(op) > 1:
                    rows.append(('survey.%s.options.%s' % (q['id'], op[0]), 'Ankieta po pizzy: odpowiedź na „%s”' % q['id'], survey_word(op[1], lang)))
    return rows


def survey_word(w, lang):
    """A survey question's wording in the study's language: a string, or {pl: ..., en: ...}."""
    if isinstance(w, dict):
        return w.get(lang or 'en') or w.get('en') or next(iter(w.values()), '')
    return '' if w is None else str(w)


def set_survey_word(study, key, new, lang):
    """survey.<id>.text / survey.<id>.options.<code> from the sheet into the study's "survey" (in its language)."""
    parts = key.split('.')
    for q in study.get('survey') or []:
        if q.get('id') != parts[1]:
            continue
        if parts[2] == 'text':
            q['text'] = dict(q['text'], **{lang or 'en': new}) if isinstance(q.get('text'), dict) else new
        else:
            for op in q.get('options') or []:
                if isinstance(op, list) and str(op[0]) == parts[3]:
                    op[1] = dict(op[1], **{lang or 'en': new}) if isinstance(op[1], dict) else new
        return True
    return False


def write_sheet(rows, path):
    if path.lower().endswith('.xlsx'):
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = 'teksty'
        ws.append(HEAD)
        for r in rows:
            ws.append(list(r) + [''])
        for c, w in zip('ABCD', (26, 38, 70, 70)):
            ws.column_dimensions[c].width = w
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
            row[3].fill = PatternFill('solid', fgColor='FFF7E0')
        ws.freeze_panes = 'C2'
        wb.save(path)
    else:
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(HEAD)
            for r in rows:
                w.writerow(list(r) + [''])


def read_sheet(path):
    if path.lower().endswith('.xlsx'):
        from openpyxl import load_workbook
        ws = load_workbook(path, read_only=True).active
        it = ws.iter_rows(values_only=True)
        next(it)
        return [[('' if v is None else str(v)) for v in r[:4]] for r in it if r and r[0]]
    with open(path, encoding='utf-8-sig', newline='') as f:
        text = f.read()
    dialect = csv.Sniffer().sniff(text.split('\n', 1)[0], delimiters=',;\t')     # Excel in Polish saves with ;
    r = list(csv.reader(io.StringIO(text), dialect))
    return [row[:4] + [''] * (4 - len(row)) for row in r[1:] if row and row[0]]


def placeholders(s):
    return sorted(re.findall(r'\{\w+\}', s or ''))


def do_import(sid, path):
    data = load_all()
    if sid not in (data.get('studies') or {}):
        sys.exit('No study %s in server/study.json.' % sid)
    study = data['studies'][sid]
    known = {k: (where, cur) for k, where, cur in current_texts(sid, study_settings(sid))}
    texts = OrderedDict(study.get('texts') or {})
    intro = list(study_settings(sid).get('intro') or [])
    changed, problems = [], []
    for key, _where, _old, new in read_sheet(path):
        key, new = key.strip(), new.strip()
        if not new or key not in known or new == known[key][1]:
            if new and key not in known:
                problems.append('%s: unknown key, skipped' % key)
            continue
        if placeholders(new) != placeholders(known[key][1]):
            problems.append('%s: the new text must keep %s; skipped' % (key, ', '.join(placeholders(known[key][1])) or 'no placeholders'))
            continue
        if key.startswith('study.intro.'):
            intro[int(key.rsplit('.', 1)[1]) - 1] = new
            study['intro'] = intro
        elif key.startswith('survey.'):
            set_survey_word(study, key, new, study_settings(sid).get('lang'))
        elif key.startswith('study.'):
            study[key[6:]] = new
        else:
            texts[key] = new
        changed.append(key)
    if texts:
        study['texts'] = texts
    with open(STUDY_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('%d texts changed in %s%s' % (len(changed), sid, (': ' + ', '.join(changed)) if changed else ''))
    for p in problems:
        print('  ' + p)
    return changed, problems


class Built(OrderedDict):
    """Settings that show every text of a language: all sauces and cheeses, the metryczka, no study's own wording."""
    no_study_rows = True


ALL_SAUCES, ALL_CHEESES = ['none', 'tomato', 'white', 'bbq'], ['none', 'light', 'normal', 'extra', 'vegan']
# texts that may read the same in English and another language (brand-like names, codes): not "untranslated"
SAME_OK = {'task.sauceNames.bbq', 'task.cheeseNames.light', 'names.pep', 'names.kim', 'names.nor', 'names.tof', 'task.metAgePh'}


def built_in(lang):
    """{key: text} of the built-in texts of a language, with the language lists the page and the task know."""
    rows = current_texts('', Built(lang=lang, followup='metryczka', sauces=ALL_SAUCES, cheeses=ALL_CHEESES))
    return {k: t for k, _w, t in rows}, current_texts.info


def check():
    """Problems with the texts: a language missing or not translating a text, placeholders that do not match, lists with
    other answers; a study's own texts with unknown keys, empty texts or lost placeholders. [] = all well."""
    problems = []
    en, info = built_in('en')
    langs = info['languages']
    if sorted(langs) != sorted(info['pageLanguages']):
        problems.append('languages: the task has %s, the participant page %s' % (', '.join(sorted(langs)), ', '.join(sorted(info['pageLanguages']))))
    for lang in langs:
        if lang == 'en':
            continue
        tx, li = built_in(lang)
        if sorted(li['pageKeys']) != sorted(built_in('en')[1]['pageKeys']):
            problems.append('%s: the participant page has other texts than in English (participate.html WORDS)' % lang)
        for k, e in en.items():
            t = tx.get(k)
            if not t:
                problems.append('%s %s: missing' % (lang, k))
            elif placeholders(t) != placeholders(e):
                problems.append('%s %s: placeholders %s, English has %s' % (lang, k, placeholders(t), placeholders(e)))
            elif t == e and k not in SAME_OK:
                problems.append('%s %s: the same as in English (not translated?): %r' % (lang, k, t))
    data = load_all()
    for sid in [''] + list((data.get('studies') or {}).keys()):
        st = study_settings(sid, data)
        lang = st.get('lang') or 'en'
        name = sid or 'main'
        if lang not in langs:
            problems.append('%s: language %r has no texts (languages: %s)' % (name, lang, ', '.join(langs)))
            continue
        base = en if lang == 'en' else built_in(lang)[0]
        for k, v in (st.get('texts') or {}).items():
            if k not in base:
                problems.append('%s texts %s: unknown key' % (name, k))
            elif not isinstance(v, str) or not v.strip():
                problems.append('%s texts %s: empty' % (name, k))
            elif placeholders(v) != placeholders(base[k]):
                problems.append('%s texts %s: must keep %s' % (name, k, ', '.join(placeholders(base[k])) or 'no placeholders'))
        for k, _w, t in current_texts(sid, st):
            if not t:
                problems.append('%s %s: shows an empty text' % (name, k))
        problems += ['%s survey: %s' % (name, p) for p in survey_problems(st.get('survey'))]
    return problems


BUILTIN_QUESTIONS = ('age', 'autism', 'adhd', 'gender', 'trans', 'diet')     # worded by the task's texts (pizza-builder.js SURVEY)


def survey_problems(survey):
    """What is wrong with a study's post-pizza questions (study.json "survey"); [] = all well."""
    if survey is None:
        return []
    if not isinstance(survey, list) or not survey:
        return ['must be a list of questions']
    out, seen = [], set()
    for i, q in enumerate(survey, 1):
        qid = q.get('id') if isinstance(q, dict) else None
        if not isinstance(qid, str) or not re.match(r'^[a-z][a-z0-9_]{0,30}$', qid):
            out.append('question %d: "id" must be lower-case letters, digits or _ (it names the data column q_<id>)' % i)
            continue
        if qid in seen:
            out.append('%s: the id is used twice' % qid)
        seen.add(qid)
        kind = q.get('type')
        if kind not in ('number', 'single', 'multi', 'text'):
            out.append('%s: "type" must be number, single, multi or text' % qid)
        if qid not in BUILTIN_QUESTIONS and not q.get('text'):
            out.append('%s: needs its wording ("text")' % qid)
        opts = q.get('options')
        if kind in ('single', 'multi') and qid not in BUILTIN_QUESTIONS and not opts:
            out.append('%s: needs "options": [[code, label], ...]' % qid)
        codes = [str(o[0]) if isinstance(o, list) else str(o) for o in opts or []]
        if any(not re.match(r'^[a-z0-9_]{1,30}$', c) for c in codes):
            out.append('%s: answer codes must be lower-case letters, digits or _' % qid)
        if len(set(codes)) != len(codes):
            out.append('%s: an answer code is used twice' % qid)
        if q.get('other') and codes and q['other'] not in codes:
            out.append('%s: "other" must be one of its answer codes' % qid)
        if kind == 'number' and q.get('min') is not None and q.get('max') is not None and q['min'] > q['max']:
            out.append('%s: min is above max' % qid)
    return out


def diff(sid, other=None):
    """[(key, text in sid, text in other)] for every text that differs; other = None: the built-in texts of sid's language."""
    a = {k: t for k, _w, t in current_texts(sid, study_settings(sid))}
    if other:
        b = {k: t for k, _w, t in current_texts(other, study_settings(other))}
    else:
        st = study_settings(sid)
        b = built_in(st.get('lang') or 'en')[0]
        b.update({k: t for k, t in a.items() if k.startswith('study.')})    # a study's own settings are its own
    keys = list(a) + ([k for k in b if k not in a] if other else [])      # against the built-in texts: only what sid shows
    return [(k, a.get(k, '(not shown)'), b.get(k, '(not shown)')) for k in keys if a.get(k) != b.get(k)]


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == 'check':
        problems = check()
        for p in problems:
            print('  ' + p)
        print('texts: %s' % ('all well' if not problems else '%d problem(s)' % len(problems)))
        sys.exit(1 if problems else 0)
    if len(sys.argv) in (3, 4) and sys.argv[1] == 'diff':
        rows = diff(sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
        for k, a, b in rows:
            print('%s\n   %s: %s\n   %s: %s' % (k, sys.argv[2], a, sys.argv[3] if len(sys.argv) == 4 else 'built-in', b))
        print('%d text(s) differ' % len(rows))
        return
    if len(sys.argv) != 4 or sys.argv[1] not in ('export', 'import'):
        sys.exit(__doc__)
    cmd, sid, path = sys.argv[1:]
    if cmd == 'export':
        rows = current_texts(sid, study_settings(sid))
        write_sheet(rows, path)
        print('%d texts of %s -> %s' % (len(rows), sid, path))
    else:
        do_import(sid, path)


if __name__ == '__main__':
    main()
