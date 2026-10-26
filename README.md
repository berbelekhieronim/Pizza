# Pizza Builder

[![check](https://github.com/berbelekhieronim/pizza/actions/workflows/check.yml/badge.svg)](https://github.com/berbelekhieronim/pizza/actions/workflows/check.yml)

A drag-and-drop virtual pizza task for food-choice research, run in Qualtrics (e.g. with Prolific) or from its own
small study server. No food is eaten.
Participants practise briefly, make a pizza by dragging toppings onto it, say which ingredients they have strong
feelings about, and tell us a little about themselves. Everything they do is recorded: which toppings, how many, where,
in what order, how long each decision took, and how each drag moved.

It is built for **exploratory** work: finding how pizzas differ across many kinds of people (autistic, ADHD, AuDHD,
otherwise neurodivergent or not, formally diagnosed or self-identified, picky eaters, people with eating difficulties...)
rather than testing one fixed contrast. Many measures are recorded per pizza, people can be grouped in several ways at
once, and `explore.html` screens every measure across every grouping, ranked by effect size with false-discovery-rate
control, so leads can be followed up in a new sample.

**Desktop and laptop computers only** (mouse or trackpad): phones and tablets see a "please use a computer" notice
instead of the task, and no data are recorded for them. In Prolific, also set the study's device compatibility to
*Desktop*. No libraries, no image hosting:
the toppings are drawn in SVG by the script itself.

| file | what |
|---|---|
| `pizza-builder.js` | the task (all three pages) |
| `index.html` | demo of the whole flow with the recorded data shown live |
| `analysis/methods.py` | the **Methods** page: every measure and test written out as a formula, with worked examples computed by the code (also on the researcher page) |
| `qualtrics/*.js` | paste-in code, one per survey page |
| `analysis/analyse.py` | scores a Qualtrics export: variety, avoidance, symmetry/clustering, order, timing, norm deviation |
| `CODEBOOK.md` | every recorded field and every computed measure |
| `preview.js` | the demo's readable preview of one participant's captured data, with symmetry, border and face pictures |
| `server/` | a small study server for running participants without Qualtrics, e.g. from a GitHub Codespace (below) |
| `examples/` | the reports built from simulated data, and the script that simulates it |
| `tests/smoke_test.py` | checks everything end to end; GitHub runs it on every push |

## Documentation

| document | for |
|---|---|
| this README | what the task does, running it (Qualtrics or the study server), pilots, the analysis |
| `CODEBOOK.md` | every recorded field and output table |
| **Methods page** (`methods.html`, researcher page → *Methods*) | how every number and test is computed, with worked examples checked against the code |
| `variables.csv` + `load_pizza.R` (written with the analysis) | the data dictionary and loader for R |
| `CHANGELOG.md` | what changed in each version (the version is stored with every pizza) |
| `HANDOFF.md` | current state, design decisions, open questions and next steps, for whoever continues the work |
| GitHub Actions → a run's *Summary* | every automatic check of that commit, the face benchmark, and the log and example reports as downloads |

## Quick start: a link to send to participants

1. **[Open this repository in a Codespace](https://codespaces.new/berbelekhieronim/pizza?quickstart=1)**
   (or on GitHub: **Code → Codespaces → Create codespace on main**). It takes a minute the first time.
2. The study server starts by itself, and the terminal shows two links: the **participant link** to send, and your
   **researcher page** (with its password in the link; keep that one to yourself).
3. On the researcher page, **Links to send** has a ready link for each group (e.g. `?group=ASD`, `?group=NT`) with a Copy
   button. The link stays the same every time you open this codespace, and works whenever the server is on.

Details, settings and limits are under [Running participants without Qualtrics](#running-participants-without-qualtrics-github-codespace).

## Requirements

Nothing to install. The task is plain JavaScript with no libraries; the analysis, the study server and the tests use only
the Python standard library (Python 3.10 or newer). A Codespace comes with everything. To run it on your own computer:

```
python3 server/server.py              # the study server: open the participant link it prints
python3 analysis/analyse.py data.json # the analysis
python3 tests/smoke_test.py           # check that everything works on this machine
```

## The procedure

1. **Practice** (`practice.js`, ~40 s). Five guided steps with a practice-only tomato slice: drop one into a target
   circle, add two more, move one, change one's size, drag one off. This teaches the controls before the real choice and
   records each person's **motor baseline** (drag speed, targeting error) on their own device.
2. **Build** (`build.js`). Choose sauce (none / tomato / white / BBQ) and cheese (none / light / normal / extra), then drag
   toppings onto the pizza, one piece at a time. The default tray has 20 toppings in three a-priori tiers of conventionality:
   - *common*: pepperoni, ham, chicken, tuna, mushrooms, green pepper, red onion, black olives, sweetcorn, jalapeños, basil
   - *mid*: anchovies, pineapple, shrimp, egg, blue cheese
   - *unusual*: nori, kimchi, kangaroo (exotic meat), fig (sweet-savoury fruit). Pear, banana and walnuts are also drawn;
     add them with `ingredients`

   Shrimp, egg, blue cheese, the meats and anchovies spoil quickly, so they also vary in perceived food safety.
   The tray order is shuffled for each participant and recorded.
   Holding a topping still for half a second, while dragging it or by pressing one already on the pizza, makes its size
   pulse smoothly between half and 2.5 times normal (one full cycle every 3 s) for as long as it is held; letting go
   keeps the size of that moment. Every piece's size is recorded.
   Pieces can be moved, dragged off to remove, undone, or cleared. "I'm done" asks for confirmation, then the pizza
   "bakes" (a short visual) and the survey moves on by itself. Each part's own button ("Continue", "I'm done", "Finish")
   is the only button needed: there is no separate Next step (in Qualtrics the scripts press Next for the participant).
3. **Optional perceived-norm build** (`build-typical.js`): the same task, "make the pizza a typical participant would choose".
4. **Follow-up** (`followup.js`). By default it is short:
   - **One list:** all the ingredients as tiles, with *Do you have strong feelings about any of these ingredients?*
     Participants tap every one they do (or *None of these*).
   - **For each ingredient tapped, five questions** chosen for ASD, ADHD and AuDHD food experiences:
     1. *How do you feel about it?* love / like / mixed / dislike / can't stand
     2. *What is it about it?* texture, smell, taste, how it looks, it touching other food, something else (sensory aspects)
     3. *Is it a "safe food" for you, one you can nearly always eat?* yes / sometimes / no
     4. *Does it have to be a certain way for you to eat it (a brand, how it is cut or cooked)?* yes / sometimes / no (sameness)
     5. *Do you crave it or go looking for it?* often / sometimes / never

     Reword them with `text: { feel: {...} }`, or drop some with `feelQuestions`.
   - **About you** (last, so it cannot prime the pizza; `askAbout: false` to leave it out if your survey asks these):
     self-described neurotype (autistic, ADHD, dyslexic/dyspraxic/dyscalculic, otherwise neurodivergent, none), and for
     autism and ADHD whether it was formally diagnosed, self-identified or awaiting assessment; eating history (picky since
     childhood, ARFID, an eating disorder, allergy or intolerance); diet; two 1-7 self-ratings (*I am a picky eater*,
     *Food textures, smells or looks often bother me*); age band and gender. Every question has *Prefer not to say*.
     The analysis derives a `neurotype` grouping from it (AuDHD / Autistic / ADHD / Other ND / Not ND).

   Two more parts can be switched on (`askPizza: true`, `askDiet: true`), and `style: 'ratings'` replaces the list with
   the detailed version: every ingredient rated on scales, plus reasons for each one left off. In that version, in
   this order, so the diet and health questions cannot prime the ratings:
   - **About your pizza**: six 1-7 agreement items: *My pizza expresses who I am* · *...is different from the pizza most
     people would make* · *I made my pizza exactly the way I wanted to* · *...I felt in control of the result* ·
     *I followed a rule or system when arranging the toppings* · *I chose toppings I was confident would be safe for me to eat*.
     Override the wording with `pizzaItems`.
   - **One card per topping** (random order, with its picture), 1-7: liking (or "never tasted"), familiarity,
     perceived safety, disgust, and how appropriate *most people* would think it is as a topping.
     For toppings they used, also *To what extent does it reflect who you are?*
     For toppings they left off, *why not* (taste, diet, religious/cultural, allergy, health, safety, disgust,
     unfamiliar, "doesn't belong on pizza", "doesn't go with my other toppings", no particular reason, other + text).
   - **About how you eat**: diets (vegetarian, vegan, pescatarian, no pork/beef, halal, kosher, gluten-/dairy-free, other);
     food allergy, intolerance, digestive problems, past bad experiences with food, avoiding foods for texture/smell/look
     (+ which foods); how often they eat pizza.

## Guiding questions and the measures behind them

The study is exploratory: the hypotheses below steer which measures exist, but the analysis does not assume any of
them. `explore.html` looks at everything; this table says where to look first for each question.

| question | measured by (column names from `analysis/analyse.py`) |
|---|---|
| **H1a** distinctive / unusual choices | a priori: `n_distinct_unusual`, `prop_unusual_distinct`, `prop_unusual_pieces`. In this sample: `ingredient_rarity` (how few others chose the same toppings), `combo_rarity` (how rarely others combined the same pairs, which catches unusual combinations of familiar toppings), `profile_uniqueness` (1 − mean Jaccard similarity to everyone else). Perceived: `norm_mean_included` (low = toppings the person thinks others find inappropriate), `counter_normative`, `pz_distinct` |
| **H1b** systematic organisation | symmetry: `mirror_match` / `mirror_score`, `rot_match` / `rot_score` + `rot_k`. Even spacing: `clark_evans`, `nn_cv`, `angular_regularity`. Repeated pattern: `sector_similarity`, `slice_spread`, `sector_cv`. Rule-like order: `blockiness`, `sweep_consistency`. Size matching: `size_match_same`, `size_match_index`. Figurative: `face_detected`, `face_score`. Staying inside the sauce vs using the crust: `border_share`. Self-report: `pz_system`. Fine-tuning: `n_ev_move`. Overall: the clusters in `profiles.html` |
| restricted choice / avoidance | `n_pieces`, `n_distinct`, `shannon`, `simpson`, categories, `n_never_picked`, `n_picked_not_kept`, reasons (`why_*`) |
| **H2a** identity expression | `ident_mean`, `ident_mean_unusual`, per-topping `ident`, `pz_express`, `pz_distinct`; plus your identity-salience manipulation as `condition` |
| **H2b** agency and control | `pz_auton`, `pz_control`; plus your control manipulation as `condition` |
| hesitation and deliberation while placing | movement of each drag: `mv_straight` (how direct), `mv_pauses` / `mv_paused_share` (stopping mid-drag), `mv_dwell` (lingering before letting go), `mv_hold` (holding before moving), `mv_crossings` (going back and forth over the pizza edge); `decision_median`; `t_after_done`, `n_done_presses`; `n_ev_undo`, `n_ev_move` |
| who the participant is (for grouping) | `neurotype`, `nd_autistic`, `nd_adhd`, `nd_identified` (formal or not), `eat_*`, `self_picky`, `self_sensory_food`, `age_band`, `gender`; the study link's `group`; `condition` |
| **H2c** dietary vigilance | `health_*`, `diet`, `diet_conflict`; `n_perishable_included`, `safe_mean_included`, per-topping `safe` and `perishable`; `decision_median` and per-topping `decision_ms_mean` against the practice motor baseline; `pz_safety`; `why_safety`, `why_allergy`, `why_health` |

Combining these into a single systematicity or distinctiveness index is a decision to make once the exploratory data
have shown which measures hang together (see the correlation map in `explore.html`), and to preregister for a confirmatory sample. Several
are ratios or proportions, so standardise them within the sample first.

### Manipulations and covariates (built natively in Qualtrics)

- **Identity activation** (after Palomares, 2008) and the **control induction** go on pages before the practice.
  Assign the conditions with a Survey Flow *Randomizer* that sets the embedded field `condition` (e.g. `autistic-id`,
  `student-id`, `low-control`, `high-control`). The build page stores it with every pizza (`condition`), so the analysis needs no merging.
  The practice sits between the manipulation and the build, so keep it short, as it is now, to limit decay.
- **Covariates**: food neophobia (Food Neophobia Scale, Pliner & Hobden, 1992), disgust sensitivity (e.g. DS-R), and
  any trait measures (e.g. AQ, ASRS). Place them **after** the follow-up so they cannot prime the pizza. Give the analysis
  their score columns with `--covariates fns_total,dsr_total` and `explore.html` correlates every measure with each;
  give categorical columns (e.g. a clinician-confirmed diagnosis) with `--group` to compare by them too.
- **Sensory and predictability.** The task has no time limit or countdown, no sound, and every action can be undone.
  It also follows the device's *reduce motion* setting, which switches off the pulsing target and the baking transition.

## Setting it up in Qualtrics

**1. Survey Flow → add an Embedded Data element at the very top** with these fields, values left empty:

```
PROLIFIC_PID  STUDY_ID  SESSION_ID  condition
pzp_final pzp_events pzp_summary pzp_counts pzp_error
pz_final  pz_events  pz_summary  pz_counts  pz_error
pzf_data  pzf_error
```

Using the `pzt_` "typical" build as well? Add `pzt_final pzt_events pzt_summary pzt_counts pzt_error`.
If your survey uses the **Simple layout** (Look & Feel → Layout), add every pizza field a second time with `__js_` in
front (`__js_pz_final`, ...). Qualtrics only saves values the script writes in that layout under those names. The scripts write both versions, and
the analysis reads whichever is filled, so declaring both does no harm.

**2. One page per step.** In a block, add a *Text / Graphic* question, put a page break after it, and repeat for each step:
practice, build, (typical build), follow-up. Write the instructions in the question text or leave it empty; the widget
shows its own short prompt. For each question: click it → *JavaScript* (the `</>` icon) → replace everything with the matching file
from `qualtrics/`.

**3. Survey options:** turn off the Back button. Set the Prolific completion redirect as usual. Collect
`PROLIFIC_PID` from the URL as usual (`?PROLIFIC_PID={{%PROLIFIC_PID%}}`).

**4. Preview on a computer**, then export a test response (Data & Analysis → Export → CSV) and run the
analysis on it. Check that `pz_events` arrives complete. A long build is ~5-15 KB of text, well within what
embedded data holds, but confirm this with your own pilot data.

## Running participants without Qualtrics (GitHub Codespace)

For a pilot with a few participants you can skip Qualtrics: `server/server.py` serves the whole study (intro and consent,
practice, build, ratings, completion code) and saves each participant as they go.

1. Open a codespace on this repository (see Quick start). The server starts by itself whenever the codespace starts, and
   the terminal prints the **participant link** and the **researcher page** link. Print them again any time with
   `python3 server/server.py --links`. The server's own output is in `server/data/server.log`.
2. The server tries to make port 8000 public so participants can open the link. If the log says it is still private:
   open the **Ports** tab, right-click port 8000 → **Port Visibility → Public**.
3. Send participants a link from **Links to send** on the researcher page. A link can carry `?group=ASD` (or `NT`, etc.)
   to record the group you recruited them through (participants also describe themselves on the "About you" card, and
   the reports use both), and `&pid=...` to use your own IDs; Prolific's `PROLIFIC_PID` is picked up too. Conditions
   listed in `server/study.json` are assigned in turn.
4. Watch sessions arrive on the researcher page (it shows what each person said they are). The **Dashboard**, **Explore patterns**, **Profiles and clusters** and **Symmetry and contact**
   buttons open the reports (and **Methods** shows how each number is counted), rebuilt automatically from everyone so far whenever new sessions have arrived (**Rebuild now**
   forces it). **Download all data** gives a zip of every session. Keep the researcher link to yourself: the password is
   part of it, which is what lets the page work even inside the codespace's preview panel.

Edit `server/study.json` for the title, intro text, consent sentence, completion message or a redirect URL (e.g. a
Prolific completion link), the conditions, the groups that get a ready-made link, whether to add the "typical
participant" build (`typical_build`), and whether to ask the "About you" questions (`about_you`, on by default).

Things to know:
- **The link works only while the server is on.** A codespace stops after about 30 minutes without activity in its editor
  (raise this to 4 hours in your GitHub settings under Codespaces → Default idle timeout), and then participants get a
  GitHub error page. Keep the codespace's tab open while participants take part. Opening it again restarts the server
  with the same links and all data so far.
- The participant link belongs to this codespace. A *new* codespace gets a new address (and starts with no data), so
  keep using the same one for a study.
- Data lives in `server/data/` inside the codespace, never in the repository (it is git-ignored). Download it from the
  researcher page when you are done: unused codespaces are deleted after a period set by GitHub.
- The researcher password is made on first start and kept in `server/data/.admin_key`; set `PIZZA_ADMIN_KEY` to choose your own.
- Your organisation may not allow public ports; then use Qualtrics, or ask for that setting to be changed.

### Running a pilot with a specific group (study-specific, filterable data)

For a pilot with, say, autistic adults recruited through community organisations, keep its data apart from everything
else and labelled with where each person came from:

1. **Define the study** in `server/study.json` under `"studies"` (an example, `pilot-asd`, is there). A study can have
   its own `intro`, `consent`, `completion_message` / `completion_redirect`, `groups`, `conditions` and `about_you`;
   anything not given comes from the main settings. Ids are lower-case letters, digits and dashes.
2. **Make personal links** on the researcher page (*Studies and links* → *Make personal links*): choose the study,
   a group (e.g. ASD) and the recruitment source (e.g. "autism charity newsletter"), and how many. Download them with
   *Invite links (.csv)* and send one link per person. A personal link (`/?i=…`) is that person's id: it records
   study, group and source, opening it again resumes their session (on any computer), and the spreadsheet shows who
   has not opened, started or finished. Unknown or mistyped links are refused, so no unlabelled data comes in.
3. **Or post an open link** (`/?study=pilot-asd&group=ASD`, listed per study) where personal links are impractical,
   e.g. a forum. Add `&source=forum` to record where it was posted.
4. **Filter by study**: the chips at the top of the researcher page show one study's sessions; its reports, the
   *Download for R* zip and the raw sessions then hold that study only. *All studies* puts everything together, and
   the analysis then compares studies (`study`) and recruitment sources (`source`) like any other grouping.

What a pilot gives for the larger study (in `explore.html`):
- **Against chance** – with one group only, each systematic measure (mirror and rotational symmetry, same-topping
  neighbours, placing in blocks, size matching, sweeping round, even spread) is tested against its chance level,
  for everyone and for each self-described neurotype (autistic, AuDHD, ADHD … within the pilot).
- **Within-group differences** – formally diagnosed vs self-identified, with or without ADHD, eating difficulties,
  the 1-7 self-ratings and any questionnaire scores (`--covariates`).
- **Leads for a larger study** – the largest differences, one per measure, each with the number of people per group a
  confirmatory study would need for 80% power, at the effect seen and at half of it (plan with the second: effects
  found by screening many measures in a small sample are usually overestimated).
- To compare the pilot with a non-autistic sample, run a second study (e.g. `general`, recruited the same way, or
  via Prolific) on the same server and look at *All studies*.

### Where the script comes from

The paste-in files load `pizza-builder.js` from this repository through jsDelivr, pinned to a specific commit
(`@<commit>` in `SRC`), so the task cannot change under a running study.

The files are currently pinned to commit `87d8f68`. To try the task on its own, open `index.html` in a browser (it works
offline), or run the study server. To change the task: edit
`pizza-builder.js`, push, and put the new commit hash in `SRC`. The repository must stay public for jsDelivr to serve it.
If you would rather not depend on a CDN, paste the whole of `pizza-builder.js` above the paste-in code in each question; the
loader then skips the download.

### Options

Set in the `PizzaBuilder.mount(box, { ... })` call:

| option | default | |
|---|---|---|
| `prompt` | built-in text | instruction shown above the pizza; `''` hides it |
| `condition` | `''` | any label, stored with the data (e.g. piped from the Survey Flow) |
| `ingredients` | the 20 above | which toppings to offer, by code (see CODEBOOK). Use the same list in the build and the follow-up |
| `shuffle` | `true` | randomise the tray order per participant |
| `sauce`, `cheese` | `'tomato'`, `'normal'` | starting base. These defaults can act as a status-quo anchor, so keep them the same across conditions |
| `baseChoices` | `true` | show the sauce/cheese choices |
| `minSeconds`, `minPieces` | `0` | earliest point "I'm done" unlocks |
| `showCounts` | `false` | count badges on the tray (off by default: numbers invite counting) |
| `confirm`, `bake` | `true` | confirmation dialog, bake animation |
| `grow`, `growDelay`, `growMin`, `growMax`, `growPeriod` | `true`, `500`, `0.5`, `2.5`, `3000` | hold to resize: on/off, ms of stillness before the pulse starts, smallest and largest size, ms per full pulse |
| `desktopOnly` | `true` | phones and tablets get a notice instead of the task (`pzX_blocked = not-desktop` is saved); `false` lets them in, untested |
| `names`, `text` | | rename toppings or translate any wording, e.g. `text: { done: 'Gotowe' }` |
| `prefix` | `pz_` / `pzp_` / `pzf_` | embedded-data field prefix; use a new one for each extra build |
| follow-up only: `askPizza`, `askIdentity`, `askReasons`, `askDiet`, `pizzaItems`, `scales` | all on | turn parts of the follow-up on or off, or reword them |

## Analysis

```
python3 analysis/analyse.py my_export.csv --out results
python3 analysis/analyse.py my_export.csv --group dx_confirmed,site --covariates fns_total,dsr_total --out results
```

This needs Python 3.10 or newer and nothing else. People are grouped by every way the data allow: the "About you" answers,
the study link's group, the condition, the device, and any `--group` columns. The first `--group` column (default: the
self-described neurotype, else the study link's group, else the condition) is the one the dashboard, symmetry and profile
reports compare. `--reference <files>` sets the pizzas that define "normal" (default: the
rest of the sample) and `--clusters <k>` fixes the number of clusters. It writes:

| file | what |
|---|---|
| `participants.csv` | one row per pizza: every measure below |
| `ingredients_long.csv` | participant × topping, ready for mixed models |
| `events_long.csv` | every interaction, for sequence analyses |
| `pieces_long.csv` | one row per piece: position, size, order, zone, contacts, symmetry partner |
| `removals_long.csv` | one row per piece taken off the pizza: topping, how, when, time on the pizza (changes of mind) |
| `variables.csv`, `load_pizza.R` | data dictionary and R loader (below) |
| `profiles.csv` | each participant's standardised profile and cluster |
| **`dashboard.html`** | the data at a glance, for proposals and for checking data as it comes in: diet breakdown, stated diet against the pizza, the normality distribution with the most unusual pizzas, space / size / time by group, a sortable table of every participant with a thumbnail |
| **`explore.html`** | for discovering patterns: every measure, and every topping (used / named with strong feelings), compared between the groups of every grouping, largest effects first with the data drawn, Cliff's δ with bootstrap intervals, p and false-discovery-rate q; each measure's correlation with each self-rating and covariate; how all the measures correlate with each other; and the profile clusters against every grouping. `explore.csv` holds every comparison |
| **`profiles.html`** | every participant as a profile of 32 measures; compare any two side by side (with each person's most similar participants); hierarchical clusters with plain-language descriptions, how the groups spread across them (χ²), a map of all profiles, and a heatmap ordered by the clustering tree |
| **`arrangement.html`** | symmetry and contact drawn on every pizza: the best mirror axis, the best rotation (rings mark where each topping's symmetric partner would have to be: green = a matching topping is there, red = none nearby), and touching and stacked pieces, with group comparisons |
| `pizzas/`, `gallery.html` | every pizza redrawn from its coordinates |
| **`methods.html`** | how every column and test is counted: one formula per measure with the function that computes it (and its line number), and worked examples computed by that code and checked against the hand calculation. The researcher page has it under **Methods** |

### Analysing in R

Every table is R-ready: UTF-8, `NA` for missing values, `1`/`0` for yes/no, and `variables.csv` describes every column
(type, factor levels, unit, description). The analysis folder (and the researcher page's **Download for R** zip) also
holds `load_pizza.R`, which needs no packages:

```r
source("load_pizza.R")
pz <- load_pizza("results")          # list of data frames with the right types, factor levels and column labels
people <- pizza_wide(pz)             # one row per participant: own pizza (+ typical pizza) + profile scores
pizza_describe("mirror_score", pz)   # what a column means
```

Factors have a sensible reference level (e.g. `neurotype` "Not ND") and ordered factors are ordered (`age_band`,
`diet_class`, `normality_band`, `cheese`, `feel`, ...). `pieces_long` has one row per piece, for spatial models;
`ingredients_long` one row per participant × topping, for mixed models (e.g. `lme4::glmer(included ~ neurotype * tier +
(1 | pid) + (1 | ing), family = binomial)`).

The measures are defined in `CODEBOOK.md`. In short:

- **Variety and distinctiveness:** number of pieces and distinct toppings, Shannon diversity and evenness, Simpson index, categories,
  unusual-tier toppings, and how rare the person's toppings and topping pairs are in the sample.
- **Avoidance:** toppings never picked up; picked up but not kept (rejected or removed); latency to first pick;
  stated reasons; whether a stated diet rules a topping out.
- **Symmetry and clustering:** centroid offset, radial spread, circular uniformity, evenness over 8 slices
  ("does every slice get some"), Clark-Evans nearest-neighbour ratio with edge correction, same-topping segregation,
  coverage, spacing regularity, the same mix repeating across slices.
- **Symmetry** counts pieces: a piece is matched when its mirror image (best axis, searched to 0.25°, through the pizza's
  centre or the toppings' centroid) lands on a piece of the same topping. `mirror_match` is the share matched,
  `mirror_chance` the share the same pieces get at random positions, and `mirror_score` = (match − chance) / (1 − chance)
  (0 = chance, 1 = every piece matched). The same for the best 2- to 8-fold rotation. This replaced a distance ratio
  that searched axes only every 10°, so a perfectly mirrored pizza scored poorly unless its axis was a multiple of 10°;
  the Methods page shows both on worked examples.
- **Contact and stacking:** each piece's outline is modelled at its real length, width, rotation and size. The measures:
  - pairs of pieces that touch, and pairs where one lies substantially on top of the other
  - the share of pieces in contact
  - the tallest pile
  - whether piles are made of the same topping or of different ones
  - the median edge-to-edge gap in mm
- **Size and amount:** pieces enlarged and shrunk, mean / smallest / largest size, and total topping area in cm², which is the truer quantity once pieces can change size.
- **Size matching:** for every resized piece, is another piece of the same topping (or the same category) the same size, within 10%?
  The rate for pieces of other categories is the chance baseline, so `size_match_index` > 0 means sizes are matched on purpose.
- **Border:** pieces inside the sauce, on the crust, or hanging over the outer edge (and by how many mm). Toppings stay where
  they are dropped, including on the crust; only drops beyond the edge remove them.
- **Faces:** whether the toppings form a face, at any rotation. Touching pieces are first merged into features, so an eye
  can be one piece, a piece with a pupil on it, or a small heap; the eyes can be two different toppings. A mouth is one
  long piece or an evenly spaced row or smile of 3+ pieces (of any toppings) under the eyes. A nose, eyebrows and cheeks
  count as part of the face, and the face must be a main feature of the pizza (at least 30% of the pieces near it and of all
  pieces). `python3 tests/face_benchmark.py` draws hundreds of faces of 11 kinds and 11 kinds of non-face: it finds 81% of
  faces (51% with two different eye toppings, 70% with eyebrows or hair, 83-93% for the rest) and flags 1.5% of non-faces
  (worst: 6% of random scatters of 9-20 pieces, 5% of mirror-symmetric pizzas). The demo preview runs the same detector,
  and the smoke test checks that both give identical answers. Have a person code faces on a subset of your own pizzas to
  check agreement before relying on it.
- **Diet class:** each pizza is classed vegan / vegetarian / pescatarian / contains meat by the strictest diet it fits
  (cheese and white sauce count as dairy), with piece counts and area shares per class, and checked against the stated diet.
- **Normality:** each pizza against a reference distribution of pizzas: `--reference` files (e.g. a pilot or a norming
  sample), or by default every other pizza in the sample. It is scored two ways, each as a percentile of the reference:
  - *which toppings*: how surprising the set is, in bits, given each topping's inclusion rate
  - *how many*: how extreme the number of different toppings is, in either direction

  The band (typical < 75th, uncommon 75-95th, unusual > 95th) uses the more extreme of the two, and the report names
  the choices that contribute most.
- **Order:** first topping, blockiness (grouping by topping vs alternating), a steady sweep round the pizza, meat before vegetables.
- **Timing:** decision time (end of one action to picking up the next, excluding the drag itself), gaps between
  placements, drag time, time away from the tab, and **time to completion**: when "I'm done" was first pressed, when the
  pizza was confirmed and submitted, and how often the participant pressed it but went back to edit.
- **Movement:** for every drag, its path, how direct it was, pauses on the way, the dwell before letting go, the hold
  before moving and crossings of the pizza edge, summarised per person (`mv_*`). Drag measures depend on the device and
  motor skill as well as on deliberation, so compare them against the practice baseline and the device (`pointer`).
- **Exploring patterns (`explore.html`):** every measure is compared between groups with Cliff's δ (−1 to 1; for yes/no
  measures the difference in proportions), which needs no assumptions about distributions and reads the same for every
  measure. With two groups the first is compared with the second; with more, each group with all the others.
  p is from a Mann-Whitney test (a permutation test when a group has fewer than 8 people) and q is the
  Benjamini-Hochberg false discovery rate across all the comparisons for that grouping. Groups smaller than 3 are left
  out and listed. With hundreds of comparisons some large-looking differences are chance: treat the page as a source
  of leads to confirm, and report how many comparisons were looked at.
- **Changes of mind and other actions:** the log is replayed piece by piece, so every piece that was added and later
  taken back is known: which topping, how (dragged off, undone, or wiped by *Start over*), when, and how long it was on
  the pizza (`removals_long.csv`). Per pizza: pieces added and removed, `revision_rate`, toppings added then left off
  (`dropped_list`), restored pieces, start overs (and *Start over* opened then declined), pieces moved and how far,
  edits after the first *I'm done*, sauce or cheese changed after toppings were placed, and toppings the mouse rested
  on (≥ 0.5 s) but never picked (`considered_list`), plus tray toppings dropped off the pizza (`rejected_list`).
  Per topping in `ingredients_long`: added, removed, dropped, moved, resized, considered.
- **Profiles and clusters:** 32 measures across composition, normality, space, size, order, time, faces, strong feelings, movement and changes of mind, each
  standardised in the sample and signed so that higher means more of the named trait. Participants are compared by the
  distance between their profiles and grouped by Ward clustering, with the number of clusters chosen by silhouette.
- **Norm deviation:**
  - against the *perceived* norm: own inclusions vs "most people would find it appropriate" ratings
    (correlation; counter-normative inclusions; normative avoidances; a 0-1 deviation score);
  - against the *actual* sample: leave-one-out inclusion rates and mean counts;
  - against the participant's own "typical person" pizza, if that build was used.

## Interpreting choices and timing

- **Dietary restrictions.** Avoidance driven by a constraint is not preference. `ingredients_long.csv` flags
  `diet_conflict` (for example, ham for someone who keeps halal, or blue cheese for someone who is dairy-free) and records the stated reasons. Analyse avoidance with and without
  these toppings. The diet questions come *after* the build so they do not prime the choice.
- **Cultural context.** Topping norms vary by country, for example pineapple, sweetcorn or anchovies. Prolific exports
  country of residence, nationality and similar demographics per `PROLIFIC_PID`; join them in and model country,
  or screen on it when recruiting. `pizza_freq` and the familiarity ratings help separate unfamiliarity from dislike.
- **Device and motor demands.** The study runs on computers only, but a mouse and a trackpad still differ in speed and
  precision. Every pizza records `pointer`, `coarse`, `layout`, the pizza's size in px and the
  viewport. The practice gives a per-person motor baseline (`practice_drag_median`, `practice_target_err`). Compare
  timing within device type, or include these as covariates. Use `decision_median`, which excludes drag time, rather than
  raw totals. Positions are stored relative to the pizza, so they compare directly across screen sizes. Pieces are
  the same size relative to the pizza on every screen.
- **Faces and borders.** Treat `face_detected` as a screening flag and confirm it by human coding; treat crust use as
  meaningful only when the pizza was big enough on screen (`pizzaPx`) for the crust to be easy to avoid.
- **Tray position.** The tray order is random per participant, and `tray_pos` is recorded so position effects can be estimated.
- **Attention.** `hiddenMs` and `flag_tab_away` mark time spent on another tab. `flag_fast` marks builds finished in
  under 15 s. Decide on exclusion rules before collecting data.

No device fingerprint or user-agent string is stored. The identifiers are whatever your survey collects.
