# A crossing keeps its real floor (band 0), so its street is drawn over it

**Status:** implemented 2026-10-04 (Kaveh: a footway never over a driving road, "yes"; sidewalks: "real floor"). Changed in duckOSM (`levels.py`, `docs/design/levels.md`, its test) and in
mapstyle (`_band`, its test, the docs below). Verified: on all 12,941 edges of Monaco the two bands agree. A stored table made before must be made again.

## What the words mean

- **Band** = the floor a road is on. From the OSM tags: the `layer`, else a bridge 1, a tunnel −1, else 0 (ground). It is an input of roadstyle's solver.
  A road in a higher band is painted over a road in a lower band (a firm rule, for roads of 10 m or more).
- **Fill number** = the exact painting order roadstyle calculates from the bands and other rules: a higher number is painted later, so it shows on top. It is what
  `visualization.edge_levels` stores.
- Between roads on the **same band** that meet at a node, roadstyle only has a soft wish: the **class order** (`order="class"`): a street over the footway that ends at it.

## Problem

Kaveh: *a footway must not be drawn over a driving road, even a crossing; only the zebra marking comes over the road.*

Today a crossing is **not** on its real floor. A crossing edge (`walk_type = 'crossing'`, a footway across a street) is on the ground, but duckOSM (`levels.py`:
`_BAND_OF_WALK_TYPE = {"sidewalk": -1, "crossing": 1}`) and mapstyle (`map.py`, `_band`) force it to **band 1**, "over its street". The solver then paints it over the street.

Monaco, `duckOSM/monaco.duckdb`, 1,266 crossing edges that meet a street. For each, its fill number against the highest fill number of the streets it crosses
(measured with roadstyle's solver on duckOSM's own roads, nothing written):

| | on top of the street | undecided (same number) | under the street |
|---|---|---|---|
| band 1 (today) | 170 | 540 | 556 |
| band 0, the class order decides | 2 | 10 | 1,254 |

The 170 are crossings the solver does stack (92 % are 10 m or longer, the length from which a road can be stacked; none has a bridge tag): ordinary crossings drawn over a driving road. The 540 are left to chance.
With band 0 nothing says the crossing is higher; the class order puts the street (a higher class) over the footway: 99 % under the street, none given up (0 pairs) in both runs.

## Proposal

1. A crossing has the band of its tags (the `layer`, bridge, tunnel; ground 0 on a plain street). Remove `"crossing": 1` from `_BAND_OF_WALK_TYPE` (duckOSM `levels.py`, line 15) and from `_band`
   (mapstyle `map.py`, lines 441-442), so the two stay the same: the stored numbers come from duckOSM's band, and mapstyle's band is what roadstyle computes from when there is no table.
2. A **sidewalk** has its real floor too (Kaveh), not −1.
3. The zebra **marking** is the icon: it is already drawn at the level of its street, over the street's fill ([edge_features.md](edge_features.md)). Nothing to change there.
4. Docs and tests that say "crossings over their street": duckOSM `docs/design/levels.md` (line 52), mapstyle `README.md`, `AGENTS.md`, `docs/design/stored_levels.md` ("The band"), `docs/design/mode_styles.md`
   ("Order at junctions"), `test_the_band_is_complete` (a crossing's band is the one of its tags), the `pieces=True` band (`map.py`, line 539: the older approach, to be decided).
5. A test that needs `duckosm levels`: on Monaco at least 99 % of the crossing edges have a fill number not above their street's (skipped when `duckosm` is not available).

## The conflict to decide first

On 2026-09-30 Kaveh chose the opposite for the look at junctions (`mode_styles.md`, "Order at junctions"): *a crossing (the zebra) draws entirely over the street and a sidewalk entirely under it,
casings included*, so that a path's halo does not vanish under the road it crosses. With band 0 the crossing's outline is under the street, as for every other path ("a street over the path ending at it",
as openstreetmap-carto does). Decide: keep that look, or "a footway never over a driving road".

## Cost and risk

- **Every stored table must be made again.** `duckosm levels` must be run again on each db: the edges are the same, so the reader's edge check **passes** and mapstyle would silently draw the old
  numbers. Only the band changed, and the table records `band_source = 'band'` and not the rule. A proposal for duckOSM: store a `band_rule` version in `edge_levels_meta`, and mapstyle refuses a
  table of another version.
- Not checked: the junction heads and the sidewalks after the change (only the crossing edges were measured); the number of positions (`levels_info`); Tartu and Södermalm (only Monaco).
- The `edge_attach` rule of [edge_features.md](edge_features.md) does not depend on this: it takes the street, not the crossing edge. After the change the fill-number tie-break it uses (`fill_level`) still holds.

## Open points

1. Decided: the 2026-09-30 look is replaced (a footway never over a driving road). Sidewalks too: their real floor.
2. Not measured after the change: the sidewalks (they were −1) and the junction heads; run `duckosm levels` on Monaco and look.
3. A crossing on a real bridge or in a tunnel keeps the band of its tags (1 or −1), as every road does. Not tested.
