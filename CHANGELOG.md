# Changelog

What changed, newest first. The task stores its version with every pizza (`summary.v` in `pz_summary`), so data can be
matched to the format below. Add an entry for every change that reaches participants or the analysis.

## 0.12.0 (2026-10-27) – Cloudflare hosting

**The study on Cloudflare, deployed from GitHub, at one address.** The task and its data are unchanged (pizzas still
record `summary.v` 0.10.1).
- **`cloudflare/`**: one Worker serves the participant page, saving, resuming and the researcher page.
  - Data goes to D1 (the schema of `server/store.py`), reports and downloads to R2 (EU jurisdiction).
  - `server/study.json` is bundled in.
  - `deploy.py` creates the database and storage the first time, then deploys.
- **GitHub workflows.**
  - `cloudflare.yml` deploys after every push to `main` whose checks pass. It does nothing until the Cloudflare
    secrets are added.
  - `reports.yml` runs `tools/cloud_sync.py`, which downloads the sessions, runs `analyse.py` for all studies and per
    study, and stores the reports, R, raw and database downloads on the site. It runs when sessions finish, on
    "Rebuild now", after deploys, and every 6 hours, and skips when nothing changed.
- **Bot and abuse protection** (Cloudflare):
  - Turnstile check before a new session (personal links and returning participants skip it);
  - rate limits per connection and per session;
  - `robots.txt` and `noindex` (also on the Codespace server);
  - no request logging.
- **Tests.** The smoke test runs the Worker in the local Workers runtime (wrangler dev with local D1 and R2):
  - every participant and researcher route;
  - access per study;
  - the reports job;
  - the bot check;
  - rate limits;
  - that the D1 schema matches `store.py`.

  CI installs wrangler for it.

## 0.11.0 (2026-10-27) – study server

**A database, a session browser, and a researcher link per study.** The task and its data are unchanged (pizzas still
record `summary.v` 0.10.1); only the study server changed.
- **SQLite database** `server/data/study.db` (standard library `sqlite3`, WAL mode): sessions, their saved fields,
  personal links, researcher links, condition counters. Schema in CODEBOOK.md. Sessions, invites and counters saved as
  files by earlier servers are imported on the first start (the files are kept).
- **Session browser.** The researcher page filters by study, group, source, condition, where people are, what they say
  they are, start dates and id; sorts by any column; pages through 100 at a time. Reports and every export follow the
  filter: *Download for R*, *Session list (.csv)* (new), *Raw sessions (.zip)*, *Database (.sqlite)* (new; a
  consistent copy, or one study's).
- **Per-study researcher links.** Each study has its own key, which opens the researcher page limited to that study
  (sessions, reports, exports, personal links). The owner's key sees everything and can replace a study's link.
  Keys are masked in the server log, and pages send `Referrer-Policy: no-referrer`.
- **`analyse.py` reads the database** (`analyse.py study.db --study pilot-asd`).

## 0.10.1 (2026-10-27)

**The participant flow, reviewed and tightened.** Each step was measured in a browser at 1366×768 and 1280×720.
- **Coming back mid-study** (reload, closed tab, personal link reopened): no second consent. The participant returns
  to the part they were on, the follow-up keeps the build's counts, a "welcome back" note shows, and `restarts` is
  recorded (new column).
- **Every step fits the window.**
  - The pizza takes the height left below its top edge.
  - The page margins are smaller.
  - Practice, build, strong-feelings list and ingredient cards need no scrolling at 1366×768 (they needed 50–750 px
    before).
- **Compact follow-up on computers.** Answer options are rows of chips on a wider card, and About you has two columns,
  cutting its scrolling from 1,650 px to 190 px.
- **Mouse wording.** "Click" instead of "tap" and "press"; clearer practice steps for moving and resizing.
- **Researcher page.**
  - Open links sit in tidy rows with a Copy button beside each.
  - Sessions are newest first, with where each person is and the time taken.

## 0.10.0 (2026-10-26)

**Nutrition panel, nutrients of every pizza, why pieces were moved**
- **Nutrition panel.** A study setting, off by default: `nutrition_panel` in study.json, or per condition through
  `condition_settings`; `nutrition: true` in Qualtrics; a switch in the demo. It shows live energy, macros, sugars,
  saturates, fibre, salt, vitamins and minerals for the whole pizza, against reference intakes.
  - Data: USDA SR28, public domain, via `tools/build_nutrition.py` → `analysis/nutrition.json`, which the task embeds.
    Stand-ins: kangaroo → venison, pizza crust → Italian bread, red onion → onion, nori → laver.
  - Size rule: grams = standard piece grams × (drawn size)², so a tomato slice at double size weighs 4×.
  - Every pizza stores whether the panel was shown (`summary.nutrition`).
- **Nutrients of every pizza** (shown or not): `nut_*` for the whole pizza with its base, `top_kcal`, `top_grams`,
  `top_kcal_share`, `nutrition_panel`. Per topping: `grams`, `kcal`. explore.html screens them and groups by panel
  shown or not.
- **Adjustments.** Every move or in-place resize of a placed piece is replayed (undos included) and classed by what it
  did:
  - symmetry: more pieces with a partner at the finished pizza's best axis or rotation, compared with 12 random moves
    of the same length;
  - otherwise grouping, spreading, spacing, unstacking, inward or outward moves, nudges, or size matching.

  New table `adjustments_long.csv`; per pizza `n_adj_*`, `adj_symmetry_excess` (a profile measure: 33 in all) and
  `adj_reasons`.
- **Faster explore.** The permutation null distributions are shared between tests (same results); 40 pizzas went from
  36 s to ~10 s.

## 0.9.0 (2026-10-26)

**Pilot studies, changes of mind, data for R**
- **Pilot studies.** `server/study.json` → `"studies"`: per-study intro, consent, completion text, groups and
  conditions (example: `pilot-asd`). Personal invite links (`/?i=…`) per study, group and recruitment source, made on
  the researcher page and downloaded as a spreadsheet with opened / finished status. An invite is the participant's id,
  so reopening it resumes the session, and unknown links are refused. Open study links (`/?study=…&group=…&source=…`).
  The researcher page, reports, R download and raw download can be filtered by study. `study` and `source` are columns
  and groupings in the analysis.
- **Changes of mind.** The log now records which pieces *Start over* removed (`clear` + ids), the topping of each
  *Undo*, and a declined *Start over* (`clearno`). The analysis replays the log piece by piece:
  - new table `removals_long.csv`;
  - per-pizza columns `n_removed_*`, `removed_list`, `revision_rate`, `dropped_list`, `n_restored`, start overs,
    moves, edits after *I'm done*, sauce/cheese changes after toppings, toppings hovered but never picked
    (`considered_list`) and `rejected_list`;
  - per-topping columns `added_pieces`, `removed_pieces`, `dropped`, `moves`, `resizes`, `considered_not_picked`;
  - `replay_matches_final` checks that the replay ends with the finished pizza.

  `revision_rate` joins the profiles (32 measures).
- **explore.html.** *Leads for a larger study* lists the largest differences, with the n per group needed for 80% power
  at the observed effect and at half of it. *Against chance* tests one group against the chance level of each systematic
  measure. Per-topping "changed mind" and "considered" rows.
- **R.** All tables use `NA` and 1/0. New `pieces_long.csv`, `variables.csv` (data dictionary) and `load_pizza.R`
  (base R: types, factor levels, labels; `pizza_wide()`). The researcher page has *Download for R*. CI checks the loader
  in R.
- **CI.** Every check is listed on the run's summary page with the face benchmark. The log and the reports built from
  simulated data are kept as run artifacts.

## 0.8.0

**Methods page, count-based symmetry, desktop only, new toppings**
- **Methods page** (`analysis/methods.py`, researcher page → *Methods*). Every output column and test has a formula and
  names its function and line. Worked examples are computed by the code and checked against the hand calculation. The
  smoke test fails on any undocumented column.
- **Symmetry redefined.**
  - Old: `sym_*`, a distance ratio searched every 10°, which scored a perfectly mirrored pizza 0.37 when its axis was at 45°.
  - New: `mirror_match` / `mirror_chance` / `mirror_score` and `rot_*` count the pieces whose mirror or rotated image
    lands on a piece of the same topping. The best axis is searched to 0.25°, and the count is compared against random
    layouts. `pieces_long` marks each piece's partner.
- **Desktop and laptop only.** Phones and tablets get a notice and no data is recorded (`desktopOnly`). The tray has
  4 columns on computers.
- **Toppings.** Added tuna (common), kangaroo (exotic meat) and fig (sweet-savoury). Pear left the default tray, which
  now has 20 toppings.

## 0.7.0

**Exploratory study**
- An "About you" card ends the follow-up. It asks:
  - self-described neurotype, and for autism and ADHD whether it is formally diagnosed, self-identified or awaiting
    assessment;
  - eating history and diet;
  - two 1-7 self-ratings, age band and gender.

  From these the analysis derives `neurotype` (AuDHD / Autistic / ADHD / Other ND / Not ND).
- **Movement of every drag** (event field 10): path, straightness, pauses, dwell, hold, edge crossings. Columns `mv_*`.
- **explore.html.** Every measure is compared across every grouping (Cliff's δ, bootstrap CI, Mann-Whitney or
  permutation p, BH q), with correlations with the self-ratings and `--covariates`, a correlation map, and clusters ×
  groups. `--group` takes several columns.

## 0.6.0

**Face detection**
- Touching pieces merge into features. Eyes can have pupils, be heaps, or be two different toppings. Mouths can be
  rows of mixed toppings. Eyebrows and cheeks count as part of the face.
- `tests/face_benchmark.py` finds 81% of faces and flags 1.5% of non-faces (was 61% / 1.2%). `preview.js` runs the same
  detector, checked by the smoke test.

## 0.5.0

**Strong-feelings follow-up; researcher page fixes**
- The default follow-up is one list ("strong feelings about any of these?"), then five ASD/ADHD/AuDHD-relevant
  questions per ingredient tapped: feeling, sensory reasons, safe food, sameness, craving. The old ratings remain as
  `style: 'ratings'`.
- One button per step: the task's own button moves the survey on.
- The researcher page works inside the codespace preview: the key is in every link, and reports rebuild on demand.

## 0.4.0

**Study server and stand-alone repository**
- `server/server.py`: participant page, saving as people go, a researcher page with reports and a zip download, and a
  one-click Codespace with fixed links.
- Profiles and clusters (Ward, silhouette, PCA), face and crust/border analysis, size matching, time to completion.

## 0.3.0

**Hold-to-resize pulse; diet classes, normality, dashboard**
- Holding a piece makes its size pulse between 0.5× and 2.5×.
- Diet class of each pizza, normality against a reference distribution, the data dashboard and the demo's captured-data
  preview.

## 0.2.0

**Symmetry and contact**
- No-sauce option.
- Contact and stacking of pieces; symmetry drawn on every pizza.

## 0.1.0

**First version**
- Practice → build → follow-up for Qualtrics (embedded data). Records ingredients, quantities, positions, order and
  timings.
- Analysis of variety, avoidance, symmetry/clustering and norms.
