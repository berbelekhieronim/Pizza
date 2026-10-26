# Handoff

The state of the project for whoever works on it next (a person or a new Claude session). Read this, `CLAUDE.md`
(rules for changing the code) and the top of `CHANGELOG.md` first. **Update this file at the end of every working
session**: the snapshot, anything decided, and the open items.

## Snapshot (2026-10-26, task version 0.9.0)

- **Repository:** github.com/berbelekhieronim/Pizza, branch `main`. All smoke-test checks pass locally (78) and in CI.
- **Purpose:** an exploratory study of food choice in autistic, ADHD and AuDHD adults (and comparison groups). People
  build a virtual pizza on a computer; everything they do is recorded and analysed to find patterns that can become
  hypotheses for a larger, confirmatory study.
- **Next milestone:** a pilot with an authentic autistic group, run from the study server as study `pilot-asd` with
  personal invite links (README → *Running a pilot with a specific group*).
- **Where it runs:**
  - **Qualtrics:** `qualtrics/*.js` load `pizza-builder.js` from jsDelivr, pinned to a commit SHA. Re-pin after every
    change to the task.
  - **Study server:** `server/server.py` in a GitHub Codespace (`.devcontainer` starts it). The researcher page is
    `/admin?key=…`, and the key is kept in `server/data/.admin_key`.
  - **Demo:** `index.html` in the repo. A copy is published as the user's private Claude artifact "Pizza Builder demo";
    republish it after changing `pizza-builder.js` or `preview.js`.

## How the pieces fit

```
participant ──> pizza-builder.js (practice, build, follow-up + About you; desktop only)
                 │  fields pz_*, pzp_*, pzf_* (JSON strings: final pieces, event log, summary, follow-up)
                 ├─> Qualtrics embedded data ──> CSV export ─┐
                 └─> server/server.py ──> server/data/participants/<pid>.json (+ study, group, source, invite)
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
| `analysis/r_export.py`, `analysis/load_pizza.R` | data dictionary and R loader |
| `server/server.py`, `server/participate.html`, `server/study.json` | study server, participant page, study settings (incl. `"studies"`) |
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
- **R-ready output.** Tables use `NA` and 1/0, and `variables.csv` gives every column's type and levels. Descriptions
  come from the Methods page, so there is one source of truth.
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
- **Undecided:**
  - which comparison sample the pilot gets (a second study on the server, or a Prolific general sample);
  - which reference distribution to use for normality (`--reference`);
  - whether to add the "typical participant" build (`typical_build`) for the pilot.

## Suggested next steps

1. Pilot dry run: make 3 invite links for `pilot-asd`, run them on two computers, check *Invite links (.csv)*, the
   per-study reports and *Download for R* → `load_pizza()`.
2. Confirm the pilot's intro, consent and completion text in `server/study.json` → `studies.pilot-asd` with the ethics
   wording.
3. After the pilot: code faces by hand on a subset, read `explore.html` → *Against chance* and *Leads*, and
   preregister the chosen leads for the larger study.

## Session log

| date | session | what was done |
|---|---|---|
| 2026-10-26 | Claude Code (cloud) | Built 0.1–0.9 (see CHANGELOG): task, analysis, study server, Methods page, symmetry rework, desktop-only, R export, pilot studies with invite links, changes-of-mind replay, CI summary and this handoff |
