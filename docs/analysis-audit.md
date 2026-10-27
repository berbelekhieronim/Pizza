# Analysis audit (27 Oct 2026)

A review of every analysis the reports run, read as a scientist: what is sound, what was fixed, and what was pruned
because it was redundant, measured the interface rather than the choice, or could not support the claim it seemed
to make. Every change is also on the Methods page and in the CHANGELOG.

## Fixed: the statistics

| problem | why it mattered | now |
|---|---|---|
| The false discovery correction ran **within each grouping**, while the page makes about 3,400 comparisons across 15 groupings | a ✓ meant "passes among this grouping's tests", so the page as a whole promised far fewer false positives than it delivered | **one correction over every comparison on the page** (all groupings and self-reports together). The ideas to test stay their own family, because they were chosen before looking at the data |
| **Bootstrap intervals for groups of 3** | a percentile bootstrap of 3 values only reshuffles them, and the "interval" looks precise when it is not | intervals only when both groups have **5 or more** |
| **Sample size "at the effect seen"** for leads and ideas | the largest of many screened effects is overestimated (winner's curse), so these numbers were too optimistic, or absurd (33,837 per group) | removed; leads plan for **half** the effect seen; ideas give the number for a large effect with their correction |
| **"Against chance" tests** (symmetry, even spread, blocks, sweeps against a fixed chance level) | the chance layouts dropped pieces uniformly at random, piling them up, while people spread pieces out: "more even than random" and some "more symmetric than chance" were built into the method, for everyone | **removed**. The symmetry chance level itself is now computed from random layouts **spaced like the pizza** (no two centres closer than the pizza's own 10th-percentile neighbour distance), so mirror_score and rot_score measure symmetry beyond what the spacing alone gives |
| **Neurotype compared "each group vs everyone else"** | "Not ND vs the rest" pooled autistic, ADHD and AuDHD people into one comparison group | **each neurodivergent group vs Not ND** (the reference) |
| **"How normal" percentiles and bands with a reference of 8 pizzas** | "above the 95th percentile" cannot be told apart from noise with fewer than 20 reference pizzas | percentiles and bands only with **20+ reference pizzas**; the surprise in bits (continuous, always defined) is used everywhere else, including the profiles |
| **Clusters always reported** | hierarchical clustering always splits people into groups; with a mean silhouette of 0.1–0.2 the "clusters" were a convenient split of one cloud, described as if they were types | clusters only with **20+ pizzas and a mean silhouette of 0.25+** (Kaufman & Rousseeuw 1990); otherwise the page says there are no clear clusters |
| **Clusters × groups χ²** with expected counts under 5 | the χ² distribution is wrong for such tables | **permutation test** (2000 shuffles), only for reported clusters and 20+ people |
| **Leads ranked by effect size** | in small groups the largest effects are the noisiest; leads were device, gender and cheese differences from groups of 2–3 | leads come from the study's own groupings, need **5+ per group**, and are ranked by **p**; with too few people the page says there are no leads |
| A grouping compared on **the measure that defines it** | "people who revealed the nutrition reveal it more often" | measures that define a grouping are left out of it |
| **Device (touch / mouse)** as a grouping | the task is desktop only | removed |

## Pruned from the screen (kept in the data files)

These columns stay in `participants.csv` for anyone who wants them, but Explore no longer tests them, because every
extra test weakens the correction for the measures that matter.

| measures | why |
|---|---|
| mouse movement: path, straightness, pauses, dwell, hold, edge crossings (`mv_*`), also removed from the profiles | depend on the mouse, the hand and the screen more than on the choice |
| hovering as "considering": `n_considered_not_picked`, `hover_total_ms`, the per-topping "considered" rows | the cursor passes over the tray on its way somewhere: resting on a topping is not considering it |
| interface counters: moves, removals, undos, drops, "I'm done" presses, time between "I'm done" and submitting, start over declined, distance moved, pieces moved or removed, base changed after toppings, adjustments after "I'm done" | duplicates of `revision_rate` and `n_adjustments`, or counts of interface events |
| reasons for adjustments: grouping, spacing, unstacking, size match, nudges, symmetry counts | assigned by an arbitrary first-match rule; `adj_symmetry_excess` (with its chance baseline) stays |
| nutrient totals: whole-pizza energy, protein, saturated fat, sugars, fibre, salt, vitamins, topping weight, energy share | they mostly re-measure how much is on the pizza and rest on estimated piece weights; the **energy of the toppings** stays. A composition analysis (shares, densities) is proposed in `nutrition-analysis-proposal.md` |
| secondary reveal measures: when in the build, how long the table was open, saturated-fat and meat changes, removals per add after seeing it, rebuilt after the end dialog | the primary ones stay: revealed, changed after seeing it, energy change, "I changed my mind" |
| parts of other measures: positive / negative feelings, texture / smell / touching reasons, cravings, evenness, uniqueness, the per-topping "changed mind" rows | already counted in `n_strong`, `n_sensory_reasons`, `shannon` and the rarity measures |

## Kept, with their limits

- **Composition and variety** (pieces, toppings, Shannon variety, unusual toppings, diet class): direct, well defined.
- **Symmetry** (mirror and rotation, matched pieces of the same topping at the best axis): defined geometrically,
  with worked examples on the Methods page; the chance level is now spacing-aware.
- **Space, contact and the crust** (coverage, touching, stacking, spacing, off-centre): geometric, from the drawn outlines.
- **Faces**: a rule-based detector, 84% of drawn test faces found and 1.8% false alarms (tests/face_benchmark.py). It
  is a heuristic: treat a "face" as "a face-like arrangement", not as intent.
- **Changes of mind** (`revision_rate`) and **adjustments for symmetry beyond chance**: from the replayed log.
- **Follow-up answers** (strong feelings, safe foods, sensory reasons): self-report, used as given.
- **Nutrition**: estimates from USDA values and estimated piece weights; good for comparing pizzas, not for intake.
- **Profiles and the profile map**: descriptive. The map (principal components) shows how people differ; it is not a test.
- **Ideas to test**: chosen from the literature before the data, tested as their own family; still exploratory until
  preregistered and run on a new sample.

## What a reader should take from any result here

The study is exploratory. A ✓ means "passes the false discovery rate among the comparisons this page makes", in the
data collected so far. It is a reason to preregister a test, not a finding. Sample sizes for confirmation are in
`sample-sizes.md` and on the Methods page.
