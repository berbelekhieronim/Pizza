# Handoff

The state of the project for whoever works on it next (a person or a new Claude session). Read this, `CLAUDE.md`
(rules for changing the code) and the top of `CHANGELOG.md` first. **Update this file at the end of every working
session**: the snapshot, anything decided, and the open items.

## Snapshot (2026-10-27, task version 0.13.1, server 0.12.1)

- **Repository:** github.com/berbelekhieronim/Pizza, branch `main`. All smoke-test checks pass locally and in CI.
- **Purpose:** an exploratory study of food choice in autistic, ADHD and AuDHD adults (and comparison groups). People
  build a virtual pizza on a computer; everything they do is recorded and analysed to find patterns that can become
  hypotheses for a larger, confirmatory study.
- **Next milestone:** a pilot with an authentic autistic group, run from the study server as study `pilot-asd` with
  personal invite links (README → *Running a pilot with a specific group*).
- **Where it runs:**
  - **Qualtrics:** `qualtrics/*.js` load `pizza-builder.js` from jsDelivr, pinned to commit `c3982cc` (0.13.1). Re-pin after every
    change to the task.
  - **Study server:** `server/server.py` in a GitHub Codespace (`.devcontainer` starts it). Data is in the SQLite
    database `server/data/study.db` (`server/store.py`). The owner's researcher page is `/admin?key=…` (key in
    `server/data/.admin_key`); each study has its own researcher link, limited to that study.
  - **Cloudflare** (`cloudflare/`, set up by the user per `cloudflare/README.md`): one Worker at
    `https://pizza-study.<subdomain>.workers.dev` with D1 (data) and R2 (reports, downloads). It is deployed by
    `.github/workflows/cloudflare.yml` once the repository has the Cloudflare secrets, and its reports are built by
    `reports.yml` → `tools/cloud_sync.py`. Not deployed yet as of this snapshot: waiting for the user's account,
    token and secrets.
  - **Demo:** `index.html` in the repo. A copy is published as the user's private Claude artifact "Pizza Builder demo";
    republish it after changing `pizza-builder.js` or `preview.js`.

## How the pieces fit

```
participant ──> pizza-builder.js (practice, build, follow-up + About you; desktop only)
                 │  fields pz_*, pzp_*, pzf_* (JSON strings: final pieces, event log, summary, follow-up)
                 ├─> Qualtrics embedded data ──> CSV export ─┐
                 └─> server/server.py ──> server/store.py ──> server/data/study.db (sessions + fields; study, group, source, invite)
                                                             │
analysis/analyse.py  <───────────────────────────────────────┘
   ├─ measures per pizza / topping / piece / removal / event  ──> *.csv (NA, 1/0) + variables.csv + load_pizza.R (R)
   ├─ reports: dashboard, explore (groupings, chance, leads), profiles (clusters), arrangement (symmetry, contact)
   └─ methods.py ──> methods.html (formula of every column + worked examples, checked against the code)
preview.js: the demo's live summary; re-implements face detection, symmetry and the change-of-mind replay
            (the smoke test checks them against analyse.py)
```

## File map

| path | what |
|---|---|
| `pizza-builder.js` | the task. Toppings (`ING`, `TIER`, `DEFAULT_INGREDIENTS`), `Builder` (practice/build), `Followup` (strong feelings, ratings, About you), desktop gate, logging |
| `analysis/analyse.py` | all measures and reports. Entry point `analyse()`; one function per measure family (see the Methods page for which) |
| `analysis/methods.py` | the Methods page: `SECTIONS` (one entry per column) and the worked examples |
| `analysis/nutrition.json`, `tools/build_nutrition.py` | nutrients per 100 g (USDA SR28) and grams per piece; the script rebuilds the JSON from SR28's ABBREV.txt and copies it into `pizza-builder.js` |
| `analysis/r_export.py`, `analysis/load_pizza.R` | data dictionary and R loader |
| `server/server.py`, `server/participate.html`, `server/study.json` | study server (routes, researcher page, exports, access scopes), participant page, study settings (incl. `"studies"`) |
| `cloudflare/src/worker.js`, `store.js`, `admin.js`, `config.js` | the Cloudflare Worker: the same routes as `server/server.py` on D1/R2, plus Turnstile and rate limits |
| `cloudflare/deploy.py`, `cloudflare/wrangler.json`, `cloudflare/migrations/` | deploy (creates D1/R2 the first time), Worker config, D1 schema (= `store.SCHEMA`) |
| `tools/cloud_sync.py` | the reports job for Cloudflare: download sessions → analyse per study → upload to R2 via the Worker |
| `server/admin.html` | the researcher page (study chooser, one view per study with tabs), served by both servers |
| `server/store.py` | the SQLite store: schema, saving, filters/sorting, personal and researcher links, per-study copies, import of the old JSON files |
| `preview.js`, `index.html` | demo page and its captured-data preview |
| `qualtrics/*.js` | paste-in code per survey page (practice, build, build-typical, follow-up) |
| `examples/` | simulator and the reports built from simulated data |
| `tests/smoke_test.py` | end-to-end checks (analysis, server, R, JS, face benchmark). `tests/face_benchmark.py` measures face detection |
| `README.md`, `CODEBOOK.md`, `CHANGELOG.md`, `HANDOFF.md`, `CLAUDE.md` | docs for users, data, history, state, contributors |

## Common tasks

```
python3 tests/smoke_test.py                                       # everything; must pass before pushing
python3 examples/simulate.py /tmp/sim 5 60 AB                     # fake participants
python3 analysis/analyse.py /tmp/sim/*.json --out /tmp/out        # all tables, reports, methods page, R files
python3 analysis/methods.py /tmp/methods.html                     # just the Methods page
python3 server/server.py --port 8000 --data /tmp/data --key test  # local study server: /admin?key=test
python3 analysis/analyse.py /tmp/data/study.db --study pilot-asd --out /tmp/out   # analyse the server's database
python3 tests/face_benchmark.py --n 300                           # face detection accuracy
```

After changing `pizza-builder.js`: commit, re-pin `qualtrics/*.js` to that SHA (`sed` the 40-character SHA), commit,
push, check the GitHub Actions run, and republish the demo artifact.

## Decisions and why

- **Exploratory framing.** Many measures and groupings are screened. Effects are given as Cliff's δ with BH false
  discovery rates. Leads come with n per group at half the observed effect, because pilot effects are inflated.
  Hypotheses H1a–H2c guide which measures exist but are not tested as such.
- **Desktop only** (user's decision). Mobile and touch layouts are frozen: do not work on them. The touch code is still
  there, but untested from 0.8.0 on.
- **Symmetry counts pieces.** The share of pieces with a same-topping partner is compared against chance. This replaced
  a distance ratio that gave misleading numbers (user noticed "symmetric pizzas don't feel symmetric number-wise").
- **Default follow-up = strong feelings.** The user wanted a short, clickable list, with at most five questions
  relevant to ASD, ADHD and AuDHD per ingredient tapped.
- **A personal invite link is the participant id.** Reopening resumes the session, the links spreadsheet shows status,
  and no separate login is needed. Unknown study or invite links are refused, so no unlabelled data comes in.
- **Nutrition from USDA SR28, frozen in the repository.** The study must not depend on a live API. SR28 (2015) is
  public domain and complete for these foods. The USDA hosts were blocked from the build environment, so the table was
  taken from SR28's ABBREV.txt as redistributed in the npm package `fda-nutrient-database` 1.0.2. Weight follows the
  area of a piece (size²); piece weights are estimates, listed in README.
- **Adjustments are judged against the finished pizza's own symmetry.** That is the arrangement the person was working
  towards, and judging every move against one fixed axis makes moves comparable and cheap to test against chance
  (12 random moves of the same length).
- **R-ready output.** Tables use `NA` and 1/0, and `variables.csv` gives every column's type and levels. Descriptions
  come from the Methods page, so there is one source of truth.
- **SQLite is the server's source of truth** (user's decision, for larger data). One file, no database server, safe
  with concurrent saves (WAL, `BEGIN IMMEDIATE`), readable from R. `sessions` keeps a few summary columns for sorting
  and filtering; `fields` keeps everything the task saved, unchanged. Old JSON files are imported once, never written.
- **Access by key, per study.** The owner key sees all; a study key is forced to its study in every route (filters,
  reports, exports, invites) and cannot reach owner-only routes (researcher-link reset). Keys stay in the URL so the
  page works inside the Codespace preview; logs mask them and pages send no referrer.
- **Cloudflare hosting (user's request: "fully workable from Cloudflare and GitHub, one www").** One Worker at one
  address. D1 because it is SQLite: the same schema and downloads as the Codespace server. The analysis is too heavy
  for a Worker (minutes of CPU), so GitHub Actions builds the reports per study and stores them in R2 through
  owner-only Worker routes (`/admin/export`, `/admin/files/...`). Reports therefore follow study scopes, not every
  filter. The Worker starts the job when sessions finish (`PIZZA_GITHUB_TOKEN`, at most every 10 minutes).
- **Bot protection** (user's request): Turnstile on new sessions (not on personal links or resumes), rate limits
  (`ratelimits` in wrangler.json), no indexing. The Python server has no Turnstile; it is for pilots in a Codespace.
- **Hard caps (user: "never get billed").** R2 is capped in the Worker below the free tier (8 GB, 800k writes and
  8M reads a month; `limits()` in worker.js, clamped so settings can only lower them). D1 at 450 MB turns new
  participants away. Workers and D1 must stay on the free plans, which stop at their limits rather than bill.
- **Setup reduced to one token and two secrets.** deploy.py finds the account, registers the workers.dev subdomain
  and creates the Turnstile widget through Cloudflare's API. The user found the manual Turnstile and token steps
  confusing.
- **Nutrition on request (user's request).** A *Show nutrition information* button under the build, and the
  nutrition in the *I'm done* dialog with *Bake it for me* / *I changed my mind*. The user replaced an earlier idea:
  a question after *I'm done*. Every sight is logged with what was shown. The analysis replays the log to the first
  sight and compares that pizza with the final one (`reveal_measures`, `replay_pieces`). The table shrinks the pizza
  rather than scrolling the page (everything in one window).
- **Participant-only view (user's request).** Participants see the task only: no part counter, and no data preview or
  steps in the demo unless *Researcher view* is ticked.
- **One researcher page for both servers** (`server/admin.html`, a small client app; data from `/admin/api/state` and
  `/admin/api/sessions`), so the page is written once. Reports are shown inside it per study scope. Scopes: owner
  (password), all (researcher link for all studies, `study_keys` row `*`), study.
- **Two servers, one behaviour.** `server/server.py` (Codespace, local) and `cloudflare/src/` (Cloudflare) must stay
  in step: same routes, page and schema. The smoke test runs the same kinds of checks against both.
- **Standard library only** (Python 3.10+, base R, no JS dependencies). The repository must run in a fresh Codespace,
  and in CI without installs beyond R.

## Known limitations and open questions

- **Faces.** Two different eye toppings are found only 51% of the time, and faces with eyebrows or hair 70%. Validate
  `face_detected` against human coding on pilot pizzas before using it.
- **Chance level.** Symmetry chance comes from 12 random layouts per pizza (fixed seed), so it is slightly noisy, and the
  preview uses its own random numbers. Its chance figure can differ a little from the analysis; the match counts and
  axes agree exactly.
- **Speed.** The analysis takes ~0.3 s per pizza, mostly symmetry. 300 participants take ~2 minutes; the server allows
  15.
- **Hosting.** The study server in a Codespace is not production hosting. Data lives in the Codespace until downloaded,
  and Codespaces stop when idle. "About you" collects health-related data (neurotype, diagnoses, eating disorders), so
  storage, retention and hosting must match the ethics approval. Download and delete data regularly.
- **Qualtrics.** Qualtrics has no invites or studies of its own here. To label a Qualtrics pilot, set embedded data
  `study` and `source` in the survey flow; `analyse.py` reads them as columns.
- **Older data.** Logs from before 0.9.0 have no ids for *Start over*. The replay then treats a cleared pizza as a whole,
  which still works.
- **Nutrition.**
  - Piece weights (grams per standard piece) are estimates; weigh real toppings if the nutrition outcomes matter.
  - SR28 values are US foods; for example, US bread is folate-fortified.
  - The panel is shown only during the build, not in the practice or the typical-participant build, unless
    `condition_settings` or `nutrition_panel` apply to those.
- **Resuming restarts the part.** A part is not restored mid-way, so a returning participant's half-built pizza is
  lost. `restarts` flags these sessions; restoring the exact pizza would need the task to rebuild state from its log.
- **Adjustment reasons.** The categories are tested against chance for symmetry only; the others (grouping, spacing,
  ...) are descriptive.
- **Cloudflare free-tier limits** (cloudflare/README.md): roughly 50–150 participants a day. A larger study needs Workers
  Paid ($5/month). The participant page saves about once a second; batching saves less often would cut requests and
  writes.
- **GitHub processes data** in the reports job (public repo, logs show counts only). If ethics does not allow it,
  disable `reports.yml` and run `tools/cloud_sync.py` on an approved computer.
- **Hosting** still matters with the database: `study.db` lives in the Codespace. Download *Database (.sqlite)*
  regularly as a backup.
- **Undecided:**
  - which comparison sample the pilot gets (a second study on the server, or a Prolific general sample);
  - which reference distribution to use for normality (`--reference`);
  - whether to add the "typical participant" build (`typical_build`) for the pilot.

## Suggested next steps

1. Cloudflare: the user creates the account, the token and Turnstile, and adds the GitHub secrets
   (cloudflare/README.md). Then run *Actions → cloudflare*, open `/admin`, and do a dry run there.
2. Pilot dry run: make 3 invite links for `pilot-asd`, run them on two computers, check *Personal links (.csv)*, the
   per-study reports and *Download for R* → `load_pizza()`.
3. Confirm the pilot's intro, consent and completion text in `server/study.json` → `studies.pilot-asd` with the ethics
   wording.
4. After the pilot: code faces by hand on a subset, read `explore.html` → *Against chance* and *Leads*, and
   preregister the chosen leads for the larger study.

## Session log

| date | session | what was done |
|---|---|---|
| 2026-10-27 | Claude Code (cloud) | 0.13.1 (task): hold-to-resize easier (20 px drift allowed, 0.3 s delay, ring and "let go" tip, clearer instructions, tip on click) after participants got stuck on it |
| 2026-10-27 | Claude Code (cloud) | 0.13.0 (task): nutrition on request (reveal button, end dialog with bake / changed my mind), reveal measures, participant-only view |
| 2026-10-27 | Claude Code (cloud) | 0.12.1: hard caps on R2 and D1 (never billed), setup reduced to one token and two GitHub secrets (deploy creates address and Turnstile) |
| 2026-10-27 | Claude Code (cloud) | 0.12.0: Cloudflare version (Worker + D1 + R2, deploy and reports workflows, bot protection), tested in the local Workers runtime |
| 2026-10-27 | Claude Code (cloud) | 0.11.0: SQLite database for the study server, session browser (filter, sort, pages) with filtered exports, per-study researcher links, `analyse.py` reads `study.db` |
| 2026-10-27 | Claude Code (cloud) | 0.10.1: participant flow reviewed in a browser and tightened (resume mid-study, fit to window, compact follow-up, mouse wording); researcher page tidied |
| 2026-10-26 | Claude Code (cloud) | 0.10.0: nutrition panel (study setting / condition), nutrients per pizza, adjustment classification, faster explore |
| 2026-10-26 | Claude Code (cloud) | Built 0.1–0.9 (see CHANGELOG): task, analysis, study server, Methods page, symmetry rework, desktop-only, R export, pilot studies with invite links, changes-of-mind replay, CI summary and this handoff |
