# The post-pizza survey of a study

After the pizza, a study can ask its own short questions instead of the standard follow-up (strong feelings about
ingredients, About you). Pizza Pilot 11.2026 does this: its *metryczka*. The questions are set per study in
`server/study.json`, so each version of the study can ask different ones without touching the code.

## Setting it up

On the researcher page's **Settings** tab (for every study, or for one study; per condition in a between-subjects
study), or in the study's settings in `server/study.json` (`"studies": {"<id>": {...}}`):

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
| `explore` | optional: what you expect the answer to relate to, which Explore turns into an *idea to test* (below) |

The six questions of the metryczka (`age`, `autism`, `adhd`, `gender`, `trans`, `diet`) need only `id` and `type`:
their wording and answers come from the task's texts (and the study's texts sheet). They also feed the usual
analysis columns (age, autism / ADHD and how identified, gender, transgender, diets). Leave any of them out and
those columns are empty; nobody is counted as "not autistic" because the question was not asked. Without
`"survey"` the metryczka asks exactly these six.

## Before or after the pizza

`"survey_when": "before"` asks the questions right after the consent, before the practice and the pizza (Pizza
Pilot 11.2026 from task 0.17.0; the default for every study from task 0.18.0); `"after"` asks them after the pizza. The
standard follow-up (strong feelings about the toppings) asks about the pizza, so it always comes after it. The card's wording follows (*Najpierw kilka pytań o
Ciebie* and *Dalej* before, *Na koniec…* and *Zakończ* after; texts `task.metSubBefore`, `task.metNext`). What it
changes:

- the session's stages: `survey` (the questions before the pizza) comes between the consent and the practice;
  `followup` stays the questions after it. A save never moves a session back to an earlier stage.
- the data: `pzf_data.when` is `before` or `after`; `participants.csv` has `survey_when`. Earlier data is `after`.
- the Data check: people who answered and then left before building are listed (their answers are kept with the
  session but not analysed, which starts from a pizza); a mix of before and after in the same data is a point to review.
- people who were past the consent when the setting changed and had not answered yet are asked after the pizza
  instead (with the after wording), so nobody misses the questions; whoever was at the questions after the pizza
  comes back to them.

Answers given before building can prime the pizza (for example, being asked about diet or autism first), and the
pizza can prime answers given after it. Keep one order within an analysis, or compare the two (`survey_when`).

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

### Explore adapts to the questions

Explore's *Ideas to test* follow what the study asked (task 0.18.2):
- The built-in ideas (from the literature on eating in autism and ADHD, and for the short card: a stated vegetarian /
  vegan diet, formal vs self-identified autism / ADHD, age, gender) run only when the study recorded what they compare
  and measure. The others are listed as *not asked in this study*, with what they would need, and are left out of the
  correction, so the ideas that can run are not penalised by those that cannot.
- Each of the study's own questions can carry an `explore` note, and becomes its own idea:

```json
{"id": "sleep", "type": "single", "text": "Jak spałeś/spałaś?", "options": [["well", "dobrze"], ["badly", "źle"]],
 "explore": {"title": "Tired people choose less", "why": "Fatigue narrows choices.",
             "measures": ["n_distinct", "nut_kcal"], "direction": "lower", "answer": "badly"}}
```

  `measures`: up to 8 columns of `participants.csv` (Methods lists them); `direction`: `higher`, `lower` or `either`;
  `answer`: for one answer or several answers, the answer compared with the rest (by default the largest group); a
  number question is correlated. The note is saved with each person's answers (`pzf_data.survey`), so the analysis
  needs nothing else. Without a note, a question still appears in Explore's screen (one answer: a grouping; a number:
  a covariate).

The ideas are chosen by fixed rules, not by an AI model: the same data always give the same tests, which a study's
analysis needs. A model could help draft `explore` notes from a question's wording, for the researcher to check.

Changing the questions mid-study is possible (the data says what each person was asked), but compare like with like:
note the date of the change and the task version.
