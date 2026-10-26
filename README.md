# Pizza Builder

A drag-and-drop virtual pizza task for Qualtrics studies run through Prolific. No food is eaten.
Participants practise briefly, then make a pizza by dragging toppings onto it, then rate each topping.
Everything they do is recorded: which toppings, how many, where, in what order, and how long each decision took.

Works the same with mouse, touch and pen, on phones and desktops. No libraries, no image hosting:
the toppings are drawn in SVG by the script itself.

| file | what |
|---|---|
| `pizza-builder.js` | the task (all three pages) |
| `index.html` | demo of the whole flow with the recorded data shown live - open it on a phone and a laptop |
| `qualtrics/*.js` | paste-in code, one per survey page |
| `analysis/analyse.py` | scores a Qualtrics export: variety, avoidance, symmetry/clustering, order, timing, norm deviation |
| `CODEBOOK.md` | every recorded field and every computed measure |

## The procedure

1. **Practice** (`practice.js`, ~40 s). Five guided steps with a practice-only tomato slice: drop one into a target
   circle, add two more, move one, make one bigger, drag one off. This teaches the controls before the real choice and
   records each person's **motor baseline** (drag speed, targeting error) on their own device.
2. **Build** (`build.js`). Choose sauce (none / tomato / white / BBQ) and cheese (none / light / normal / extra), then drag
   toppings onto the pizza, one piece at a time. The default tray has 18 toppings in three a-priori tiers of conventionality:
   - *common*: pepperoni, ham, chicken, mushrooms, green pepper, red onion, black olives, sweetcorn, jalapeños, basil
   - *mid*: anchovies, pineapple, shrimp, egg, blue cheese
   - *unusual*: nori, kimchi, pear (banana and walnuts are also drawn; add them with `ingredients`)

   Shrimp, egg, blue cheese, the meats and anchovies spoil quickly, so they also vary in perceived food safety.
   The tray order is shuffled for each participant and recorded.
   Holding a topping still for half a second, while dragging it or by pressing one already on the pizza, makes it grow
   steadily, up to 2.5 times its size; letting go keeps that size. Every piece's size is recorded.
   Pieces can be moved, dragged off to remove, undone, or cleared. "I'm done" asks for confirmation, then the pizza
   "bakes" (a short visual) and the Next button appears.
3. **Optional perceived-norm build** (`build-typical.js`): the same task, "make the pizza a typical participant would choose".
4. **Follow-up** (`followup.js`), in this order, so the diet and health questions cannot prime the ratings:
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

## How the measures map onto the study's questions

| question | measured by (column names from `analysis/analyse.py`) |
|---|---|
| **H1a** distinctive / unusual choices | a priori: `n_distinct_unusual`, `prop_unusual_distinct`, `prop_unusual_pieces`. In this sample: `ingredient_rarity` (how few others chose the same toppings), `combo_rarity` (how rarely others combined the same pairs, which catches unusual combinations of familiar toppings), `profile_uniqueness` (1 − mean Jaccard similarity to everyone else). Perceived: `norm_mean_included` (low = toppings the person thinks others find inappropriate), `counter_normative`, `pz_distinct` |
| **H1b** systematic organisation | symmetry: `sym_mirror`, `sym_rot180`, `sym_rot_best` + `sym_rot_k`. Even spacing: `clark_evans`, `nn_cv`, `angular_regularity`. Repeated pattern: `sector_similarity`, `slice_spread`, `sector_cv`. Rule-like order: `blockiness`, `sweep_consistency`. Self-report: `pz_system`. Fine-tuning: `n_ev_move` |
| restricted choice / avoidance | `n_pieces`, `n_distinct`, `shannon`, `simpson`, categories, `n_never_picked`, `n_picked_not_kept`, reasons (`why_*`) |
| **H2a** identity expression | `ident_mean`, `ident_mean_unusual`, per-topping `ident`, `pz_express`, `pz_distinct`; plus your identity-salience manipulation as `condition` |
| **H2b** agency and control | `pz_auton`, `pz_control`; plus your control manipulation as `condition` |
| **H2c** dietary vigilance | `health_*`, `diet`, `diet_conflict`; `n_perishable_included`, `safe_mean_included`, per-topping `safe` and `perishable`; `decision_median` and per-topping `decision_ms_mean` against the practice motor baseline; `pz_safety`; `why_safety`, `why_allergy`, `why_health` |

Combining these into a single systematicity or distinctiveness index is a decision to preregister. Several
are ratios or proportions, so standardise them within the sample first.

### Manipulations and covariates (built natively in Qualtrics)

- **Identity activation** (after Palomares, 2008) and the **control induction** go on pages before the practice.
  Assign the conditions with a Survey Flow *Randomizer* that sets the embedded field `condition` (e.g. `autistic-id`,
  `student-id`, `low-control`, `high-control`). The build page stores it with every pizza (`condition`), so the analysis needs no merging.
  The practice sits between the manipulation and the build, so keep it short, as it is now, to limit decay.
- **Covariates**: food neophobia (Food Neophobia Scale, Pliner & Hobden, 1992), disgust sensitivity (e.g. DS-R), and
  your autism measure / diagnosis status. Place them **after** the follow-up so they cannot prime the pizza. Merge them
  with the output by `PROLIFIC_PID` (the analysis keeps that as `pid`).
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

**4. Preview on a phone and a computer**, then export a test response (Data & Analysis → Export → CSV) and run the
analysis on it. Check that `pz_events` arrives complete. A long build is ~5-15 KB of text, well within what
embedded data holds, but confirm this with your own pilot data.

### Where the script comes from

The paste-in files load `pizza-builder.js` from this repository through jsDelivr, pinned to a specific commit
(`@<commit>` in `SRC`), so the task cannot change under a running study.

The files are currently pinned to commit `16660f5`. The demo at that commit is
<https://raw.githack.com/berbelekhieronim/eye-tracking-library/16660f574708687c4a35d72511a025a8be51a25b/pizza-builder/index.html>, which you can open on any phone. To change the task: edit
`pizza-builder.js`, push, and put the new commit hash in `SRC`. The repository must stay public for jsDelivr to serve it.
If you would rather not depend on a CDN, paste the whole of `pizza-builder.js` above the paste-in code in each question; the
loader then skips the download.

### Options

Set in the `PizzaBuilder.mount(box, { ... })` call:

| option | default | |
|---|---|---|
| `prompt` | built-in text | instruction shown above the pizza; `''` hides it |
| `condition` | `''` | any label, stored with the data (e.g. piped from the Survey Flow) |
| `ingredients` | the 18 above | which toppings to offer, by code (see CODEBOOK). Use the same list in the build and the follow-up |
| `shuffle` | `true` | randomise the tray order per participant |
| `sauce`, `cheese` | `'tomato'`, `'normal'` | starting base. These defaults can act as a status-quo anchor, so keep them the same across conditions |
| `baseChoices` | `true` | show the sauce/cheese choices |
| `minSeconds`, `minPieces` | `0` | earliest point "I'm done" unlocks |
| `showCounts` | `false` | count badges on the tray (off by default: numbers invite counting) |
| `confirm`, `bake` | `true` | confirmation dialog, bake animation |
| `autoScroll` | `true` | on phones, scroll once so the pizza and the whole tray are on screen together |
| `grow`, `growDelay`, `growRate`, `growMax` | `true`, `500`, `0.8`, `2.5` | hold to grow: on/off, ms of stillness before growing starts, size added per second, largest size |
| `touchLift` | `44` | on touch screens the dragged topping floats this many px above the finger so it stays visible |
| `names`, `text` | | rename toppings or translate any wording, e.g. `text: { done: 'Gotowe' }` |
| `prefix` | `pz_` / `pzp_` / `pzf_` | embedded-data field prefix; use a new one for each extra build |
| follow-up only: `askPizza`, `askIdentity`, `askReasons`, `askDiet`, `pizzaItems`, `scales` | all on | turn parts of the follow-up on or off, or reword them |

## Analysis

```
python3 analysis/analyse.py my_export.csv --out results
```

This needs Python 3.10 or newer and nothing else. Add `--group <column>` (e.g. your ASD / NT column) to compare groups
in the arrangement report. It writes `participants.csv` (one row per pizza),
`ingredients_long.csv` (participant × topping, ready for mixed models), `events_long.csv`, and every pizza
redrawn as SVG plus a `gallery.html` contact sheet, and **`arrangement.html`**. That is the visual analysis of
symmetry and contact: every pizza drawn three times, with its best mirror axis, its best rotational symmetry
(rings mark where each topping's symmetric partner would have to be: green = a matching topping is there,
red = none nearby), and its touching and stacked pieces. Sample-wide dot plots compare the groups at the top. The measures are defined in `CODEBOOK.md`. In short:

- **Variety and distinctiveness:** number of pieces and distinct toppings, Shannon diversity and evenness, Simpson index, categories,
  unusual-tier toppings, and how rare the person's toppings and topping pairs are in the sample.
- **Avoidance:** toppings never picked up; picked up but not kept (rejected or removed); latency to first pick;
  stated reasons; whether a stated diet rules a topping out.
- **Symmetry and clustering:** centroid offset, radial spread, circular uniformity, evenness over 8 slices
  ("does every slice get some"), Clark-Evans nearest-neighbour ratio with edge correction, same-topping segregation,
  coverage, spacing regularity, the same mix repeating across slices. Mirror, 180° and the best k-fold rotational symmetry are each
  expressed as a ratio to random layouts of the same toppings (< 1 = more symmetric than chance).
- **Contact and stacking:** each piece's outline is modelled at its real length, width, rotation and size. The measures:
  - pairs of pieces that touch, and pairs where one lies substantially on top of the other
  - the share of pieces in contact
  - the tallest pile
  - whether piles are made of the same topping or of different ones
  - the median edge-to-edge gap in mm
- **Size and amount:** pieces enlarged, mean and largest size, and total topping area in cm², which is the truer quantity once pieces can grow.
- **Order:** first topping, blockiness (grouping by topping vs alternating), a steady sweep round the pizza, meat before vegetables.
- **Timing:** decision time (end of one action to picking up the next, excluding the drag itself), gaps between
  placements, drag time, time to finish, time away from the tab.
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
- **Device and motor demands.** Touch dragging on a small screen is slower and less precise than a mouse, and hover
  is only measurable with a mouse. Every pizza records `pointer`, `coarse`, `layout`, the pizza's size in px and the
  viewport. The practice gives a per-person motor baseline (`practice_drag_median`, `practice_target_err`). Compare
  timing within device type, or include these as covariates. Use `decision_median`, which excludes drag time, rather than
  raw totals. Positions are stored relative to the pizza, so they compare directly across screen sizes. Pieces are
  the same size relative to the pizza on every screen.
- **Tray position.** The tray order is random per participant, and `tray_pos` is recorded so position effects can be estimated.
- **Attention.** `hiddenMs` and `flag_tab_away` mark time spent on another tab. `flag_fast` marks builds finished in
  under 15 s. Decide on exclusion rules before collecting data.

No device fingerprint or user-agent string is stored. The identifiers are whatever your survey collects.
