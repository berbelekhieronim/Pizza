# The post-pizza survey of a study

After the pizza, a study can ask its own short questions instead of the standard follow-up (strong feelings about
ingredients, About you). Pizza Pilot 11.2026 does this: its *metryczka*. The questions are set per study in
`server/study.json`, so each version of the study can ask different ones without touching the code.

## Setting it up

In the study's settings (`"studies": {"<id>": {...}}`):

```json
"followup": "metryczka",
"survey": [
  {"id": "age", "type": "number", "min": 16, "max": 99},
  {"id": "autism", "type": "single"},
  {"id": "adhd", "type": "single"},
  {"id": "gender", "type": "single"},
  {"id": "trans", "type": "single"},
  {"id": "diet", "type": "multi", "other": "other"},
  {"id": "sleep", "type": "single", "text": "Jak spałeś/spałaś ostatniej nocy?",
   "options": [["well", "dobrze"], ["average", "średnio"], ["badly", "źle"]]},
  {"id": "hungry", "type": "number", "text": "Jak bardzo jesteś teraz głodny/głodna? (0-10)", "min": 0, "max": 10},
  {"id": "comment", "type": "text", "text": "Uwagi (opcjonalnie)", "required": false}
]
```

Each question:

| key | meaning |
|---|---|
| `id` | a short name, lower-case letters, digits or `_`; it names the answer in the data (`met.<id>`, column `q_<id>`) |
| `type` | `number` (a whole number), `single` (one answer), `multi` (several or none), `text` (a short free answer) |
| `text` | the wording, in the study's language, or `{"pl": "...", "en": "..."}` |
| `options` | for `single` / `multi`: `[[code, label], ...]`; codes are lower-case, labels in the study's language (or `{"pl": ..., "en": ...}`) |
| `other` | for `multi`: the option code that opens a box to type in (kept as `met.<id>Other`) |
| `min`, `max` | for `number` |
| `required` | must be answered before *Dalej*; by default `number` and `single` are, `multi` and `text` are not |
| `placeholder` | the grey hint in a number or text box |

The six questions of the metryczka (`age`, `autism`, `adhd`, `gender`, `trans`, `diet`) need only `id` and `type`:
their wording and answers come from the task's texts (and the study's texts sheet). They also feed the usual
analysis columns (age, autism / ADHD and how identified, gender, transgender, diets). Leave any of them out and
those columns are empty; nobody is counted as "not autistic" because the question was not asked. Without
`"survey"` the metryczka asks exactly these six.

## Checking and editing the wording

- `python3 tools/texts.py check` (also run by the smoke test) checks every study's survey: ids, types, options, an
  `other` that is one of the options, `min` ≤ `max`.
- `python3 tools/texts.py export <study> sheet.xlsx` puts the wording of the study's own questions in the sheet
  (`survey.<id>.text`, `survey.<id>.options.<code>`); `import` writes the edited wording back into `"survey"`.

## In the data and the reports

- `pzf_data`: `met` holds the answers (`met.<id>`, `met.t` the time to each first answer, `met.ms` the time on the
  card); `survey` lists what was asked (`id`, `type`).
- `participants.csv`: the metryczka's questions in their usual columns; every other question as `q_<id>` (the answer;
  a `multi` question's codes space-separated), `q_<id>_<code>` (1/0 per answer of a `multi` question) and
  `q_<id>_text` (what was typed for "other").
- **Explore** compares groups by the study's own questions: a `single` question with 2-8 different answers becomes a
  grouping (`Survey: <id>`), a `number` question a covariate. It also groups by transgender and by a stated special
  diet. The overview leaves out the "strong feelings" section when the study did not ask it.

Changing the questions mid-study is possible (the data says what each person was asked), but compare like with like:
note the date of the change and the task version.
