# The pizza builder

What a participant can put on a pizza, what each choice means, what the builder records, and how the builder has
changed between versions. This page is about the builder only (`pizza-builder.js`); the consent, questionnaires and
servers are in the README, and every recorded field is in `CODEBOOK.md`.

**Current version: 0.15.0.** Every pizza stores the version that recorded it (`v` in `pz_summary`) and the toppings
that person was offered (`tray` in `pz_summary`). The analysis reads both, so pizzas recorded by different versions can
be analysed together (see *Changing the builder without breaking the data* below).

## What the participant does

1. **Practice** (`pzp_` fields): one practice topping (tomato slice) to learn placing, moving, resizing and removing.
   Nothing here counts as a choice.
2. **Build** (`pz_` fields): choose a **sauce** and a **cheese** (where the study offers a choice), then drag toppings
   from the **tray** onto the pizza, one piece per drag. A piece is resized by holding it, removed by dragging it off
   the pizza. The tray order is shuffled for each participant and recorded (`tray` in the summary, `start` event).
3. Optional, per study: a nutrition table (`nutrition_panel`), nutrition on request (`nutrition_reveal`), a
   "typical participant" pizza (`pzt_`), and the follow-up questions (`pzf_data`).

## Sauces

| code | English | Polish | on the button | diet of the base | nutrition (per 30 cm pizza) |
|---|---|---|---|---|---|
| `none` | None | Bez sosu | | vegan | nothing |
| `tomato` | Tomato | Pomidorowy | 🌿 **vegan** / **wegański** | vegan | pizza sauce, SR28 06152, 80 g |
| `white` | White | Biały | | vegetarian (béchamel: butter, milk) | white sauce, SR28 06264, 80 g |
| `bbq` | BBQ | BBQ | 🌿 **vegan** / **wegański** | vegan | barbecue sauce, SR28 06150, 60 g |

The **vegan mark** (from 0.15.0) is a small green leaf with the word *vegan* (*wegański* in Polish) under the sauce's
name. It is information for the participant only: nothing extra is recorded for it, and the sauce choice is recorded
as before (`sauce` in the summary and `sauce` events). Pizzas recorded with the mark have `v` ≥ 0.15.0. Which sauces
carry it: `VEGAN_SAUCES` in `pizza-builder.js`, which must list the sauces that `SAUCE_DIET` in `analysis/analyse.py`
calls vegan (the smoke test checks this). The word is a text of its own (`task.vegan` in `tools/texts.py`), so a
study can change it.

## Cheeses

| code | English | Polish | diet of the base | nutrition |
|---|---|---|---|---|
| `none` | None | Bez sera | vegan | nothing |
| `light` | Light | Light | vegetarian | mozzarella, part-skim, SR28 01028, 60 g |
| `normal` | Normal | Zwykły | vegetarian | the same, 100 g |
| `extra` | Extra | Extra ser | vegetarian | the same, 150 g |
| `vegan` | Vegan | Wegański ser | vegan | coconut-oil vegan mozzarella (label values; SR28 has none), 100 g |

A study chooses which are offered and which is selected at the start (`cheeses`, `cheese` in `server/study.json`).
Pizza Pilot 11.2026 offers `none`, `light`, `extra`, `vegan`, with `light` selected.

## Toppings

The default tray (every study, unless a study sets `ingredients`) has **21 toppings** since 0.15.0:

| code | topping | Polish | category | tier | diet | grams per piece | kcal / 100 g |
|---|---|---|---|---|---|---|---|
| `pep` | Pepperoni | Pepperoni | meat | common | meat | 3 | 504 |
| `ham` | Ham | Szynka | meat | common | meat | 3 | 163 |
| `chk` | Chicken | Kurczak | meat | common | meat | 5 | 165 |
| `tun` | Tuna | Tuńczyk | seafood | common | seafood | 3 | 86 |
| `mus` | Mushrooms | Pieczarki | veg | common | vegan | 3 | 22 |
| `grp` | Green pepper | Zielona papryka | veg | common | vegan | 3 | 20 |
| `oni` | Red onion | Czerwona cebula | veg | common | vegan | 2 | 40 |
| `oli` | Black olives | Czarne oliwki | veg | common | vegan | 1 | 115 |
| `crn` | Sweetcorn | Kukurydza | veg | common | vegan | 1 | 67 |
| `jal` | Jalapeños | Jalapeño | veg | common | vegan | 1.5 | 27 |
| `bas` | Basil | Bazylia | herb | common | vegan | 0.5 | 23 |
| `anc` | Anchovies | Anchois | seafood | mid | seafood | 3 | 210 |
| `pin` | Pineapple | Ananas | fruit | mid | vegan | 6 | 50 |
| `shr` | Shrimp | Krewetki | seafood | mid | seafood | 6 | 99 |
| `egg` | Egg | Jajko | egg | mid | vegetarian | 8 | 155 |
| `gor` | Blue cheese | Ser pleśniowy | dairy | mid | vegetarian | 2 | 353 |
| **`tof`** | **Tofu** (from 0.15.0) | **Tofu** | soy | mid | vegan | 3 | 144 |
| `nor` | Nori | Nori | seaweed | unusual | vegan | 0.5 | 35 |
| `kim` | Kimchi | Kimchi | veg | unusual | vegan | 5 | 15 |
| `kan` | Kangaroo | Kangur | meat | unusual | meat | 6 | 158 |
| `fig` | Fig | Figa | fruit | unusual | vegan | 10 | 74 |

Pear (`par`), banana (`ban`) and walnuts (`wal`) are drawn too but are not on the default tray. `tom` (tomato slice)
is the practice item only. **Tofu** is a cube of firm tofu, about 1.4 cm a side, cream with lightly browned edges
(nutrition: SR28 16426, tofu, raw, firm, prepared with calcium sulfate). Its tier is *mid*: known, but not a
standard pizza topping. Check every tier against your own sample's ratings.

## The diet of a whole pizza (`diet_class`)

The strictest diet the whole pizza fits, from the toppings **and** the base:

1. `meat` if any meat topping;
2. else `pescatarian` if any seafood (anchovies, shrimp, tuna);
3. else `vegetarian` if egg or blue cheese, **or white sauce, or any cheese except vegan cheese**;
4. else `vegan`. So tomato or BBQ sauce (or none), no cheese or vegan cheese, and only vegan toppings (tofu included)
   make a vegan pizza.

The base has worked this way since vegan cheese came in (0.14.0); 0.15.0 writes it down as two tables in
`analysis/analyse.py` (`SAUCE_DIET`, `CHEESE_DIET`; an unknown sauce or cheese counts as vegetarian, never vegan) and
fixes the demo preview, which had counted vegan cheese as dairy. The smoke test compares the task's vegan marks, the
analysis and the preview on 180 combinations of base and toppings.

## What a build records

Four fields per build (prefix `pz_`; `pzp_` practice, `pzt_` typical pizza): `final` (every piece: topping, position,
rotation, size), `events` (every pick, drop, move, resize, removal, sauce and cheese change, with times), `summary`
(totals, timing, `sauce`, `cheese`, `tray`, `v`, device) and `counts` (`pep:3,ham:0,…`). Details: `CODEBOOK.md`.

## Changing the builder without breaking the data

The pilot already has pizzas, so a change to the builder must leave those pizzas valid and comparable:

- **The version** (`VERSION` in `pizza-builder.js`) goes up with every change to what participants see or what is
  recorded, and is stored with every pizza: a change is always visible in the data.
- **A new topping** is only on the trays of pizzas recorded after it was added. The analysis treats it as **not
  offered** (NA), never as "left off" (0), for earlier pizzas: `n_tof` is NA where the tray had no tofu; tofu has no
  row in `ingredients_long.csv` for them; and the measures that compare a person with the rest of the sample
  (`sample_norm_dev`, `sample_count_dev`, `ingredient_rarity`, `combo_rarity`) compare each topping only with the
  people who were offered it. Topping popularity in the reports is a share of the people who were offered it.
- **The vegan mark** changes nothing in the data.

To add a topping, change all of these together (the smoke test fails when one is missing):
`ING`, `TIER`, `DEFAULT_INGREDIENTS` and the Polish `names` in `pizza-builder.js`; `CATS`, `NAMES`, `TIER`, `SIZE`,
`FOOT`, `COLORS` (and `PERISHABLE`, `MEATS`, `DIET_EXCLUDES`, `DIET_CLASS` if it is not vegan) in
`analysis/analyse.py`; `NAMES`, `FOOT`, `SIZE`, `CATS` (and `DIET`, `TIER`) in `preview.js`; `TRAY` in
`examples/simulate.py` and `analysis/synthetic.py`; `FOODS` in `tools/build_nutrition.py` (then run it, which rewrites
`analysis/nutrition.json` and the copy in `pizza-builder.js`); `NAMES` (and `SAME_OK` if the name is the same in
Polish) in `tools/texts.py`; the topping table in `CODEBOOK.md` and this page. Then bump `VERSION`, add a CHANGELOG
entry and re-pin `qualtrics/*.js`.

## Version history of the builder

| version | what changed for participants | what changed in the data |
|---|---|---|
| 0.15.0 | tofu on the tray (all studies); a green *vegan* mark on the tomato and BBQ sauce buttons | `tof` in `final`, `events`, `counts`, `tray`; nothing new for the mark |
| 0.14.0 | Polish; vegan cheese; the metryczka; the baked pizza at the end; consent TAK / NIE (Pizza Pilot 11.2026) | cheese `vegan`; `pzf_data.met` |
| earlier | see `CHANGELOG.md` | |
