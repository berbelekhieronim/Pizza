# Proposal: what kind of nutrition does each pizza add up to, and does it differ by neurotype?

Status: **proposal, not implemented**. Once agreed, every formula below becomes a Methods-page entry, with a worked
example checked against the code, as for every other measure.

## The problem to solve first: "more" is not "different"

Every nutrient of a pizza grows with how much is on it. A participant who builds a big meaty pizza has more
protein, fat, salt, iron and B12 than someone who builds a small one, so comparing raw grams between groups mostly
re-measures *amount*. The analysis therefore keeps three questions apart:

1. **How much?** Energy and weight.
2. **What kind?** Composition, independent of amount: macronutrient energy shares, nutrient densities and quality
   indices.
3. **From what?** Which food categories supply the nutrients.

It also keeps two levels apart:
- the **whole pizza**: base, sauce, cheese and toppings, i.e. what would be eaten;
- **toppings only**: what the person actually chose on top of a fixed base. This is the primary level for
  preferences, because the base is the same for everyone and dominates the energy.

Notation: for one pizza, *n<sub>k</sub>* is the amount of nutrient *k* in its unit, from the existing `nut_*`
columns (whole pizza), or from the same sum over toppings only. *E* is energy (kcal) and *M* is weight (g).
*RI<sub>k</sub>* is the EU reference intake (Regulation 1169/2011 Annex XIII, as in `analysis/nutrition.json`).

## 1. Quantity

| column | formula | why |
|---|---|---|
| `nq_kcal`, `nq_grams` | *E*, *M* (whole pizza; existing `nut_kcal`, `nut_grams`) | appetite / portion size |
| `nq_top_kcal`, `nq_top_grams` | the same over toppings only (existing `top_kcal`, `top_grams`) | how much they added |
| `nq_energy_density` | *E* / *M* (kcal per g) | dense vs light food, independent of portion |

## 2. Composition (energy-adjusted)

### 2a. Macronutrient energy shares

Atwater factors: protein 4, carbohydrate 4, fat 9 kcal/g. Fibre (2 kcal/g in EU labelling) is left out of the shares
and kept as a density instead.

> *E*<sub>m</sub> = 4P + 4C + 9F, then
> *s*<sub>P</sub> = 4P / *E*<sub>m</sub>, *s*<sub>C</sub> = 4C / *E*<sub>m</sub>, *s*<sub>F</sub> = 9F / *E*<sub>m</sub>
> (columns `nc_protein_share`, `nc_carb_share`, `nc_fat_share`; they sum to 1)

These are compositional data: if one share rises, another must fall, so they cannot be tested as three independent
measures. For tests and for the multivariate step, use **log-ratios** (Aitchison):

> `nc_lr_fat_carb` = ln(*s*<sub>F</sub> / *s*<sub>C</sub>), `nc_lr_prot_carb` = ln(*s*<sub>P</sub> / *s*<sub>C</sub>)

The two log-ratios carry all the information in the three shares, and are unbounded and comparable. The report would
show the shares on a **ternary plot** (one dot per pizza, colour = group, one centroid per group), which is easy to
read: "autistic participants' pizzas sit further toward the fat corner".

Extra composition shares, all as a share of total energy:
- saturated fat: `nc_satfat_share` = 9·SF / *E*, which links directly to the WHO advice to keep it under 10% of
  energy;
- sugars: `nc_sugar_share` = 4·S / *E*.

### 2b. Nutrient densities: micronutrients and things to limit

The nutrient-density method (Willett): the amount per 1000 kcal, so that portion size cancels out.

> `nd_{k}` = 1000 · *n*<sub>k</sub> / *E* for k ∈ {fibre, salt, vitA, vitC, vitD, vitB12, folate, calcium, iron, potassium}

To compare nutrients on one scale, express each as a share of the reference intake that 1000 kcal "should"
provide, scaled to a 2000 kcal day:

> `ndr_{k}` = (*n*<sub>k</sub> / *RI*<sub>k</sub>) / (*E* / 2000)

- 1 means the pizza supplies the nutrient in proportion to its energy.
- Above 1 means it is rich in that nutrient for its energy; below 1 means poor.
- This lets "iron-rich", "calcium-rich" and "vitamin C-poor" sit side by side in one **radar or heat strip per group**.

### 2c. Two established quality indices

**Nutrient Rich Food index (NRF), adapted** (Drewnowski 2009), computed per 100 kcal.
- Encouraged nutrients, the 9 we have data for: protein, fibre, vitamins A, C, D, B12, folate, calcium, iron and
  potassium. That is 10 with B12; B12 is not in the original index, so report the index both with and without it.
- Limited nutrients: saturated fat, sugars and salt. Their maximum recommended values are the reference intakes,
  20 g, 90 g and 6 g.

> NR = Σ<sub>i ∈ encouraged</sub> min(100, 100 · (*n*<sub>i</sub> · 100/*E*) / *RI*<sub>i</sub>)
> LIM = Σ<sub>j ∈ limited</sub> 100 · (*n*<sub>j</sub> · 100/*E*) / *MRV*<sub>j</sub>
> `nq_nrf` = NR − LIM. Higher = more nutrients per calorie and fewer of the things to limit.

**UK front-of-pack traffic lights** (FSA 2016 thresholds, per 100 g of food).

| | green ≤ | red > |
|---|---|---|
| fat | 3 g | 17.5 g |
| saturates | 1.5 g | 5 g |
| sugars | 5 g | 22.5 g |
| salt | 0.3 g | 1.5 g |

> `nq_reds` = number of red lights (0–4), `nq_greens` = number of green lights.

This summary is the easiest of all to explain to participants and community partners.

## 3. Where the nutrients come from

Every nutrient is a sum over toppings: *n*<sub>k</sub> = Σ<sub>t</sub> *g*<sub>t</sub> · *c*<sub>t,k</sub> / 100, where
- *g*<sub>t</sub> is the grams of topping *t* (already known, size² rule);
- *c*<sub>t,k</sub> is the nutrient per 100 g.

Grouping the toppings into categories (meat, fish, cheese, vegetable, fruit, sweet-savoury) gives the share of a
nutrient supplied by each category:

> `ns_{k}_{cat}` = Σ<sub>t ∈ cat</sub> *g*<sub>t</sub> *c*<sub>t,k</sub> / Σ<sub>t</sub> *g*<sub>t</sub> *c*<sub>t,k</sub>, for k ∈ {kcal, protein, fat, fibre, salt}

This turns a nutrition difference into a food explanation: "the higher salt density in group A comes 70% from cured
meat". It is reported as stacked bars per group, and is only screened in explore.html if the composition step shows a
difference.

## 4. How to compare groups

1. **One omnibus test for the profile, before screening single nutrients.**
   - Build a profile per pizza (toppings-only level): the 2 macro log-ratios, ln `ndr_k` for the micronutrients,
     `nq_energy_density` and `nq_nrf`. Each is standardised (z-scored across pizzas).
   - Test whether the groups differ at all with a **PERMANOVA**: pseudo-F on Euclidean distances between profiles,
     p from 4999 permutations of the group labels (Anderson 2001).

     > F = [SS<sub>between</sub> / (g − 1)] / [SS<sub>within</sub> / (N − g)], SS from distances to centroids;
     > p = (#{F<sub>perm</sub> ≥ F<sub>obs</sub>} + 1) / (4999 + 1)

   - A PERMANOVA can also flag groups that differ only in spread, so add a **dispersion check** (PERMDISP: distances to
     the group centroid compared with a permutation test).
   - Show a **PCA map** of the profiles: dots per pizza, group centroids with 95% bootstrap ellipses, and the arrows of
     the nutrients that load most. This is the "which nutrition does each group prefer" picture.
2. **Then screen the single measures** in the existing pipeline (explore.html, area "Nutrition profile"):
   - Cliff's δ with its bootstrap CI, Mann-Whitney / permutation p, and Benjamini-Hochberg q within each grouping, as
     for every other measure.
   - With the omnibus test first, the single measures are read as the explanation of an overall difference rather
     than as 25 separate chances to find something.
3. **Diet stated by the participant is a confounder.** Vegetarians eat less protein, B12 and iron by design. Run every
   comparison twice:
   - on all pizzas;
   - on pizzas from people who state no diet. A difference that survives within "no diet" is about preference, not
     about the diet rule.
4. **Amount versus kind.** Densities are the primary measures. As a sensitivity check, use the residual method: regress
   ln *n*<sub>k</sub> on ln *E* across all pizzas and compare groups on the residuals (Willett's residual method).
   The two should agree.
5. **Seeing the nutrition changes the pizza.** This builds on the existing `post_nutri_*` columns.
   - **Within a group:** does `nq_nrf`, or salt / saturated-fat density, move after the first sight? Use a sign-flip
     permutation test of the change against 0 (the existing `chance_test`).
   - **Between groups:** compare the changes with Cliff's δ.
   - Only participants offered the information count, and the panel or button is a study condition, so randomise it
     (`condition_settings`) for a clean comparison.
6. **Sample size for the larger study:** the existing Noether formula for each lead. For the multivariate profile, plan
   on the smallest single-measure δ that the PERMANOVA difference rests on.

## 5. What it would add to the reports

**Overview → Nutrition:**
- a ternary macro plot;
- the nutrient-density strip (`ndr`) per group;
- NRF and traffic-light counts as dot plots with median and IQR;
- the source stacked bars.

**Explore:**
- the PERMANOVA / PCA panel at the top of a new "Nutrition profile" area;
- the single measures in the screen, with "all pizzas" and "no stated diet" versions.

**Data:** about 35 new columns in `participants.csv`, with R types and labels in `variables.csv`, at both levels
(whole pizza and toppings only).

## 6. Limits to state in any write-up

- **The pizza is imagined, not eaten.** The nutrition measures how the chosen ingredients add up, not intake.
- **Piece weights are estimates.** Weigh real toppings if absolute amounts matter. Densities and shares are much less
  sensitive to this than grams.
- **SR28 values are US foods.** For example, US bread is fortified with folate. Toppings-only measures avoid most of this.
- **Vitamin D and B12 come almost entirely from a few toppings** (fish, egg, meat). Their densities are zero for most
  vegetable pizzas, so test them as "contains a source" (yes/no) rather than as continuous values.
- **Exploratory.** Leads go to a preregistered confirmatory study, with sizes from the Noether calculation.

## Decisions needed

1. **Which level is primary:** toppings only (recommended) or the whole pizza.
2. **Whether to randomise the nutrition button** in the pilot (`condition_settings`), so its effect can be measured
   cleanly.
3. **Whether to weigh real toppings** to replace the estimated piece weights before the larger study.
