#!/usr/bin/env python3
"""The Methods page: how every number in the analysis is counted, one entry per output column.

    python3 analysis/methods.py methods.html

The formulas below are the single written definition of each measure. The page shows, for every entry, the function in
analyse.py that computes it (with its current line number), and worked examples that are computed by that code when
the page is built and checked against an independent hand calculation: if code and formula disagree, building fails.
tests/smoke_test.py fails when any output column has no entry here, so a new or renamed measure must be described
here in the same change. Standard library only.
"""
import inspect
import math
import os
import random
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse as A  # noqa: E402

# Placeholders in column names: {ing} = a topping code, {reason} = a reason code, and so on.
SLOTS = {'ing': '|'.join(sorted(set(A.CATS) | {'tom'})), 'reason': '|'.join(A.REASONS), 'about': '|'.join(A.ABOUT),
         'health': '|'.join(A.HEALTH), 'item': '|'.join(A.PIZZA_ITEMS), 'scale': '|'.join(A.SCALES),
         'nd': '|'.join(A.AB_NEURO), 'eat': '|'.join(A.AB_EATING), 'ev': 'pick|add|reject|tap|grab|move|remove|resize|abort|undo|clear|hover',
         'class': 'vegan|vegetarian|seafood|meat', 'nut': '|'.join(A.NUT_COL.values()), 'tier': 'common|mid|unusual', 'feature': '[a-z_0-9]+'}

# (section, intro, [(columns, how it is counted, function in analyse.py)]). Notation: n = pieces on the pizza; each piece
# has a topping, a centre (x, y) in pizza radii (crust edge = 1 = 15 cm, y up) and a size factor s (random 0.9-1.1 times
# the hold-to-resize factor g). Keep the text short: what is counted, and how.
SECTIONS = [
    ('Identifiers and raw counts', None, [
        ('pid, build, condition, finished, group', 'As recorded: participant, which build (pz = own pizza, pzt = "typical" pizza), condition, finished (1/0), group from the study link.', 'analyse'),
        ('study, source', 'Study server: the study the participant\'s link belongs to (study.json "studies"), and the recruitment source written on their invite link (or ?source= on an open link).', 'analyse'),
        ('sauce, cheese', 'The base chosen: sauce none / tomato / white / bbq; cheese none / light / normal / extra.', 'analyse'),
        ('n_pieces, n_{ing}', 'Pieces on the finished pizza, in total and per topping.', 'analyse'),
        ('n_ev_{ev}', 'Number of events of that type in the log (pick, add, reject, tap, grab, move, remove, resize, abort, undo, clear, hover).', 'analyse'),
        ('pointer, coarse, layout, pizzaPx, vw, vh, dpr, hiddenMs, hides', 'Device record: pointer used first (mouse / touch / pen), coarse pointer (1/0), task layout, pizza width in px, window size, pixel ratio, ms the tab was hidden, times hidden.', 'analyse'),
        ('pid, build, t_ms, type, a, b, x, y, drag_ms, snapped', '<b>events_long.csv</b>: one row per logged event: time since the task started (ms), event type, its first two fields (topping, piece id), drop position, drag duration, snapped (0/1).', 'analyse'),
    ]),
    ('Composition and variety', None, [
        ('n_distinct', 'Toppings with ≥ 1 piece.', 'analyse'),
        ('shannon', 'H = −Σ p<sub>k</sub> ln p<sub>k</sub>, p<sub>k</sub> = pieces of topping k / n.', 'shannon'),
        ('evenness', 'H / ln(n_distinct); empty when n_distinct &lt; 2.', 'analyse'),
        ('simpson', '1 − Σ p<sub>k</sub>².', 'analyse'),
        ('n_categories, meat_or_fish', 'Food categories used (meat, seafood, veg, fruit, herb, egg, dairy, seaweed, nut); 1 if any meat or seafood.', 'analyse'),
        ('n_distinct_{tier}', 'Distinct toppings in each a-priori tier (common / mid / unusual; table TIER).', 'analyse'),
        ('prop_unusual_distinct, prop_unusual_pieces', 'Unusual-tier toppings / n_distinct; unusual-tier pieces / n.', 'analyse'),
        ('n_perishable_included', 'Distinct perishable toppings used (meat, seafood, egg, blue cheese; table PERISHABLE).', 'analyse'),
        ('n_never_picked, n_picked_not_kept', 'Tray toppings never lifted; lifted at least once but not on the final pizza.', 'analyse'),
        ('first_topping, meat_before_veg', 'First topping placed. Mean placement rank of veg minus of meat, ranks scaled 0-1 (> 0: meat placed earlier).', 'order_measures'),
    ]),
    ('Diet', None, [
        ('diet_class, diet_rank', 'Strictest diet the pizza fits: meat if any meat; else pescatarian if any seafood; else vegetarian if egg, blue cheese, any cheese, or white sauce; else vegan. Rank 0 = vegan … 3 = meat.', 'pizza_diet_class'),
        ('n_{class}_pieces, area_share_{class}', 'Pieces of each diet class; their outline area / total topping area.', 'analyse'),
        ('diet, diet_other', 'Stated diets (follow-up), space-separated; "prefer not to say" is left out.', 'analyse'),
        ('diet_conflict', '<b>ingredients_long</b>: 1 if the stated diets usually exclude this topping (table DIET_EXCLUDES); empty if no diet stated.', 'ingredient_rows'),
    ]),
    ('Normality: how usual is the pizza', 'Compared with a reference set of pizzas (--reference, else every other pizza in the sample).', [
        ('atypicality_bits', 'Σ over tray toppings of −log<sub>2</sub> P, where P = r<sub>k</sub> if topping k is on the pizza, else 1 − r<sub>k</sub>; r<sub>k</sub> = (reference pizzas with k + 0.5) / (N + 1).', 'atypicality'),
        ('composition_pct', 'Percentile of atypicality_bits among the reference pizzas\' own scores (each scored leave-one-out); ties count ½.', 'normality'),
        ('count_pct', '100 × (1 − t), t = min(1, 2 × min(P(≤ d), P(≥ d))), d = n_distinct, P from the reference with +0.5 / (N + 1) smoothing (two-sided).', 'count_extremeness'),
        ('atypicality_pct, normality_band', 'max(composition_pct, count_pct); band typical &lt; 75 ≤ uncommon &lt; 95 ≤ unusual.', 'normality'),
        ('unusual_elements', 'Text: an extreme count (count_pct ≥ 75) and the up to 3 toppings contributing ≥ 2 bits.', 'normality'),
        ('sample_norm_dev, sample_count_dev', 'Leave-one-out against the rest of the sample: mean over toppings of |included − inclusion rate|; Σ |count − mean count|.', 'analyse'),
        ('ingredient_rarity, combo_rarity, profile_uniqueness', 'Mean (1 − rate) of the toppings used; mean (1 − co-occurrence rate) over pairs used; 1 − mean Jaccard similarity of the topping set to every other pizza.', 'analyse'),
        ('typical_jaccard, typical_count_dev, typical_d_pieces, typical_d_distinct', 'Own pizza vs the "typical participant" pizza (if built): Jaccard of topping sets; Σ |count difference|; difference in n; in n_distinct.', 'analyse'),
    ]),
    ('Symmetry', 'Three worked examples follow this table.', [
        ('mirror_match', 'Share of pieces with a mirror partner at the best axis. A piece is matched when its reflection lands on a piece of the <i>same topping</i> within ½ (r<sub>i</sub> + r<sub>j</sub>) (r = bounding radius × s). One-to-one, closest pairs first; a piece on the axis can match itself.', 'sym_match'),
        ('mirror_axis_deg, mirror_cx, mirror_cy', 'Best axis: every 3° (0-177°) through the pizza centre and through the toppings\' centroid; the 3 best refined in 0.25° steps (±1.5°). Best = most matched, then smallest summed distance.', 'best_mirror'),
        ('mirror_chance', 'Mean mirror_match of 12 random layouts of the same pieces (same toppings and sizes, uniform positions within r = 0.9), with the same axis search.', 'symmetry'),
        ('mirror_score', '(match − chance) / (1 − chance) when match ≥ chance; (match − chance) / chance below. −1 = nothing matched, 0 = chance, 1 = every piece matched.', 'symmetry'),
        ('rot_match, rot_k, rot_cx, rot_cy, rot_chance, rot_score', 'The same for turning the pizza by 360°/k, k = 2…8, about each centre. Best k = most matched; equal counts go to the higher k.', 'best_rotation'),
    ]),
    ('Space', None, [
        ('centroid_offset', 'Distance of the mean piece position from the centre.', 'spatial'),
        ('mean_r, sd_r, prop_outer', 'Mean and SD of the pieces\' distance from the centre; share with distance > 0.6.', 'spatial'),
        ('circ_resultant', '|Σ (cos θ<sub>i</sub>, sin θ<sub>i</sub>)| / n over the pieces\' angles: 0 = balanced round the centre, 1 = all on one side.', 'spatial'),
        ('sectors_used, sector_cv, sector_chi2', '8 equal slices: slices with a piece; SD / mean of pieces per slice; Σ (c − n/8)² / (n/8).', 'spatial'),
        ('slice_spread', 'Per topping with ≥ 2 pieces: slices it appears in / min(8, its pieces); mean over toppings.', 'spatial'),
        ('clark_evans', 'Mean nearest-neighbour distance / E, E = ½ √(A/n) + (0.0514 + 0.041/√n) P/n (Donnelly edge correction), A and P of the disc r = 0.9. &lt; 1 clustered, ≈ 1 random, > 1 even. n ≥ 3.', 'clark_evans'),
        ('clark_evans_within', 'clark_evans of each topping\'s own pieces (≥ 3), averaged.', 'spatial'),
        ('nn_cv', 'SD / mean of the nearest-neighbour distances (0 = perfectly even spacing).', 'spatial'),
        ('angular_regularity', 'Per topping with ≥ 3 pieces: SD / mean of the angular gaps between its pieces round the centre; mean over toppings (0 = clock-like).', 'angular_regularity'),
        ('sector_similarity', 'Mean cosine similarity between the topping-count vectors of every pair of non-empty slices (1 = every slice has the same mix).', 'sector_similarity'),
        ('segregation', 'Share of pieces whose nearest neighbour is the same topping, minus the share expected by chance, Σ c<sub>k</sub>(c<sub>k</sub> − 1) / (n(n − 1)).', 'spatial'),
        ('coverage', 'Share of a 48 × 48 grid of points inside the sauce (r &lt; 0.86) that lie under a piece\'s outline.', 'coverage'),
    ]),
    ('Contact, stacking and the crust', 'Each piece\'s outline is a capsule (a line segment with a half-width; table FOOT) scaled by s. Gap = distance between the two segments − both half-widths.', [
        ('n_touch_pairs, n_stack_pairs', 'Pairs with gap ≤ 1 unit (1.5 mm). Stacked when they overlap by more than half the thinner half-width, else touching.', 'contacts'),
        ('prop_touching, prop_stacked', 'Pieces in at least one touching (any contact) / stacked pair, ÷ n.', 'contact_measures'),
        ('max_stack_depth', 'Tallest pile: longest chain of stacked pieces in drawing order (1 = none stacked).', 'contact_measures'),
        ('stack_same_share, touch_same_share', 'Share of stacked / all contact pairs that are the same topping.', 'contact_measures'),
        ('nn_gap_mm', 'Median over pieces of the gap to the nearest other piece, in mm (negative = overlapping).', 'contact_measures'),
        ('n_on_crust, n_over_edge, border_share', 'Outer edge of the outline (furthest end + half-width): inside the sauce ≤ 0.86 &lt; on the crust ≤ 1.005 &lt; over the edge. border_share = (crust + over) / n.', 'border_measures'),
        ('n_centre_on_crust, max_overhang_mm', 'Pieces whose centre is beyond 0.86; furthest outer edge beyond 1, in mm (1 = 150 mm).', 'border_measures'),
        ('n_touching, n_on_top, n_covered', '<b>ingredients_long</b>: pieces of this topping touching any piece / lying on top / lying under.', 'ingredient_rows'),
    ]),
    ('Size', 'g = the hold-to-resize factor (1 = not resized, 0.5-2.5).', [
        ('n_grown, n_shrunk, resized_share', 'Pieces with g > 1.01, g &lt; 0.99; share with |g − 1| > 0.01.', 'analyse'),
        ('size_min, size_mean, size_max, size_sd', 'Of g over the pieces (population SD).', 'analyse'),
        ('topping_area_cm2, area_cm2', 'Σ capsule areas (π w² + 4 h w) × s² × 0.15², in cm² (per topping in ingredients_long).', 'area_cm2'),
        ('n_resized_pieces, size_match_same, size_match_category, size_match_other', 'For each piece with |g − 1| > 0.1: is another piece within 10% of its size (|g<sub>i</sub> − g<sub>j</sub>| ≤ 0.1 max) of the same topping / another topping of the same category / a different category? Share yes.', 'size_matching'),
        ('size_match_index', 'size_match_same − size_match_other (other categories = chance baseline).', 'size_matching'),
        ('size_mean', '<b>ingredients_long</b>: mean g of this topping\'s pieces.', 'ingredient_rows'),
    ]),
    ('Faces', 'Rules in face_detect(); accuracy on drawn test faces in README (tests/face_benchmark.py).', [
        ('face_detected, face_score', '1 if a face is found: two similar eyes, a mouth under them, ≤ 1 nose, ≤ 1 stray feature in the face, face pieces ≥ 30% of nearby and of all pieces. Score = 1 − 0.15 × stray − 0.6 × |mouth offset| − 0.1 if the eyes differ (kept if ≥ 0.6); 0 if none.', 'face_detect'),
        ('face_eyes, face_mouth, face_nose, face_up_deg, face_brows, face_cheeks', 'Eye topping(s); mouth (topping or "row of n …"); nose 0/1; direction the face points (90 = up); eyebrows 0/1; cheeks 0/1.', 'face_detect'),
    ]),
    ('Order of placement', None, [
        ('switch_rate', 'Share of consecutive placements that change topping.', 'order_measures'),
        ('blockiness', 'Expected switch rate if the order were random, 1 − Σ c<sub>k</sub>(c<sub>k</sub> − 1) / (n(n − 1)), minus switch_rate. > 0 = grouped by topping.', 'order_measures'),
        ('sweep_consistency', 'Placements > 0.15 from the centre: share of consecutive angular steps that keep the previous step\'s direction (1 = steady sweep round).', 'sweep_consistency'),
    ]),
    ('Time (ms from the task start)', None, [
        ('t_first_pick, t_done_first, t_submit, t_finish', 'First pick; first press of "I\'m done"; confirmed submission (t_finish = t_submit).', 'timing'),
        ('n_done_presses, t_after_done', '"I\'m done" presses; t_submit − t_done_first.', 'timing'),
        ('t_active', 't_submit − time the tab was hidden.', 'timing'),
        ('decision_median', 'Median time from the end of one action (add, reject, move, remove, tap, resize, undo, sauce, cheese) to the next pick.', 'timing'),
        ('add_gap_median, drag_median', 'Median time between consecutive adds; median drag duration of adds and moves.', 'timing'),
        ('practice_drag_median, practice_target_err, practice_target_tries, practice_ms, practice_pointer, drag_vs_practice', 'Practice trial: median drag; first distance from the target; tries; duration; pointer; drag_median / practice_drag_median.', 'practice_measures'),
        ('first_pick_ms, first_add_ms, hover_ms, decision_ms_mean, picks, rejects, removes, picked_not_kept, tray_pos', '<b>ingredients_long</b>: per topping: first pick and add time; total mouse rest on its tray item; mean decision time before picking it; counts; lifted but not kept (0/1); position in the shuffled tray.', 'ingredient_rows'),
    ]),
    ('Nutrition', 'Nutrients per 100 g from USDA SR28 (analysis/nutrition.json, made by tools/build_nutrition.py; stand-ins where SR28 has no entry are listed there and in the README). The task\'s nutrition panel uses the same table and formula. Base of a 30 cm pizza: dough 250 g; sauce tomato 80 g, white 80 g, BBQ 60 g; mozzarella light 60 g, normal 100 g, extra 150 g.', [
        ('grams', '<b>ingredients_long</b>: Σ over this topping\'s pieces of grams<sub>piece</sub> = grams of a standard piece × s², s = drawn size (random 0.9-1.1 × hold-to-resize g). A slice is flat, so its weight follows its area: twice as wide = 4 × the grams.', 'piece_grams'),
        ('kcal', '<b>ingredients_long</b>: grams × kcal per 100 g / 100.', 'analyse'),
        ('{nut}', 'Whole pizza (toppings + dough + sauce + cheese): Σ grams / 100 × amount per 100 g. Salt = sodium × 2.5. Units in the name (g, mg, ug).', 'nutrition_measures'),
        ('nut_grams, top_grams, top_kcal, top_kcal_share', 'Weight of the whole pizza; weight and energy of the toppings alone; top_kcal / nut_kcal.', 'nutrition_measures'),
        ('nutrition_panel', '1 if the participant saw the live nutrition panel while building (a study setting or condition).', 'nutrition_measures'),
    ]),
    ('Changes of mind and other actions', 'The log is replayed piece by piece: added, moved, removed (dragged off, undone, or wiped by "Start over"), restored (undo). The replay must end with exactly the pieces on the finished pizza (replay_matches_final).', [
        ('n_added_pieces, n_removed_pieces', 'Pieces ever added; pieces removed and not restored.', 'action_measures'),
        ('n_removed_dragged, n_removed_undo, n_removed_start_over, n_restored', 'Removed pieces by how (dragged off the pizza; Undo of their adding; "Start over"); removals undone again.', 'action_history'),
        ('removed_list, removal_ms_median', 'Removed pieces per topping (code:count); median time a piece stayed on the pizza before being dragged off or undone.', 'action_measures'),
        ('revision_rate', 'n_removed_pieces / n_added_pieces (0 = nothing taken back).', 'action_measures'),
        ('n_dropped_toppings, dropped_list', 'Toppings added at some point but not on the finished pizza ("changed mind"), and which.', 'action_measures'),
        ('n_start_over, n_start_over_declined', '"Start over" confirmed; opened, then declined.', 'action_measures'),
        ('n_moved_pieces, move_dist_total', 'Distinct pieces moved; total distance moved (pizza radii).', 'action_measures'),
        ('n_edits_after_done', 'Adds, removals, moves, resizes, undos and start overs after the first "I\'m done" press.', 'action_measures'),
        ('n_sauce_changes, n_cheese_changes, base_changed_after_toppings', 'Sauce / cheese choices made; 1 if either was changed after the first topping was placed.', 'action_measures'),
        ('hover_total_ms, n_considered_not_picked, considered_list', 'Total mouse rest on tray toppings (rests ≥ 150 ms are logged); toppings rested on ≥ 500 ms in total but never picked up, and which.', 'action_measures'),
        ('rejected_list, replay_matches_final', 'Toppings lifted from the tray and dropped off the pizza (code:count); 1 if the replay ends with the finished pizza.', 'action_measures'),
        ('added_pieces, removed_pieces, dropped, moves, resizes, considered_not_picked', '<b>ingredients_long</b>: the same per topping.', 'action_measures'),
        ('piece_id, how, t_added, t_removed, ms_on_pizza, restored', '<b>removals_long</b>: one row per removed piece: how (dragged off / undo / start over), when added and removed (ms), time on the pizza, position when removed, restored later (0/1).', 'action_history'),
    ]),
    ('Adjustments: why pieces were moved', 'An adjustment is a placed piece moved, or resized in place. The log is replayed (undos included) and each adjustment is judged against the pizza as it was at that moment. Symmetry is measured against the finished pizza\'s own best mirror axis and best rotation: the symmetry the person ended up with.', [
        ('n_adjustments, n_adj_moves, n_adj_resizes, n_adj_after_done', 'Adjustments; of which moves, resizes in place; adjustments after the first "I\'m done".', 'adjustment_measures'),
        ('sym_gain_mirror, sym_gain_rot, sym_gain', '<b>adjustments_long</b>: matched pieces (sym_match) at the final best mirror axis / rotation after the move − before; sym_gain = the larger. > 0 = the move made the pizza more symmetric.', 'adjustment_measures'),
        ('sym_chance', '<b>adjustments_long</b>: the same piece moved the same distance in 12 random directions (staying on the pizza): share of those that also gain symmetry.', 'adjustment_measures'),
        ('n_adj_symmetry, n_adj_symmetry_loss, adj_symmetry_expected, adj_symmetry_excess', 'Moves with sym_gain > 0 / < 0; Σ sym_chance (symmetry-making moves expected by chance); (n_adj_symmetry − expected) / moves: symmetry-seeking beyond chance.', 'adjustment_measures'),
        ('spacing, same_topping_dist_change, contacts_change, r_before, r_after, dist, nudge', '<b>adjustments_long</b>: +1 if the piece\'s nearest-neighbour distance moved towards the median nearest-neighbour distance of the other pieces (evener spacing), −1 away; change in distance to the nearest piece of the same topping; change in pieces it touches; distance from the centre before / after; distance moved; nudge = moved &lt; 0.08 (1.2 cm).', 'adjustment_measures'),
        ('t, kind, g_before, g_after, size_match_gain, after_done', '<b>adjustments_long</b>: time (ms), move or resize, size factor before / after; size_match_gain = 1 if a resize brought the piece within 10% of another piece of the same topping (and it was not before).', 'adjustment_measures'),
        ('reason, adj_reasons', 'The first that applies: symmetry (sym_gain > 0), grouping (nearest same topping > 0.05 closer), spreading (> 0.05 further), spacing (+1), unstacking (fewer contacts), inward / outward (> 0.05 nearer / further from the centre), nudge, other; resizes: size match or resize. adj_reasons counts them per pizza (reason:count).', 'adjustment_measures'),
        ('n_adj_grouping, n_adj_spreading, n_adj_spacing, n_adj_unstacking, n_adj_inward, n_adj_outward, n_adj_size_match, n_adj_nudges', 'Adjustments by reason; n_adj_nudges = moves under 0.08 (1.2 cm), whatever their reason.', 'adjustment_measures'),
        ('pid, build, piece_id, ing', '<b>adjustments_long</b>: participant, build, the piece and its topping.', 'adjustment_measures'),
    ]),
    ('Movement of each drag', 'Recorded per drag in the task (event field 10): path, straightness, pauses, longest pause, dwell, crossings, hold.', [
        ('mv_path', 'Pointer path length / pizza diameter; median over drags.', 'movement_measures'),
        ('mv_straight', 'Straight-line distance start→drop / path length (1 = straight); median.', 'movement_measures'),
        ('mv_pauses, mv_paused_share, mv_longest_pause', 'Stops of ≥ 250 ms (pointer within 8 px) after the piece first moved: mean per drag; share of drags with one; longest (ms).', 'movement_measures'),
        ('mv_dwell, mv_hold, mv_crossings, mv_n', 'Median still time before letting go; median time from press to first movement; mean crossings of the pizza edge; drags with a record.', 'movement_measures'),
        ('mv_path, mv_straight, mv_pauses, mv_longest_pause, mv_dwell, mv_crossings, mv_hold', '<b>events_long</b>: the same for this one drag (no medians): path, straightness, pauses, longest pause (ms), dwell (ms), edge crossings, hold before moving (ms).', 'movement_measures'),
    ]),
    ('Follow-up: strong feelings', 'Ingredients tapped in "Do you have strong feelings about any of these?", then up to five questions each.', [
        ('n_strong, strong_none, strong_list', 'Ingredients tapped; chose "None of these" (0/1); the list as code:feeling.', 'analyse'),
        ('n_strong_positive, n_strong_negative', 'Of those, feeling love/like; dislike/can\'t stand.', 'analyse'),
        ('n_safe_foods, n_same_way, n_crave_often', 'Answered "yes" safe food; "yes" must be a certain way; craves "often".', 'analyse'),
        ('n_about_{about}, n_sensory_reasons', 'Ingredients where that reason was ticked; sum over texture, smell, taste, look, touching.', 'analyse'),
        ('strong_pos_on_pizza, strong_neg_on_pizza', 'Share of positively / negatively felt ingredients that are on the pizza.', 'analyse'),
        ('strong, feel, about_{about}, safe_food, same_way, crave', '<b>ingredients_long</b>: tapped (0/1) and the answers for this ingredient.', 'ingredient_rows'),
    ]),
    ('Follow-up: ratings style and diet card (when used)', None, [
        ('{scale}, never_tasted, rating_ms', '<b>ingredients_long</b>: 1-7 ratings (like, familiarity, safety, disgust, perceived norm, identity); never tasted; time on the card.', 'ingredient_rows'),
        ('why_{reason}, why_other_text', '<b>ingredients_long</b>: reasons ticked for leaving the topping off (0/1).', 'ingredient_rows'),
        ('pz_{item}', '1-7 agreement with the six "about your pizza" statements.', 'analyse'),
        ('norm_incl_corr, like_incl_corr, disg_incl_corr', 'Pearson r over toppings between included (0/1) and the norm / liking / disgust rating.', 'corr'),
        ('counter_normative, normative_avoided, perceived_norm_dev', 'Included toppings rated norm ≤ 3; left-off toppings rated ≥ 5; mean |included − (norm − 1)/6|.', 'analyse'),
        ('ident_mean, ident_mean_unusual, safe_mean_included, norm_mean_included', 'Means over included toppings (unusual tier only for ident_mean_unusual).', 'analyse'),
        ('health_{health}, health_any, health_other, pizza_freq', 'Diet card: food-health answers (0/1), any of them, text, how often they eat pizza.', 'analyse'),
        ('ing, name, cat, tier, perishable, count, included', '<b>ingredients_long</b>: topping code, name, category, tier, perishable (0/1), pieces, included (0/1).', 'ingredient_rows'),
    ]),
    ('About you (groupings)', None, [
        ('neurotype', 'From the ticked self-descriptions: autistic + ADHD → AuDHD; autistic → Autistic; ADHD → ADHD; dyslexic etc. or otherwise neurodivergent → Other ND; none → Not ND; prefer not to say → empty.', 'neurotype'),
        ('nd_{nd}, dx_autistic, dx_adhd', 'Each self-description ticked (0/1); how autism / ADHD was identified (formal / self / waiting / pnts).', 'about_measures'),
        ('nd_identified', 'formal if every ticked autism / ADHD identity is formally diagnosed, else "self or waiting".', 'about_measures'),
        ('eat_{eat}, eat_any', 'Eating history ticked (0/1); any of picky, ARFID, eating disorder, allergy.', 'about_measures'),
        ('self_picky, self_sensory_food, age_band, gender', '1-7 self-ratings; demographics (prefer not to say → empty).', 'about_measures'),
    ]),
    ('Removals (removals_long.csv: one row per piece taken off the pizza)', None, [
        ('pid, build, ing, x, y', '<b>removals_long</b>: participant, build, topping code, position the piece had when removed.', 'action_history'),
    ]),
    ('Pieces (pieces_long.csv: one row per piece on the finished pizza)', None, [
        ('pid, build, ing, x, y', '<b>pieces_long</b>: participant, build, topping code, centre position (pizza radii, y up).', 'piece_rows'),
        ('piece_id, place_order', 'The piece\'s id in the task; its place in the order pieces were added (1 = first).', 'piece_rows'),
        ('r, angle_deg', 'Distance of the piece\'s centre from the pizza centre (pizza radii); angle anticlockwise from 3 o\'clock (0-360°).', 'piece_rows'),
        ('rot, g, s', 'Rotation of the drawing (°); hold-to-resize factor g; drawn size s = random 0.9-1.1 × g.', 'piece_rows'),
        ('zone', 'inside the sauce / on the crust / over the edge, as for n_on_crust.', 'border_measures'),
        ('touching, on_top, covered, pile_depth', 'In any contact pair (0/1); lies on top of / under another piece in a stacked pair (0/1); height of the pile ending at this piece.', 'contact_measures'),
        ('mirror_matched, rot_matched', 'Has a partner at the pizza\'s best mirror axis / rotation (the green rings; their mean = mirror_match / rot_match).', 'sym_match'),
    ]),
    ('Data-quality flags', None, [
        ('flag_tab_away, flag_fast, flag_empty', 'Tab hidden > 30 s; submitted in &lt; 15 s; no pieces.', 'analyse'),
        ('restarts', 'Study server: times the participant came back mid-study (reload, closed tab, personal link reopened) and the part they were on started again; their pizza is from the last attempt.', 'analyse'),
    ]),
    ('Profiles and clusters (profiles.html, profiles.csv)', None, [
        ('z_{feature}', 'For each of the profile measures: log(1 + x) where marked, × −1 where lower means more of the trait, missing → sample median, then z = (x − mean) / SD across participants, capped at ±3.', 'build_profiles'),
        ('cluster', 'Ward hierarchical clustering on Euclidean distances between profiles (Lance-Williams updates); k = 2…8 with the highest mean silhouette s = (b − a) / max(a, b) (a = mean distance to own cluster, b = to the nearest other), unless --clusters.', 'profile_analysis'),
        ('(profile map)', 'Principal components of the profiles\' covariance matrix (Jacobi eigen-decomposition); first two drawn.', 'profile_analysis'),
        ('(clusters × groups)', 'χ² = Σ (O − E)² / E over the cluster × group table, df = (k − 1)(groups − 1).', 'chi2_sf'),
    ]),
    ('Comparing groups (explore.html, explore.csv)', 'Each grouping: groups with ≥ 3 people; two groups → first vs second, more → each vs all the others.', [
        ('grouping, level, vs, area, key, label, n1, n0', 'Which comparison: grouping column, group, comparison group, measure (key = participants.csv column; inc_{ing} on the pizza; neg_/pos_{ing} named with strong feelings; field=value a choice), group sizes.', 'explore_grouping'),
        ('m1, m0', 'Medians (proportions for yes/no measures).', 'explore_grouping'),
        ('delta', 'Cliff\'s δ = [#(x<sub>i</sub> > y<sub>j</sub>) − #(x<sub>i</sub> &lt; y<sub>j</sub>)] / (n1 n0) over all group × comparison pairs. For yes/no measures = difference in proportions. For covariates: Spearman ρ (Pearson r of ranks, ties = mid-ranks).', 'cliff_delta'),
        ('p', 'Mann-Whitney: rank sum R of the group (mid-ranks), two-sided. Smaller group &lt; 8: permutation, (hits + 1) / 4001 with 4000 random relabellings. Else normal approximation with tie correction and 0.5 continuity correction. Spearman: t = ρ √((n − 2) / (1 − ρ²)), df = n − 2.', 'mw_p'),
        ('q', 'Benjamini-Hochberg within the grouping: q<sub>(i)</sub> = min<sub>j ≥ i</sub> p<sub>(j)</sub> m / j.', 'bh'),
        ('(95% CI)', 'Percentile bootstrap of δ, 600 resamples within each group.', 'boot_ci'),
        ('n_per_group_80, n_per_group_80_half', 'People per group a new two-group study needs for 80% power at α = .05 (two-sided Mann-Whitney) if the true δ equals the observed / half the observed δ (Noether): n = 2 (z<sub>.975</sub> + z<sub>.80</sub>)² / (3 δ²). For covariate rows (ρ): total n = ((z<sub>.975</sub> + z<sub>.80</sub>) / atanh ρ)² + 3.', 'n_per_group'),
        ('(against chance)', 'Rows with grouping = chance: one group against a chance level (e.g. mirror_score 0, sweep_consistency 0.5, clark_evans 1). delta = dominance = (#above − #below) / n; m1 = median, m0 = chance; p = sign-flip permutation of the differences from chance, (hits + 1) / 4001; q = BH over all chance rows.', 'chance_test'),
    ]),
]


def code_ref(fn):
    """'analyse.py:123 name()' for a function in analyse.py (line numbers are read from the code itself)."""
    obj = getattr(A, fn, None)
    if obj is None:
        raise KeyError('methods.py names a function analyse.py does not have: %s' % fn)
    return 'analyse.py:%d %s()' % (inspect.getsourcelines(obj)[1], fn)


def column_patterns():
    pats = []
    for _, _, rows in SECTIONS:
        for cols, _, _ in rows:
            for c in cols.split(','):
                c = c.strip()
                if c.startswith('('):
                    continue
                rx = re.escape(c)
                for k, v in SLOTS.items():
                    rx = rx.replace(re.escape('{%s}' % k), '(?:%s)' % v)
                pats.append(re.compile('^%s$' % rx))
    return pats


def describe(column, file=None):
    """(section, plain-text description) of a column from this page, or (None, None). Entries that name the file
    (in the section title or the text) are preferred, so a column shared by several files gets that file's meaning."""
    entries = [(title, cols, how) for title, _, rows in SECTIONS for cols, how, _ in rows]
    if file:
        entries.sort(key=lambda e: file not in e[0] + e[2])        # stable: the file's own entries first
    for title, cols, how in entries:
        if True:
            pats = []
            for c in cols.split(','):
                c = c.strip()
                if c.startswith('('):
                    continue
                rx = re.escape(c)
                for k, v in SLOTS.items():
                    rx = rx.replace(re.escape('{%s}' % k), '(?:%s)' % v)
                pats.append(re.compile('^%s$' % rx))
            if any(p.match(column) for p in pats):
                text = re.sub(r'<sub>(.*?)</sub>', r'_\1', how)
                text = re.sub(r'<sup>(.*?)</sup>', r'^\1', text)
                text = re.sub(r'<[^>]+>', '', text).replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
                return title, text
    return None, None


def undocumented(columns):
    """Columns that no entry on this page describes (the smoke test requires none)."""
    pats = column_patterns()
    return [c for c in columns if not any(p.match(c) for p in pats)]


# ------------------------------------------------------------------ worked examples (computed by the real code)

def P(ing, x, y, s=1.0):
    return {'ing': ing, 'x': x, 'y': y, 'rot': 0, 's': s, 'g': 1}


def example_pizzas():
    """Three small pizzas for the symmetry examples: mirrored at 37 degrees by hand, the same with three pieces
    moved, and a random scatter of the same pieces."""
    R = random.Random(11)
    a = math.radians(37)
    base = [('pep', .5, .3), ('pep', .25, .62), ('mus', .55, -.05), ('oli', .2, .2), ('oli', .7, .45)]
    pz = []
    for ing, u, v in base:
        x, y = u * math.cos(a) - v * math.sin(a), u * math.sin(a) + v * math.cos(a)   # one side of the 37 degree axis
        mx, my = A.mirror(a)(x, y)
        pz += [P(ing, x + R.gauss(0, .012), y + R.gauss(0, .012)), P(ing, mx + R.gauss(0, .012), my + R.gauss(0, .012))]
    moved = [dict(p) for p in pz]
    for i, (dx, dy) in zip((1, 4, 9), ((.25, -.2), (-.3, .1), (.1, .3))):
        moved[i]['x'] += dx; moved[i]['y'] += dy
    rnd = [dict(p, x=r * math.cos(t), y=r * math.sin(t)) for p, r, t in
           ((p, .85 * math.sqrt(R.random()), R.random() * 2 * math.pi) for p in pz)]
    return [('Mirrored by hand, axis at 37°', pz), ('The same pizza with three pieces moved', moved), ('The same pieces scattered at random', rnd)]


def symmetry_examples():
    out = []
    for title, pz in example_pizzas():
        r = A.symmetry(pz, random.Random(1))
        n = len(pz)
        m = round(r['mirror_match'] * n)
        ch = r['mirror_chance']
        share = m / n
        hand = (share - ch) / (1 - ch) if share >= ch else (share - ch) / ch       # the formula, by hand
        assert abs(hand - r['mirror_score']) < 1e-9, 'mirror_score does not follow its formula'
        _, pairs = A.sym_match(pz, A.mirror_about(r['mirror_cx'], r['mirror_cy'], math.radians(r['mirror_axis_deg'])))
        assert len(pairs) == m
        for i, j, d in pairs:          # every match is the same topping, within tolerance
            assert pz[i]['ing'] == pz[j]['ing'] and d <= 0.5 * (A.piece_radius(pz[i]) + A.piece_radius(pz[j])) + 1e-12
        old = old_mirror_ratio(pz)
        calc = ('(%d/%d − %.2f) / (1 − %.2f) = <b>%.2f</b>' % (m, n, ch, ch, r['mirror_score']) if share >= ch
                else '(%d/%d − %.2f) / %.2f = <b>%.2f</b>' % (m, n, ch, ch, r['mirror_score']))
        out.append('<div class="ex"><div class="pic">%s</div><div><b>%s</b><table class="calc">'
                   '<tr><td>matched (green rings)</td><td>%d of %d = %.0f%%</td></tr>'
                   '<tr><td>chance (12 random layouts)</td><td>%.0f%%</td></tr>'
                   '<tr><td>mirror_score</td><td>%s</td></tr>'
                   '<tr><td>axis</td><td>%.2f°</td></tr>'
                   '<tr class="old"><td>old ratio (until 2026-10-26)</td><td>%.2f (0 = perfect, 1 = random)</td></tr></table></div></div>'
                   % (A.mirror_panel(pz, r), title, m, n, 100 * share, 100 * ch, calc, r['mirror_axis_deg'], old))
    return ''.join(out)


def old_mirror_ratio(pz):
    """The previous definition, kept here only to show the difference: mean distance from each reflected piece to the
    nearest piece of the same topping, best of 18 axes 10 degrees apart through the centre, / the same for 40 random layouts."""
    def cost(ps, T):
        tot = 0.0
        for p in ps:
            tx, ty = T(p['x'], p['y'])
            tot += min(math.hypot(tx - q['x'], ty - q['y']) for q in ps if q['ing'] == p['ing'])
        return tot / len(ps)
    axes = [math.radians(a) for a in range(0, 180, 10)]
    rnd = random.Random(2)
    obs = min(cost(pz, A.mirror(a)) for a in axes)
    null = [min(cost([dict(p, x=r * math.cos(t), y=r * math.sin(t)) for p, r, t in
                      ((p, .9 * math.sqrt(rnd.random()), rnd.random() * 2 * math.pi) for p in pz)], A.mirror(a)) for a in axes) for _ in range(40)]
    return obs / (sum(null) / len(null))


def small_examples():
    rows = []
    counts = [6, 3, 1]
    h = A.shannon(counts)
    hand = -sum(c / 10 * math.log(c / 10) for c in counts)
    assert abs(h - hand) < 1e-12
    rows.append(('shannon', '6 pepperoni, 3 mushrooms, 1 olive', '−(0.6 ln 0.6 + 0.3 ln 0.3 + 0.1 ln 0.1) = <b>%.3f</b>' % h))
    x, y = [3, 5, 7], [1, 4, 4, 6]
    d = A.cliff_delta(x, y)
    gt = sum(a > b for a in x for b in y)
    lt = sum(a < b for a in x for b in y)
    assert abs(d - (gt - lt) / (len(x) * len(y))) < 1e-12
    rows.append(("Cliff's δ", 'group 3, 5, 7 vs comparison 1, 4, 4, 6', '(%d higher − %d lower) / (3 × 4) = <b>%.3f</b>' % (gt, lt, d)))
    ps = [0.001, 0.02, 0.03, 0.2]
    q = A.bh(ps)
    hand = [min(min(ps[j] * 4 / (j + 1) for j in range(i, 4)), 1) for i in range(4)]
    assert all(abs(a - b) < 1e-12 for a, b in zip(q, hand))
    nn = A.n_per_group(0.5)
    assert nn == math.ceil(2 * (1.959964 + 0.841621) ** 2 / (3 * 0.25))
    rows.append(('n_per_group_80', 'δ = 0.5', '2 × (1.960 + 0.842)² / (3 × 0.5²) = 20.9 → <b>%d</b> per group' % nn))
    ev = [[0, 'start', ''], [10, 'add', 'pep', 1, .1, .1], [20, 'add', 'mus', 2, -.2, .3], [30, 'add', 'oli', 3, .4, 0], [40, 'remove', 'mus', 2, .9, .9],
          [50, 'clear', 2, '1 3'], [60, 'undo', 'clear', 2, '1 3'], [70, 'remove', 'oli', 3, -.95, .5], [80, 'done'], [90, 'finish']]
    acts, _, rem = A.action_measures(ev, [[1, 'pep', .1, .1, 0, 1, 0, 1, 1]])
    assert (acts['n_added_pieces'], acts['n_removed_pieces'], acts['n_restored'], acts['dropped_list'], acts['replay_matches_final']) == (3, 2, 2, 'mus oli', 1)
    rows.append(('changes of mind', 'add pepperoni, mushroom, olive; drag the mushroom off; Start over; Undo (pepperoni and olive return); drag the olive off',
                 'removed and not restored: mushroom, olive = <b>%d</b> of %d added (Start over undone: %d restored); dropped: %s; revision_rate = <b>%.2f</b>'
                 % (acts['n_removed_pieces'], acts['n_added_pieces'], acts['n_restored'], acts['dropped_list'], acts['revision_rate'])))
    tom = A.NUTRITION['toppings']['tom']
    sizes = [(0.5, 'small (half size)'), (1.0, 'standard'), (2.0, 'big (double size)')]
    calc = []
    for sz, word in sizes:
        g = A.piece_grams({'ing': 'tom', 's': sz})
        assert abs(g - tom['grams'] * sz * sz) < 1e-12
        calc.append('%s: %g g × %g² = <b>%g g</b> → %.1f kcal, %.1f mg vitamin C' % (word, tom['grams'], sz, g, g * tom['per100']['kcal'] / 100, g * tom['per100']['vitC'] / 100))
    rows.append(('grams (size)', 'one tomato slice (USDA %s, %g kcal and %g mg vitamin C per 100 g; standard slice %g g)' % (tom['ndb'], tom['per100']['kcal'], tom['per100']['vitC'], tom['grams']),
                 '<br>'.join(calc)))
    # adjustments: three pairs mirrored about the vertical axis; one piece is first dropped off its mirror spot, then moved onto it
    ev = [[0, 'start', ''], [10, 'add', 'pep', 1, -.4, .3, 0, 0, 1], [20, 'add', 'pep', 2, .4, .3, 0, 0, 1], [30, 'add', 'mus', 3, -.3, -.3, 0, 0, 1],
          [40, 'add', 'mus', 4, .5, -.1, 0, 0, 1], [50, 'add', 'oli', 5, 0, 0, 0, 0, 1], [60, 'move', 'mus', 4, .3, -.3, 300, 0, 1], [70, 'done'], [80, 'finish']]
    final = [[1, 'pep', -.4, .3, 0, 1, 0, 1, 1], [2, 'pep', .4, .3, 0, 1, 0, 2, 1], [3, 'mus', -.3, -.3, 0, 1, 0, 3, 1], [4, 'mus', .3, -.3, 0, 1, 0, 4, 1], [5, 'oli', 0, 0, 0, 1, 0, 5, 1]]
    pcs = [{'ing': f[1], 'x': f[2], 'y': f[3], 'rot': 0, 's': 1, 'g': 1} for f in final]
    rec = A.symmetry(pcs, random.Random(1))
    adj, arows = A.adjustment_measures(ev, final, rec, random.Random(2))
    mv = arows[0]
    assert mv['reason'] == 'symmetry' and mv['sym_gain_mirror'] == 2 and adj['n_adj_symmetry'] == 1
    rows.append(('adjustment reason', 'pepperoni and olive placed symmetrically; mushrooms at (−0.3, −0.3) and (0.5, −0.1); the second mushroom moved to (0.3, −0.3)',
                 'final best axis %.0f°: matched pieces before %d → after %d, sym_gain = <b>%+d</b> → reason <b>%s</b>; by chance %d of 12 random moves of that length gain (sym_chance %.2f)'
                 % (rec['mirror_axis_deg'], round(rec['mirror_match'] * 5) - mv['sym_gain_mirror'], round(rec['mirror_match'] * 5), mv['sym_gain'], mv['reason'], round(mv['sym_chance'] * 12), mv['sym_chance'])))
    rows.append(('q (BH)', 'p = 0.001, 0.02, 0.03, 0.2', 'q = ' + ', '.join('%.3g' % v for v in q)))
    ref = [frozenset('a'), frozenset('ab'), frozenset('b'), frozenset('a')]
    bits, _ = A.atypicality(frozenset('b'), ref, ['a', 'b'])
    ra, rb = (3 + .5) / 5, (2 + .5) / 5
    assert abs(bits - (-math.log2(1 - ra) - math.log2(rb))) < 1e-12
    rows.append(('atypicality_bits', 'pizza {b}; reference {a}, {a,b}, {b}, {a}', 'r<sub>a</sub> = 3.5/5, r<sub>b</sub> = 2.5/5: −log<sub>2</sub>(1 − 0.7) − log<sub>2</sub>(0.5) = <b>%.3f</b>' % bits))
    pts = [(0, 0), (0.5, 0), (0, 0.5), (-0.5, -0.5)]
    ce = A.clark_evans(pts)
    E = 0.5 * math.sqrt(math.pi * 0.81 / 4) + (0.0514 + 0.041 / 2) * 2 * math.pi * 0.9 / 4
    nn = sum(min(math.hypot(px - qx, py - qy) for qx, qy in pts if (qx, qy) != (px, py)) for px, py in pts) / 4
    assert abs(ce - nn / E) < 1e-12
    rows.append(('clark_evans', 'pieces at (0,0), (0.5,0), (0,0.5), (−0.5,−0.5)', 'mean NN %.3f / E %.3f = <b>%.3f</b>' % (nn, E, ce)))
    return ''.join('<tr><td><code>%s</code></td><td>%s</td><td>%s</td></tr>' % r for r in rows)


def version():
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        sha = subprocess.run(['git', 'log', '-1', '--format=commit %h (%cs)', '--', '.'], cwd=here, capture_output=True, text=True, timeout=5).stdout.strip()
        if sha and subprocess.run(['git', 'status', '--porcelain', '--', '.'], cwd=here, capture_output=True, text=True, timeout=5).stdout.strip():
            sha += ' with uncommitted changes'
    except (OSError, subprocess.SubprocessError):
        sha = ''
    return sha or 'analysis code of %s' % time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(os.path.join(here, 'analyse.py'))))


CSS = """
.sec { margin: 22px 0 6px; } .sec + p { margin-top: 0; }
table.m { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 13.5px; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
table.m td { padding: 6px 10px; border-top: 1px solid var(--line); vertical-align: top; }
table.m td.c { width: 26%; font: 12.5px/1.45 ui-monospace, Menlo, Consolas, monospace; word-break: break-word; }
table.m td.r { width: 21%; color: var(--muted); font: 11.5px ui-monospace, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
.ex { display: grid; grid-template-columns: 240px 1fr; gap: 14px; align-items: center; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 10px 14px; margin-bottom: 10px; }
.ex .pic svg { width: 240px; height: 240px; display: block; }
table.calc td { padding: 3px 12px 3px 0; font-variant-numeric: tabular-nums; } table.calc tr.old td { color: var(--muted); }
.note { color: var(--muted); font-size: 13px; }
"""


def build_page():
    secs = []
    for title, intro, rows in SECTIONS:
        body = ''.join('<tr><td class="c">%s</td><td>%s</td><td class="r">%s</td></tr>' % (A.esc(cols), how, code_ref(fn)) for cols, how, fn in rows)
        secs.append('<h2 class="sec">%s</h2>%s<table class="m">%s</table>' % (A.esc(title), '<p class="note">%s</p>' % intro if intro else '', body))
        if title == 'Symmetry':
            secs.append('<div style="margin-top:10px">%s</div><p class="note">Rings: where each piece\'s mirror image falls. Green = a piece of the same topping is '
                        'there (matched), red = not. The old ratio missed axes between its 10° steps, so a perfectly mirrored pizza scored well above 0 '
                        'unless its axis happened to be a multiple of 10°.</p>' % symmetry_examples())
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Pizza Methods</title><style>%s%s</style></head><body><div class="wrap"><h1>Methods: how every number is counted</h1>'
            '<p class="muted">Pizza coordinates: centre (0, 0), crust edge at radius 1 (= 15 cm), y up; 1 drawing unit = 1.5 mm. n = pieces on the pizza. '
            'Each row names the function in <code>analysis/analyse.py</code> that computes it. Built from %s on %s.</p>%s'
            '<h2 class="sec">Worked examples</h2><p class="note">Computed by the code above while this page was built, and checked against the hand calculation shown.</p>'
            '<table class="m"><tr><td class="c"><b>measure</b></td><td><b>input</b></td><td><b>calculation</b></td></tr>%s</table>'
            '</div></body></html>' % (A.REPORT_CSS, CSS, A.esc(version()), time.strftime('%Y-%m-%d %H:%M'), ''.join(secs), small_examples()))


def write(path):
    html = build_page()
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path


if __name__ == '__main__':
    print(write(sys.argv[1] if len(sys.argv) > 1 else 'methods.html'))
