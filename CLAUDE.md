# Working on this repository

**Start of a session:** read `HANDOFF.md` (state, decisions, open items) and the top of `CHANGELOG.md`, then run
`python3 tests/smoke_test.py`.
**End of a session (or before handing over):** add a `CHANGELOG.md` entry for what changed (bump `VERSION` in
`pizza-builder.js` when the recorded data changes), update `HANDOFF.md` (snapshot, decisions, open items, session log),
make sure the smoke test passes, push, and check that the GitHub Actions run is green (its summary lists every check).

- **Every change to a measure or test updates the Methods page in the same change.** `analysis/methods.py` holds one
  entry per output column (formula + the `analyse.py` function that computes it) and the worked examples. Add, rename
  or redefine a column in `analysis/analyse.py` → edit its entry in `SECTIONS`; if the formula changed, update the
  worked example's hand calculation too. `python3 tests/smoke_test.py` fails when any output column has no entry, and
  building the page fails when a worked example no longer matches its formula.
- Computations that also run in the demo preview (`preview.js`: face detection, symmetry) must stay identical to
  `analyse.py`; the smoke test compares the two on hundreds of pizzas.
- **Desktop only.** The task blocks phones and tablets (`desktopOnly`). Do not work on mobile or touch layouts.
- Toppings live in several tables that must stay in step: `ING`/`TIER`/`DEFAULT_INGREDIENTS` in `pizza-builder.js`;
  `CATS`, `NAMES`, `TIER`, `PERISHABLE`, `SIZE`, `FOOT`, `COLORS`, `MEATS`/`DIET_EXCLUDES`/`DIET_CLASS` in
  `analysis/analyse.py`; `NAMES`, `DIET`, `TIER`, `FOOT`, `SIZE`, `CATS`, colours and the simulated `REF` in
  `preview.js`; `TRAY` in `examples/simulate.py`; the topping table in `CODEBOOK.md`.
- After changing `pizza-builder.js`, commit, then re-pin the jsDelivr URL in `qualtrics/*.js` to that commit's SHA.
- Run `python3 tests/smoke_test.py` before pushing (standard library + node only).
