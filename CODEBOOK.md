# Pizza Builder codebook

## Conventions

- **Coordinates**: `x` to the right, `y` up, relative to the pizza centre; `1.0` = outer edge of the crust.
  Sauce covers `r < 0.86`. A topping stays where it is dropped, including on the crust (`0.86 < r ≤ 1`); dropped beyond
  `r = 1` it is off the pizza. (With the `snapIn` option, centres beyond `r = 0.9` are pulled in to 0.9 and `snapped = 1`.)
- **Times**: milliseconds since the page's task appeared.
- **Topping codes**:

| code | topping | category | tier | perishable | | code | topping | category | tier | perishable |
|---|---|---|---|---|---|---|---|---|---|---|
| `pep` | Pepperoni | meat | common | ✓ | | `pin` | Pineapple | fruit | mid | |
| `ham` | Ham | meat | common | ✓ | | `anc` | Anchovies | seafood | mid | ✓ |
| `chk` | Chicken | meat | common | ✓ | | `shr` | Shrimp | seafood | mid | ✓ |
| `mus` | Mushrooms | veg | common | | | `egg` | Egg (boiled slice) | egg | mid | ✓ |
| `grp` | Green pepper | veg | common | | | `gor` | Blue cheese | dairy | mid | ✓ |
| `oni` | Red onion | veg | common | | | `nor` | Nori | seaweed | unusual | |
| `oli` | Black olives | veg | common | | | `kim` | Kimchi | veg | unusual | |
| `crn` | Sweetcorn (a pinch of 3 kernels) | veg | common | | | `par` | Pear | fruit | unusual | |
| `jal` | Jalapeños | veg | common | | | `ban` | Banana *(not in the default tray)* | fruit | unusual | |
| `bas` | Basil | herb | common | | | `wal` | Walnuts *(not in the default tray)* | nut | unusual | |
| `tom` | Tomato slice (practice only) | | | | | | | | | |

One drag places one piece, which is one quantity unit. The tiers are a-priori. Check them against the sample's own
`norm` ratings and inclusion rates, and report both.

## Embedded-data fields

Each build page writes four fields under its prefix (`pzp_` practice, `pz_` build, `pzt_` optional typical build).
In the Simple layout, Qualtrics stores them as `__js_<name>`.

### `<prefix>final` - the finished pizza

A JSON array with one entry per piece, bottom to top: `[id, code, x, y, rotation_deg, scale, variant, add_order, size]`.
`size` is the size the participant chose by holding the piece (1 = normal; holding pulses it between 0.5 and 2.5). The drawn size is `scale × size`.
`id` numbers every pick-up, including ones that were rejected. `add_order` is the order of first placement.
`scale` (0.9-1.1) and `variant` (0-2) are small random differences in appearance, kept so the pizza can be redrawn exactly.

### `<prefix>events` - everything that happened

A JSON array of `[t, type, ...]`:

| type | fields after `t, type` | meaning |
|---|---|---|
| `start` | tray order (space-separated codes) | task shown |
| `pick` | code, id, pointer (`m`ouse/`t`ouch/`p`en) | topping lifted from the tray |
| `add` | code, id, x, y, drag_ms, snapped, size | dropped on the pizza |
| `reject` | code, id, x, y, drag_ms | lifted from the tray, then dropped off the pizza |
| `tap` | code, id | touched without dragging (a hint is shown) |
| `grab` | code, id | placed topping picked up again |
| `move` | code, id, x, y, drag_ms, snapped, size | placed topping moved |
| `resize` | code, id, size, hold_ms | placed topping pressed and held in place, released at a new size |
| `remove` | code, id, x, y, drag_ms | placed topping dragged off the pizza |
| `abort` | code, id | drag interrupted by the browser (e.g. a system gesture) |
| `undo` | undone action (`add`/`move`/`resize`/`remove`/`clear`), id or count | |
| `clear` | number of pieces removed | "Start over" confirmed |
| `sauce`, `cheese` | new value | sauce: `none`/`tomato`/`white`/`bbq`; cheese: `none`/`light`/`normal`/`extra` |
| `hover` | code, ms | mouse rested ≥150 ms on a tray item (desktop only) |
| `hide`, `show` | | tab hidden or visible again |
| `done`, `cancel`, `finish` | | "I'm done" pressed, confirmation declined, task finished |

### `<prefix>summary` - totals, device and layout

`v` script version · `mode` · `cond` condition label · `start` ISO time · `finished` ·
`tFinish`, `tDone` (first press of "I'm done"), `tSubmit` (confirmed and submitted; = `tFinish`), `nDone` (presses of "I'm done"),
`nDoneCancelled` (times they went back to edit), `tFirstPick`, `tFirstAdd`, `tLast` · `nPieces`, `nDistinct`, `counts` {code: n} · `sauce`, `cheese` · `tray` order ·
`n` {event type: count} · `nGrown`, `nShrunk` (pieces made bigger / smaller) · `dragMsMedian` · `addGapMsMedian` · `hiddenMs`, `hides` ·
`pointer` (first pointer type used) · `coarse` (touch-first device) · `hover` (device can hover) · `vw`, `vh`, `dpr` ·
`pizzaPx` (pizza diameter on screen in CSS px) · `layout` (`wide` side-by-side or `narrow` stacked) · `trimmed` (hover events dropped to save space).
Practice only: `targetErr` (distance from the target centre for each attempt, max 3), `stepT` (time each step was completed), `stepsDone`.

### `<prefix>counts`

`pep:3,ham:0,...`: the same counts in a form that is safe to pipe into later questions.

### `pzf_data` - follow-up

The default (`style: 'strong'`):

```
{ v, style: 'strong', start, countsKnown, order: [codes in the order shown],
  strong: [codes the participant has strong feelings about], none: true if they chose "None of these",
  firstTapMs, pickMs,
  items: { <code>: { placed, feel, about: [...], safe, sameway, crave, t: {<question>: ms to first answer}, ms } },
  finished, tTotal }
```

- `feel`: `love` / `like` / `mixed` / `dislike` / `cant` (can't stand it)
- `about`: any of `texture`, `smell`, `taste`, `look`, `touching` (it touching other food), `other`
- `safe`: a "safe food", one they can nearly always eat: `yes` / `sometimes` / `no`
- `sameway`: it has to be a certain way (brand, cut, cooking) to eat it: `yes` / `sometimes` / `no`
- `crave`: crave it or go looking for it: `often` / `sometimes` / `never`
- `placed`: pieces of it on their pizza (`null` if the counts did not reach the follow-up page)

With `style: 'ratings'` (and optionally `askPizza`, `askDiet`):

```
{ v, start, countsKnown, order: [codes in the order rated],
  pizza: { express, distinct, auton, control, system, safety, t: {...}, ms },
  items: { <code>: { placed, like, never, fam, safe, disg, norm, ident, reasons: [...], other, t: {<scale>: ms to first answer}, ms } },
  diet: [vegetarian|vegan|pescatarian|nopork|nobeef|halal|kosher|glutenfree|dairyfree|other|none], dietOther,
  health: [allergy|intolerance|digestive|badexp|sensory|none], healthOther, freq, dietMs,
  finished, tTotal }
```

`pizza` items are 1-7, strongly disagree → strongly agree:
- `express`: My pizza expresses who I am.
- `distinct`: My pizza is different from the pizza most people would make.
- `auton`: I made my pizza exactly the way I wanted to.
- `control`: While making my pizza, I felt in control of the result.
- `system`: I followed a rule or system when arranging the toppings.
- `safety`: I chose toppings I was confident would be safe for me to eat.

`ident` (*To what extent does X on your pizza reflect who you are?*) is asked only for toppings on the pizza.
If the counts did not reach the follow-up page, it is asked for every topping (`countsKnown: false`).

Scales run 1-7:
- `like`: dislike a lot → like a lot (`null` if `never` tasted)
- `fam`: familiarity
- `safe`: perceived safety
- `disg`: disgust
- `norm`: how appropriate most people would think it is as a topping

`reasons` appears only for toppings with zero pieces. It can include `taste`, `diet`, `culture`, `allergy`, `health`, `safety`,
`disgust`, `unfamiliar`, `notpizza`, `nofit`, `noreason`, `other`.
`freq` is one of `never`, `lt1m`, `1-3m`, `1w`, `gt1w`.

## Computed measures (`analysis/analyse.py`)

### `participants.csv` (one row per pizza)

| column | definition |
|---|---|
| `n_pieces`, `n_distinct`, `n_<code>` | quantity: total pieces, distinct toppings, pieces of each |
| `shannon`, `evenness`, `simpson` | diversity over topping counts: H = -Σp ln p; H / ln(distinct); 1 - Σp² |
| `n_categories`, `meat_or_fish` | categories used; any meat or seafood |
| `n_distinct_common`, `_mid`, `_unusual` | distinct toppings in each a-priori tier |
| `prop_unusual_distinct`, `prop_unusual_pieces` | share of distinct toppings / of pieces that are unusual-tier |
| `n_perishable_included` | perishable toppings used (meat, seafood, egg, blue cheese) |
| `ingredient_rarity` | mean over the person's toppings of (1 − share of *other* participants using it) |
| `combo_rarity` | mean over each pair of the person's toppings of (1 − share of others using both). Captures unusual combinations of ordinary toppings |
| `profile_uniqueness` | 1 − mean Jaccard similarity of the person's topping set to every other participant's |
| `n_never_picked` | toppings never lifted from the tray |
| `n_picked_not_kept` | toppings lifted at least once but absent from the final pizza (approached, then avoided) |
| `n_ev_*` | event counts |
| `centroid_offset` | distance of the toppings' mean position from the centre (0 = balanced) |
| `mean_r`, `sd_r`, `prop_outer` | radial position; share of pieces beyond r = 0.6 |
| `circ_resultant` | mean resultant length of the angles: 0 = spread around, 1 = all on one side |
| `sectors_used`, `sector_cv`, `sector_chi2` | pieces per 8 slices: slices with any; spread of counts (CV, χ² against equal) |
| `slice_spread` | for each topping with ≥2 pieces, the slices it reaches ÷ the most it could reach (min(8, n)), averaged. 1 = each topping spread round the pizza |
| `clark_evans` | mean nearest-neighbour distance ÷ that expected for random placement in the disc (Donnelly edge correction). <1 clustered, >1 evenly spaced |
| `clark_evans_within` | the same within each topping (≥3 pieces), averaged |
| `nn_cv` | coefficient of variation of nearest-neighbour distances: low = evenly spaced, like a grid or ring |
| `angular_regularity` | for each topping with ≥3 pieces, CV of the angular gaps between its pieces around the centre (0 = evenly spaced like clock positions), averaged |
| `sector_similarity` | mean cosine similarity of the topping mix between the occupied slices: 1 = the same pattern repeats in every slice |
| `segregation` | share of pieces whose nearest neighbour is the same topping, minus the share expected from the counts alone. >0 = toppings kept together (e.g. half-and-half) |
| `n_touch_pairs`, `n_stack_pairs` | pairs of pieces whose outlines touch (gap ≤ 1.5 mm, or a slight overlap); pairs where one lies substantially on the other (overlap deeper than half the thinner piece's half-width). Outlines are capsules at each piece's real length, width, rotation and size |
| `prop_touching`, `prop_stacked` | share of pieces touching at least one other / stacked on or under another |
| `max_stack_depth` | the tallest pile, in layers (1 = nothing stacked). Drawing order is stacking order: later pieces lie on top |
| `stack_same_share`, `touch_same_share` | share of stacked / touching pairs that are the same topping (piling one topping vs layering different ones) |
| `nn_gap_mm` | median edge-to-edge distance from each piece to its nearest neighbour, in mm on a 30 cm pizza (negative = overlapping) |
| `n_grown`, `n_shrunk`, `size_mean`, `size_min`, `size_max` | pieces made bigger / smaller by holding; mean, smallest and largest size factor |
| `diet_class` | the strictest diet the whole pizza fits: `vegan`, `vegetarian` (dairy or egg, including any cheese or white sauce), `pescatarian` (anchovies or shrimp, no meat), `meat` |
| `n_<vegan/vegetarian/seafood/meat>_pieces`, `area_share_<...>` | pieces, and share of topping area, in each diet class. Kimchi counts as vegan (change `DIET_CLASS` if your kimchi has fish sauce) |
| `atypicality_bits`, `composition_pct` | *which toppings*: surprisal of the pizza's set of toppings under the reference, Σ over toppings offered of −log₂ P(on or off) with P from the reference inclusion rate (+0.5 smoothing); and its percentile in the reference distribution |
| `count_pct` | *how many*: how extreme the number of different toppings is in the reference, in both directions, as 100 × (1 − two-sided tail probability). A plain pizza or one with everything scores high |
| `atypicality_pct`, `normality_band` | the more extreme of the two percentiles; `typical` < 75, `uncommon` 75-95, `unusual` > 95 |
| `unusual_elements` | up to three choices that make the pizza most surprising (each ≥ 2 bits), e.g. "added nori (on 3% of reference pizzas)" or "0 different toppings (like 1% of reference pizzas)" |
| `n_resized_pieces`, `size_match_same`, `size_match_category`, `size_match_other`, `size_match_index` | size matching: of the pieces resized by more than 10%, the share with another piece of the same topping / of another topping in the same category / of a different category within 10% of its size; the last is the chance baseline, and the index is same − other |
| `n_on_crust`, `n_over_edge`, `border_share`, `n_centre_on_crust`, `max_overhang_mm` | pieces whose outline reaches the crust (beyond r = 0.86) / hangs over the outer edge (beyond r = 1); their share of all pieces; pieces centred on the crust; the furthest overhang in mm on a 30 cm pizza |
| `face_detected`, `face_score`, `face_eyes`, `face_mouth`, `face_nose`, `face_up_deg`, `face_brows`, `face_cheeks` | a face made of toppings: found or not, how clean it is (0.6-1), the eye topping ("Olives + Mushrooms" when the eyes differ), the mouth (a long piece or "row of n ..."), whether there is a nose, which way the face points (degrees, 90 = up), and whether it has eyebrows / cheeks (0/1). Rules in `face_detect()` in the analysis script; accuracy on drawn faces in README |
| `cluster` | the participant's cluster in `profiles.html` (blank if there are too few pizzas) |
| `n_strong`, `strong_none`, `strong_list` | ingredients with strong feelings; whether they chose "None of these"; the list as `code:feeling` |
| `n_strong_positive`, `n_strong_negative` | of those, loved or liked / disliked or can't stand |
| `n_safe_foods`, `n_same_way`, `n_crave_often` | of those, "safe foods"; ones that must be a certain way; ones craved often |
| `n_about_<texture/smell/taste/look/touching/other>`, `n_sensory_reasons` | how often each reason was given; the sensory reasons added up |
| `strong_pos_on_pizza`, `strong_neg_on_pizza` | share of the loved/liked ingredients that are on their pizza, and of the disliked ones (expected near 1 and 0) |
| `topping_area_cm2` | total area covered by toppings' outlines (overlaps counted twice), on a 30 cm pizza |
| `coverage` | share of the sauced area under toppings |
| `sym_mirror`, `sym_axis_deg` | best mirror symmetry: mean distance from each reflected piece to the nearest piece of the same topping, at the best of 18 axes, ÷ the same for 40 random layouts of the same toppings. <1 = more symmetric than chance |
| `sym_rot180` | the same for a half turn |
| `sym_rot_best`, `sym_rot_k` | the best k-fold rotational symmetry for k = 2-8 (ratio to random as above), and its k |
| `first_topping`, `switch_rate`, `blockiness` | placement order: share of consecutive placements that change topping; expected minus observed switch rate (>0 grouped, <0 alternating) |
| `sweep_consistency` | share of consecutive placements that keep turning round the pizza in the same direction (1 = a steady clockwise/anticlockwise sweep, ~0.5 = none) |
| `meat_before_veg` | mean relative rank of vegetable placements minus meat placements (>0 = meat first) |
| `t_first_pick`, `t_finish`, `t_active` | ms; `t_active` excludes time on another tab |
| `t_done_first`, `t_submit`, `t_after_done`, `n_done_presses` | time to completion: first press of "I'm done", confirmed submission, the time between them, and how often "I'm done" was pressed (more than once = went back to edit) |
| `decision_median` | median ms from the end of one action to lifting the next topping. This is decision time without the motor component |
| `add_gap_median`, `drag_median` | median ms between placements; median drag duration |
| `practice_*`, `drag_vs_practice` | motor baseline from the practice (drag time, targeting error, tries, duration, pointer); build drag ÷ practice drag |
| device | `pointer`, `coarse`, `layout`, `pizzaPx`, `vw`, `vh`, `dpr`, `hiddenMs`, `hides` |
| `diet`, `diet_other`, `pizza_freq` | from the follow-up |
| `health_<allergy/intolerance/digestive/badexp/sensory>`, `health_any`, `health_other` | food-related health and past experience |
| `pz_<express/distinct/auton/control/system/safety>` | the "About your pizza" items |
| `ident_mean`, `ident_mean_unusual` | mean "reflects who I am" rating over the toppings used / over unusual-tier toppings used |
| `safe_mean_included`, `norm_mean_included` | mean perceived safety and mean perceived-norm rating of the toppings used |
| `norm_incl_corr` | correlation across toppings between included (0/1) and the perceived-norm rating |
| `counter_normative` | toppings included that the participant thinks most people find inappropriate (norm ≤3) |
| `normative_avoided` | toppings left off that they think most people find appropriate (norm ≥5) |
| `perceived_norm_dev` | mean \|included − (norm − 1)/6\|: 0 = choices match the perceived norm exactly |
| `like_incl_corr`, `disg_incl_corr` | how far choices follow the participant's own liking and disgust |
| `sample_norm_dev`, `sample_count_dev` | deviation from the rest of the sample: mean \|included − others' inclusion rate\|; Σ\|count − others' mean count\| |
| `typical_jaccard`, `typical_count_dev`, `typical_d_*` | own pizza vs their "typical participant" pizza (if built) |
| `flag_tab_away`, `flag_fast`, `flag_empty` | >30 s on another tab; finished in <15 s; no toppings |

### `ingredients_long.csv` (one row per participant × topping)

`tier`, `perishable`, `tray_pos` (1 = first in the tray), `count`, `included`, `picks`, `rejects`, `removes`, `picked_not_kept`,
`first_pick_ms`, `first_add_ms`, `hover_ms`, `decision_ms_mean` (mean time from the previous action to picking this topping up),
`area_cm2` and `size_mean` (amount of this topping, and its mean size factor), `n_touching`, `n_on_top`, `n_covered`
(pieces of this topping touching another piece, lying on another, lying under another),
`strong` (they have strong feelings about it), `feel`, `about_<reason>` (0/1), `safe_food`, `same_way`, `crave` (default follow-up),
`diet_conflict` (the stated diet usually excludes this topping:
- vegetarian → meats, anchovies, shrimp
- vegan → those plus egg and blue cheese
- pescatarian → meats
- no pork or halal → pepperoni, ham
- kosher → pepperoni, ham, shrimp
- no beef → pepperoni
- dairy-free → blue cheese),
the ratings (`like`, `fam`, `safe`, `disg`, `norm`, `ident`), `never_tasted`, `why_<reason>` (0/1; empty when the question was not asked), `why_other_text`, `rating_ms`.

### `profiles.csv`

`pid`, `group`, `cluster`, then `z_<measure>` for each of the 29 profile measures: the measure standardised across the
sample (mean 0, SD 1, capped at ±3; missing values take the sample median), signed so that higher means *more* of the
named trait. Measures marked log are log(1 + x) first. In order:
- **Composition:** pieces (log), different toppings, variety (Shannon), unusual toppings share, animal products (0 vegan … 3 meat)
- **Normality:** unusual combination (which-toppings percentile), unusual number of toppings (how-many percentile)
- **Space:** mirror symmetry (−`sym_mirror`), rotational symmetry (−`sym_rot_best`), even spacing (−`nn_cv`), repeating slice pattern,
  spread out (Clark-Evans), coverage, touching, stacking, on or over the crust, off-centre
- **Size:** amount (log area), size variation, pieces resized, size matching within a topping
- **Order:** grouped by topping, placed in a sweep
- **Time:** time to start, decision time, time to completion (each log)
- **Figurative:** face-like (`face_score`)
- **Feelings:** strong feelings about toppings (`n_strong`), sensory reasons given (`n_sensory_reasons`)

Clusters: Ward's hierarchical clustering on the Euclidean distances between profiles; the number of clusters (2-8) is the one
with the highest mean silhouette, unless `--clusters` fixes it.
