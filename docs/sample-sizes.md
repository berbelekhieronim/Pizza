# How many participants each analysis needs

Every number here comes from the code (`analysis/analyse.py`) or from the power formulas the reports already use
(Explore's "n per group for 80% power"). "Pizzas" means **finished own pizzas**: participants who pressed "I'm done"
and are included on the Sessions tab. So far about 1 in 3 people who open the link finish (4 of 13 on 27 Oct), so
recruit about **3 × the numbers below** until the completion rate improves.

## What each participant gives us

| level | how much per participant | file |
|---|---|---|
| measures of the pizza (one row per pizza) | **333 columns**: composition, diet, nutrition, symmetry, contact and stacking, faces, size choices, order and timing, movement, changes of mind, nutrition reveal, follow-up answers, profile scores | `participants.csv` |
| toppings on the tray | 20 rows × 64 columns (one per topping: picked, kept, how many, considered, feelings about it) | `ingredients_long.csv` |
| pieces on the pizza | about 21 rows × 19 columns (position, size, rotation, when placed, touching, stacked) | `pieces_long.csv` |
| logged actions | about 80 rows × 17 columns (every pick, drop, move, resize, removal, undo, with times) | `events_long.csv` |
| adjustments and removals | about 5 + 4 rows (what each change did) | `adjustments_long.csv`, `removals_long.csv` |
| profile | 33 standardised features and a cluster | `profiles.csv` |
| "typical participant" pizza | a second row of the same 333 columns (if the study asks for it) | `participants.csv` (`build` = pzt) |

In total the data dictionary (`variables.csv`) describes **517 variables**. Explore screens **179 measures** for every
grouping (15 groupings, such as neurotype, autistic yes/no, ADHD yes/no, picky eater, gender, age band and study, plus
2 self-report scales). That is about 3,400 comparisons, which is why sample size matters so much here: with that many
tests, small samples produce leads, not findings.

## Minimum participants per analysis, from fewest to most

"Runs from" is when the report shows the analysis at all. "Meaningful from" is the smallest sample where the result can
say something; the reason is in the last column. Group sizes are **per group** (e.g. autistic and non-autistic each).

| # | analysis | where | runs from | meaningful from | why |
|---|---|---|---|---|---|
| 1 | Data check, session counts, who stopped where | Overview, researcher page | 1 session | 1 | counting |
| 2 | Every measure of one pizza (composition, nutrition, symmetry, contact, faces, timing, movement) | Every participant table, `participants.csv` | 1 pizza | 1 pizza with **3+ pieces** | symmetry, contact, spacing and order measures need at least 3 pieces on the pizza |
| 3 | Own pizza vs "typical participant" pizza (overlap, difference in pieces and toppings) | `participants.csv` (`typical_*`) | 1 | 1 | a within-person difference |
| 4 | Dot plots by group | Overview, Symmetry | 1 per group | 1 per group | every person is a dot; nothing is estimated |
| 5 | Group median and interquartile range on the dot plots | Overview, Symmetry | **5 per group** | 5 per group | below 5 the dots are shown but not summarised (`SMALL_N`) |
| 6 | Profiles, clusters, profile map | Profiles | **4 pizzas** | about **30–50 pizzas**, and **10+ per cluster** | clusters from 33 features are unstable in small samples; trust them only with a mean silhouette of 0.25 or more |
| 7 | Explore page | Explore | **6 pizzas** | see 8–10 | below 6 the page explains it needs more |
| 8 | A grouping appears in Explore | Explore | **3 per group**, 2+ groups | **4 per group** | with 3 vs 3 the smallest possible p is 0.10 (exact Mann–Whitney: 2 / 20), so nothing can ever reach p < .05; 4 vs 4 can (0.029) |
| 9 | Stacked bars as percentages (diet class, strong feelings) | Overview | 1 per group (counts) | **10 per group** | below 10 the bars show counts, not percentages |
| 10 | Seeing the nutrition changed the pizza (within person, against no change) | Overview → Nutrition, Explore | 1 revealer | **6 revealers** for p < .05 at all (sign-flip: 2 / 64 = .031); **20** to detect a strong shift (dominance 0.6), **29** for a medium-large one (0.5) | only people who were offered the button and pressed it count |
| 11 | Any Explore difference surviving the false-discovery correction | Explore (q-values) | — | **8 per group**, even for a perfect separation | with 179 measures the best result must reach p ≤ 0.05 / 179 = 0.00028; 7 vs 7 cannot (smallest p 0.00058), 8 vs 8 can (0.00016) |
| 12 | "How normal is this pizza" bands (typical / uncommon / unusual) | Overview → How normal | 2 pizzas | **21 pizzas** (each compared with 20 others), better **40+** or an external reference set | "unusual" is above the 95th percentile of the others: it needs 20 others to exist |
| 13 | Two groups, **very large** difference (Cliff's δ = 0.8; most of one group above most of the other) | Explore, confirmatory test | — | **9 per group** (13 with 5 primary outcomes) | Noether's formula, 80% power, α = .05 two-sided |
| 14 | Two groups, **large** difference (δ = 0.6) | | — | **15 per group** (22) | |
| 15 | Two groups, **large** by convention (δ = 0.474) | | — | **24 per group** (35) | Romano et al. 2006 thresholds: 0.147 small, 0.33 medium, 0.474 large |
| 16 | Correlation with a self-report scale, **strong** (ρ = 0.5) | Explore → links with self-reports | 6 people | **30** (42) | Fisher's z, 80% power |
| 17 | Two groups, **medium** difference (δ = 0.33) | | — | **49 per group** (72) | |
| 18 | Clusters against groups (do the clusters line up with neurotype?) | Profiles | 4 | about **60** (e.g. 3 clusters × 4 groups × 5 expected per cell) | the χ² test needs about 5 expected people per cell |
| 19 | Four neurotype groups (AuDHD, autistic, ADHD, not ND), each compared with the rest | Explore (`neurotype`) | 3 per group | **24 per group = about 100 in total** for large effects; **about 200** for medium | the same per-group numbers as above, for each group |
| 20 | Correlation, **medium** (ρ = 0.3) | | 6 | **85** (125) | |
| 21 | Nutrition profile, multivariate (PERMANOVA, proposed in `nutrition-analysis-proposal.md`) | not built yet | — | about **20 per group** | a common rule for permutation MANOVA on standardised profiles |
| 22 | Two groups, **small** difference (δ = 0.147) | | — | **243 per group** (361) | small effects need a large confirmatory study |
| 23 | Correlation, **small** (ρ = 0.1) | | — | **783** (1,164) | |

Numbers in brackets: the same with a Bonferroni correction for **5 preregistered primary outcomes** (α = .01).

What a given group size can detect (80% power, α = .05, two groups):

| people per group | smallest Cliff's δ detectable |
|---|---|
| 10 | 0.72 (very large) |
| 15 | 0.59 |
| 20 | 0.51 (large) |
| 30 | 0.42 |
| 50 | 0.32 (medium) |

## The formulas

- **Two groups (Mann–Whitney, Cliff's δ):** n per group = 2 (z<sub>α/2</sub> + z<sub>β</sub>)² / (3 δ²)
  (Noether 1987; `n_per_group` in `analyse.py`), z<sub>α/2</sub> = 1.96, z<sub>β</sub> = 0.84.
- **Correlation:** n = ((z<sub>α/2</sub> + z<sub>β</sub>) / atanh ρ)² + 3 (`n_for_rho`).
- **Change against no change (sign test, dominance d):** with p = (1 + d) / 2,
  n = (0.5 z<sub>α/2</sub> + z<sub>β</sub> √(p(1 − p)))² / (p − 0.5)².
- **Smallest possible p:** exact Mann–Whitney with n per group = 2 / C(2n, n); sign-flip with n people = 2 / 2ⁿ.
- **False-discovery correction (Benjamini–Hochberg):** with m tests, the best result passes only if p ≤ 0.05 / m.

## The most promising analyses for this study

The study's groups are self-described: autistic, ADHD, AuDHD (both), other neurodivergent and not neurodivergent, plus
"picky eater" and self-rated sensory sensitivity to food. The leads below have both a clear reason to expect a
difference and a measure the task records well. **Pick 3–5 of them as preregistered primary outcomes**, and treat
everything else in Explore as exploratory.

These leads are on the **Explore** page, under **Planned hypotheses** (H1–H8). Each shows its verdict, the measures with
their predicted direction, effect, p and q, whether the direction matches the prediction, and a bar for how close the
smaller group is to the 24 people a large effect needs. They are corrected as one small family of tests, so a real
difference can show there before it would survive the full screen.

| lead | why expect it | measures | first test |
|---|---|---|---|
| **1. Fewer, more familiar toppings** (autistic, AuDHD; picky eaters) | food selectivity and preference for the familiar are among the most replicated eating findings in autism | `n_distinct`, `shannon`, `prop_unusual_distinct`, `ingredient_rarity`, `atypicality_pct` | autistic (incl. AuDHD) vs not ND |
| **2. Foods kept apart** (autistic) | many autistic people dislike foods touching | `prop_touching`, `prop_stacked`, `clark_evans` (spacing) | autistic vs not ND |
| **3. Order and symmetry** (autistic) | preference for sameness and pattern | `mirror_score`, `rot_score`, `size_match_index`, `sweep_consistency` | autistic vs not ND |
| **4. Sensory reasons and safe foods** (autistic, sensory scale) | sensory sensitivity drives food choice | `n_strong`, `n_sensory_reasons`, `n_safe_foods`; correlate with `self_sensory_food` | correlation (needs ~30 for ρ = 0.5) |
| **5. Faster, more changes of mind** (ADHD, AuDHD) | impulsivity and novelty seeking | `t_first_pick`, `decision_median`, `n_adjustments`, `revision_rate`, `n_changed_mind`, more unusual toppings | ADHD (incl. AuDHD) vs not ND |
| **6. AuDHD in between, or its own pattern** | the two traits pull in opposite directions (sameness vs novelty) | leads 1 and 5 together | AuDHD vs autistic-only vs ADHD-only: needs 3 groups of 24+ |
| **7. Nutrition information changes the pizza** (all; interoception differs in autism) | people may revise once they see calories or salt | `nutri_revealed`, `post_nutri_d_kcal`, `post_nutri_direction` | randomise the button (half the people) and compare; within revealers, sign-flip test |
| **8. "My pizza vs a typical person's"** | theory-of-mind and self-other differences | `typical_jaccard`, `typical_count_dev` | autistic vs not ND |

**A realistic plan.** For the pilot, aim for **24 per group** in two groups (autistic incl. AuDHD vs not ND), about 50
finished pizzas, or about 150 people opening the link at today's completion rate. That detects large differences on the
leads above with 5 primary outcomes and gives the effect sizes for planning the confirmatory study, where medium effects
need about 50–70 per group.

## Notes

- **Exploratory screening is not confirmation.** Explore runs about 3,400 comparisons. Report its leads as leads, with
  their q-values, and test them in a new sample.
- **Self-described groups overlap.** AuDHD people are counted in both "autistic yes/no" and "ADHD yes/no". Compare
  AuDHD separately when there are enough of them.
- **Exclusions.** Decide them before looking at group differences (see the Data check and the Sessions tab), ideally in
  the preregistration.
