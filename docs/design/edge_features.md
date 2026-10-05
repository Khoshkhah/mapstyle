# Points on a road are drawn at their road's level

**Status:** implemented 2026-10-04 (Kaveh: "when do you want to implement them?"), after the roads-as-overlays experiment
([roads_as_overlays.md](roads_as_overlays.md)). Crossings and traffic signals only.

## Problem

The crossing and signal layers were plain "over" overlays: drawn above every road, whatever the road's level. A crossing on a bridge
showed over the street under the bridge; a signal in a tunnel showed over the roads above it.

## What changes

roadstyle's edge-attached overlays (`Overlay(edge_col="edge_id")`) draw a feature at the place of its edge in the drawing order: over that
edge's fill, under every road above it. So each crossing and signal gets an `edge_id`, and its overlay is attached to edges.

1. `edge_attach(fcs, roads)` (`map.py`) puts `edge_id` (text: it can pass 2**53) on every feature of the layers in `EDGE_ATTACHED`
   (`crossings`, `traffic_signals`). It runs in `render_map` before the overlays are built, not with `pieces=True` (the pieces' ids are
   not the roads').
2. `feature_overlays(..., edge_attached=names)` builds those overlays with `edge_col="edge_id"`. roadstyle then makes one map layer for each
   `(fill number, order)` that occurs, and puts each between the fills of its position and its arrows.
3. `layers.js` made the icon layer (a symbol layer on top of the map) and hid the circle. Now it makes **one icon layer for each circle layer**, right after
   it and with its filter, so the icon sits at the same level. A plain overlay (one layer) is built as before. `bodies` is the list of an overlay's body layers
   (the circles, not a polygon's outline); the interaction code sets the colour on all of them.

## Which edge: the street, not the crossing's own edge

The first idea was the crossing's own edge (`walk_type = 'crossing'`). It is wrong: a footway, a crossing included, must not be drawn over a driving road
(Kaveh); only the zebra, the marking, is over the street. In Monaco duckOSM's levels (`duckosm levels`) put 562 of the 1,292 crossing edges **below** the street they cross, 534 at the same
fill number and 170 above (all 562 below are shorter than 10 m, 2 x `head_m`: the model never stacks a short road over another road, `short_upper_pairs`). An icon at the level of its crossing
edge is hidden under the street in the 562: two zebras of the test view were gone.

So the point takes the **street** it is on (a class that is not a path), and the street's level puts the icon right over the street's own fill:

1. the streets within about 1 m of the point; of them the one drawn on top: the highest `fill_level` (the stored levels, read before the overlays), then the highest band,
   then the highest class (a link as its parent). A street the point overlaps cannot cover it;
2. else the nearest street within about 3 m (a signal stands beside its road; at equal distance the one drawn on top);
3. else the nearest road (a point on a footpath only).

Not matched by a node id: 412 of 553 crossings are the start or end node of a walking edge, but the node says nothing about the street's level, and GMNS
has only 2 of the 22 signals and 82 of the 553 crossings as nodes. Geometry works for every point.

## Checked (Monaco, `duckOSM/monaco.duckdb`)

- Every one of the 553 crossings and 22 signals gets the `edge_id` of a road of the page. Attached fill numbers: crossings -1 to 4, signals 1 to 4.
- At zoom 18 in the test view, the page looks like the one before (screenshots diffed): the zebras on the yellow road and on the slip road show; the only
  differences left are street-name labels roadstyle places differently on every load.
- 96 of the 553 crossings have a road drawn above their edge within 1 m; every one of those is a footpath (mostly the crossing's own thin edge), none a street.
- No page error; the other point layers (parking, bus stops, ...) keep their one icon layer on top as before. The page has 152 layers, against 136.
- Tests: `test_a_point_on_a_road_gets_the_street_it_is_on` (the rules, on a built table), `test_crossings_and_signals_are_drawn_at_their_roads_level` (the page).

## Not done

- Not measured: the file size and the frame rate of the page (16 more layers: 152 against 136, and an `edge_id` on 575 features); the icon layers were not compared on a GPU.
- A point beside a road drawn from a tunnel above another road: the nearest street is taken, which may be the lower one; no such case was seen in Monaco.
- Other point layers (bus stops, bicycle rental) are still plain "over" overlays: they are not on a road in the data (they stand beside it).
- The `edge_id` is computed when the page is built (about 0.1 s for Monaco), not stored in duckOSM's `features.*`. If duckOSM wrote it, mapstyle would read it instead.
