# Changelog

What changed, newest first. The task stores its version with every pizza (`summary.v` in `pz_summary`), so data can be
matched to the format below. Add an entry for every change that reaches participants or the analysis.

## Unreleased

**Profiles: searching for types, honestly** (and synthetic people with real types)
- Clusters were judged by a fixed silhouette of 0.25. Tested on synthetic data: clustering on 2 components gave 0.37-0.40
  on data with no types, and a plain normal "no types" comparison let skewed measures pass as clustered at 500 people.
- Now four families of measures are searched (all; build behaviour; preferences; arrangement). Each is clustered and
  compared with 79 datasets that have no types but the same values of each measure and the same correlations (a
  Gaussian copula null); a family finds types only when none of them splits as well (p = .0125 = .05 / 4). The search
  stops early when a family cannot pass. Types found are described, with how neurodivergent and not neurodivergent
  people spread across them (permutation test). Larger samples are tested on a random 200.
- New on the Profiles page: **Build behaviour and preferences**, the best-supported correlations between how people
  build and what they choose (Spearman, BH over the pairs; total time left out, as it mostly counts the pieces).
- Synthetic people now have a latent eating style (selective / abundant / typical) that depends on their neurotype.
  With 100 of them, types are found in preferences and arrangement, and the arrangement types differ between
  neurodivergent and not (p ≈ .02); all the measures together show no types (the styles are mixed with other variation).

**Synthetic test data for the test study** (`analysis/synthetic.py`)
- A bar at the top of the researcher page (test study, and "all studies"): **Include [0 / 25 / 50 / 100 / 200 / 500]
  simulated pizzas → Generate and build**. Default 100 (study.json `"synthetic": 100`, only on `tests`). On Cloudflare
  the build adds or removes synthetic sessions to match; on the codespace server it happens at once.
- The synthetic people have **known, built-in group differences** (autistic: fewer and more familiar toppings, kept
  apart, in order, more sensory reasons; ADHD: quicker, more changes of mind, more unusual toppings), so the reports
  show what every comparison looks like and whether the analysis finds a difference that is really there. The same
  number always gives the same people (200 = the first 100 + 100 more).
- **Flagged everywhere**: ids SYN-…; a "synthetic" badge and a "real / synthetic only" filter on the Sessions tab;
  "+100 synthetic" on the study picker and the tiles, which count real sessions only (also last started and median
  time); a banner on every report ("Includes 100 synthetic pizzas … nothing here describes real people"); a
  `synthetic` column in participants.csv; synthetic and real counts in the Data check.
- 500 synthetic sessions take about 1.6 MB of the database.

**Analysis audit: no smoke and mirrors** (`docs/analysis-audit.md` lists every change and its reason)
- **One correction per family of questions.** The false discovery rate was corrected within each grouping while the
  page made about 3,400 comparisons. Now the study's groupings and the self-reports are corrected together (about 900
  tests); demographics (gender, age, link group, source) are a separate family; the ideas to test are their own.
  The thresholds quoted on the page ("pass the correction from n per group") are computed from its own number of tests.
- **Bootstrap intervals only for groups of 5 or more**; no sample sizes "at the effect seen" (winner's curse): leads
  plan for half the effect.
- **"Against chance" removed**: its chance layouts piled pieces up at random, so even spacing and some symmetry were
  "beyond chance" for everyone. The symmetry chance level now comes from random layouts spaced like the pizza itself.
- **Neurotype: each group against Not ND**, not against "everyone else"; yes/no groupings read "yes vs no".
- **"How normal" percentiles and bands only with 20+ reference pizzas**; the profiles use the continuous surprise.
- **Clusters only when they are real**: 20+ pizzas and a mean silhouette of 0.25+; otherwise "no clear clusters".
  Clusters × groups uses a permutation test. **"Compare two participants" is now "Compare two clusters"**: two
  clusters' average profiles side by side, ordered by how much they differ, with their group make-up and typical pizzas.
- **Pruned from the screen** (kept in the data): mouse movement, hovering as "considering", interface counters,
  adjustment-reason counts, nutrient totals other than the toppings' energy, secondary reveal measures, and measures
  that are parts of other measures. Explore now screens about 90 measures per grouping instead of about 180; the
  profiles have 30 features (no mouse movement).
- **New grouping `nd_any`** (any self-described neurodivergence) and **idea 9: neurodivergent people make more unusual
  pizzas** (unusualness = surprise of the topping set, rarity of the toppings), against autistic selectivity (idea 1).
- The example reports in `examples/` are rebuilt with the audited analysis.

**Explore, tidied up** (it highlighted odd things: device, gender and cheese differences from groups of 2-3)
- A status line at the top says what the data can do now: describe only (smaller group under 8), screen, or test (24+
  per group), for the study's best grouping.
- Order: Ideas to test, then Leads, then each of the study's groupings (neurotype, autistic, ADHD, diagnosis, eating,
  nutrition, study, condition). Demographic and recruitment groupings (gender, age, link group, source) are folded under
  "Other groupings"; the device grouping is gone (the task is desktop only). Correlations and clusters are folded.
- **Leads** come only from the study's groupings, need 5+ people in each group, leave out single toppings, base choices
  and low-level timings, and are ranked by evidence (p) rather than by the size of the difference. With too few people
  the page says there are no leads yet instead of listing noise. Each grouping's table is ranked the same way.
- A grouping is no longer compared on the measures that define it (people who revealed the nutrition do not "reveal
  it more often").
- **"Analysis updated"**: each deploy records the analysis code's fingerprint, and reports built with older code show
  as out of date ("The analysis was updated … press Build reports"), so a code change is not missed now that builds
  are on request.

**Explore: ideas to test.** The eight leads from `docs/sample-sizes.md` (fewer and more familiar toppings, foods
kept apart, order and symmetry, sensory reasons and safe foods, quicker choices and changes of mind, AuDHD's own
pattern, the effect of seeing the nutrition, own vs typical pizza) open the Explore page as **ideas**, not hypotheses
(nothing is preregistered; two have no expected direction). They are tested as one small family (false discovery rate
over these tests only). Each shows a verdict (strong lead / too few yet / no sign yet), whether the effect goes the
expected way, its number of tests (measures × comparisons) and the people per group a large effect needs with the
correction for those tests (alone, and as part of all the ideas), with a bar for how close the groups are. Also in
`explore.csv` (grouping = planned) and on the Methods page.
- **Methods → Sample sizes: how they are worked out**: every formula behind the sample sizes (two groups via Noether
  with Cliff's δ, correlations via Fisher's z, changes within a person via the sign test, the correction for several
  tests, unequal groups, the smallest possible p, what "large" means), with its assumptions and worked examples that the
  page build checks against the code, and a table of what each group size can detect. Explore shows the formula when you
  hover a sample size (ⓘ).

**Reports are built on request, to save compute**
- On Cloudflare the reports are built when a researcher presses **Build reports** (the button turns solid when there
  is new data). No build per finished session, no build after each deploy, no 5-minute waiting runner. Automatic builds
  stay available: repository variable `PIZZA_REPORTS_AUTO` = `1` (cloudflare/README.md).
- A build analyses only the studies whose sessions changed (before, the button rebuilt everything), skips studies with
  no pizza yet, and finishes in seconds when nothing changed. A change to the analysis code still rebuilds everything
  once; a full rebuild is *Actions → reports → Run workflow* with *force*.
- An include/exclude choice on the Sessions tab now counts as new data on Cloudflare too, so the page shows the reports
  as out of date until the next build (the Codespace server already did this).

**Sample sizes per analysis:** `docs/sample-sizes.md` lists every analysis from the fewest to the most participants it
needs, with the reason and the formula, what each participant contributes (333 measures per pizza, 517 variables), and
the most promising analyses for the study's groups.

**Sessions tab: choose which sessions are analysed**
- A new **Analysis** column shows each session's status: Included, Left out (not finished), or No pizza.
- A dropdown overrides it: **Auto** (the rule: analysed once they pressed "I'm done"), **Include** (e.g. keep a pizza
  someone nearly finished) or **Exclude** (e.g. a test run or a participant you know should not count).
- The choice is stored with the session (field `inclusion`, which a participant's save can never set), the reports
  rebuild (on Cloudflare: one queued build, so several choices in a row are one build), and the analysis applies it:
  excluded sessions go to `excluded.csv` with the reason "excluded by the researcher"; kept-in unfinished pizzas have
  `inclusion` = researcher in `participants.csv`. The Data check lists both.
- The Analysis column sits next to the participant id. It is one coloured dropdown that is also the indicator:
  green "Included" or amber "Excluded", marked "(auto)" when the automatic rule decided and "(your choice)" when
  overridden.
- The "Where" filter has "pizza in the analysis" and "pizza left out of the analysis". The session list download has
  `analysis` (included / left_out / no_pizza) and `inclusion` (auto / include / exclude); Links & data explains how the
  choices reach each download (R tables: analysed pizzas only, the rest in `excluded.csv`; raw sessions and database:
  every session).

**Only finished pizzas are analysed, with a data check** (the reports counted more pizzas than "built a pizza")
- **Why the numbers differed:** the task saves the pizza every few seconds while it is being built, so a participant
  who stopped part-way left a half-built pizza. The reports analysed it as if it were a choice, and also counted the
  "typical participant" pizza in the same total. "Built a pizza" counts only people who pressed "I'm done".
- **Now:** a build that never reached "I'm done" is left out of every report and download and listed in
  `excluded.csv`. The pizza count on the researcher page is the finished own pizzas, with the typical pizzas and the
  left-out builds named beside it, and a ✓ when it matches the sessions past the build (a warning when it does not).
- **Data check** at the top of the Overview: where every session is now, what was analysed and left out, and what to
  review before deciding on exclusions (very fast builds, empty pizzas, tab hidden, came back mid-study, mixed task
  versions, test sessions mixed with real ones). Also in `data_check.json`. New column `task_version`.

**Task 0.13.1: hold-to-resize is easier to find and to do** (participants got stuck on it in the practice and the build)
- **More forgiving:** the pointer may drift up to 20 px (`growStillPx`) while holding; before, 8 px of hand tremor
  restarted the hold. The pulse starts after 0.3 s (was 0.5 s) and is a little slower (3.6 s per cycle, was 3 s),
  so it is easier to let go at the size wanted. The movement measures (pauses, `stillPx` 8 px) are unchanged.
- **Visible feedback:** a ring appears round a held topping, and a "Let go when it is the size you want" tip follows
  the pointer while it grows and shrinks.
- **Clearer words:** the build instruction and the practice step say "press it and keep the mouse button down without
  moving"; clicking a topping on the pizza (instead of holding it) now shows a tip on how to resize.

**Reports rebuild by themselves, with progress on the page**
- **Triggered by the data, not a schedule.**
  - When a session finishes, the Cloudflare site queues one reports build on GitHub (needs `PIZZA_GITHUB_TOKEN`).
  - The build waits until nobody has saved for 5 minutes (at most 30), then builds.
  - Sessions finishing in the meantime join the queued build.
  - Cloudflare does nothing in between: one flag and one request per finished session.
  - "Rebuild reports" queues a full rebuild the same way.
- **Progress on the researcher page:** a spinner with the current step ("Analysing tests (3 of 9)"), elapsed time, a
  live log and a link to the GitHub run. Reports reload by themselves when the build is done. The page refreshes only
  while a build is queued or running, and not when its tab is hidden.
- **Status tile in the top bar:** green "✓ All analysed" when every session so far is in the reports; amber while
  new data waits or is being analysed. The last-started date is shortened (27 Oct 13:55).
- **Faster iteration.**
  - A push to `main` deploys at once, after a one-minute test of the Cloudflare part (`smoke_test.py --only
    cloudflare`); the full checks run alongside.
  - The reports job analyses studies side by side, and a study holding the same sessions as "all studies" reuses
    that analysis instead of repeating it.
- **Sessions: opened, built a pizza, finished, in progress, stopped.** An unfinished session with no save for 30
  minutes counts as stopped. This is worked out from the time of its last save, so nothing runs in the background,
  and it turns back to in progress if the person returns. The top bar shows all five counts. The Sessions list
  marks "stopped at …" with the last save, and **Where** can filter "in progress now" or "stopped".
- **Less computing, same numbers.**
  - Each pizza's symmetry chance level (and the random moves of the adjustment test) is seeded by the pizza itself,
    so a pizza's numbers no longer depend on which other pizzas are analysed with it. Before, the same pizza could
    differ slightly between "all studies" and its own study.
  - The slow per-pizza measures are cached between report builds.
  - The data dictionary and the Methods page are no longer rebuilt from scratch for every study (2.7× faster for 8
    pizzas; identical output).
  - Participant pages save every 4 seconds instead of every second (a quarter of the requests and writes).
  - CI skips documentation-only pushes, runs R and the Cloudflare tests in one job, and uses current action versions.
- **Fixed:** the reports job could be refused partway through many studies, because the per-connection limit counted
  its uploads. The limit now applies to wrong keys only, and the job retries if refused.

**The researcher page, rebuilt; clearer reports**
- **One page for both servers** (`server/admin.html`, data from `/admin/api/state` and `/admin/api/sessions`).
  - **Study chooser first:** a card per study, and "All studies together".
  - **Then one view per study:** counts at the top, with tabs for Overview (the dashboard), Sessions (filter, sort,
    pages), Explore, Profiles, Symmetry, Methods, and Links & data (participant and personal links, researcher links,
    downloads, storage).
- **Researcher link for all studies.** It sees every study but manages no links. It sits next to each study's own link
  under Links & data, and can be replaced like them. Use it instead of the owner password in links.
- **Reports.**
  - **Dot plots:** one colour; median and interquartile range written out for groups of 5 or more; smaller groups drawn
    but not summarised; axis units.
  - **Stacked bars:** counts instead of percentages under 10.
  - **Strong feelings:** shares of everyone who answered, one row per ingredient, group counts beside it.
  - **Explore:**
    - typical values labelled as medians, with times in seconds;
    - δ size words (Romano 2006);
    - p &lt; 0.001 shown as such;
    - each grouping states how many comparisons pass the false discovery rate, and those rows are marked ✓;
    - leads warn about groups under 5 and selection.
  - **New Nutrition section** in the overview: energy of every pizza, who looked (while building or only at the end),
    changes of mind, and which way pizzas changed after the first sight.
  - **Contents bar** at the top of the overview.

  The Methods page documents the new summaries.

- Study `tests` (the team's test runs; nutrition button on). *Actions → move sessions* moves sessions between
  studies in the Cloudflare database (`deploy.py move`). Everything collected before was moved to `tests`.

## 0.13.0 (2026-10-27) – task: seeing the nutrition on request; participant-only view

Task data changes, so pizzas now record `summary.v` 0.13.0. The task jumps from 0.10.1 to 0.13.0 because 0.11 and
0.12 were server versions.
- **New study setting `nutrition_reveal`** (`nutritionReveal` in Qualtrics; also per condition):
  - while building, a *Show nutrition information* button under the pizza;
  - the table is shown below the pizza, with kcal per slice of a pizza cut into 8;
  - at *I'm done*, a dialog with the pizza's nutrition offers *Bake it for me* or *I changed my mind* (back to
    building).

  The build and the dialog fit 1366×768 and 1280×720 without scrolling.
- **Logged.**
  - New events: `nshow` and `nmodal` (each with the pieces, kcal, sauce and cheese shown), `nhide`, `changemind`,
    `bake`.
  - `add` events now carry the piece's drawn size, so the pizza at any moment can be rebuilt exactly.
  - New `summary.reveal`.
- **Analysis.**
  - New columns: `nutrition_reveal`, `nutri_*`, `n_changed_mind`, `post_nutri_*` (changes after the nutrition was first
    seen: pieces, energy and nutrients, diet classes, direction, pace and removals before and after),
    `rebuilt_after_done`, `post_done_*`.
  - All on the Methods page, with a worked example. explore.html gets measures and the grouping "revealed the
    nutrition".
  - The simulator gives every other participant the setting.
- **The participant sees only the task.** The "Part i of n" counter is gone from the participant page. The demo is
  participant-first: the steps, the settings and the captured-data preview sit behind a small *Researcher view*
  switch, remembered per browser.
- **Fix:** a dialog's dark backdrop now covers the whole window.

## 0.12.1 (2026-10-27) – Cloudflare: hard caps, simpler setup

- **Hard caps so Cloudflare never bills.** R2 is the only product that bills by use, so the Worker caps it below the
  free tier:
  - 8 GB stored, 800,000 writes and 8 million reads a month;
  - the database at 450 MB: new participants are then turned away, and people already in can finish.

  Settings can lower the caps, never raise them. The caps fail closed. The reports job checks for room before it
  uploads anything. Database copies are stored compressed. The owner's page shows usage against each cap.
- **Setup: one token and two GitHub secrets** (`CLOUDFLARE_API_TOKEN`, `PIZZA_ADMIN_KEY`). The deploy itself:
  - finds the account;
  - registers a workers.dev address if there is none;
  - creates the Turnstile bot check for the site's address.

  The workflow first lists what the token can reach, with a FAIL line naming any missing permission.

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
