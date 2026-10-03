# The drawing order of the roads

`render_map(order=True)` (the default) decides, for every road, **when its casing and when its fill are drawn**, so that
roads at different levels (bridges, tunnels, ramps, raised paths) join cleanly and an overpass is drawn over the road
it crosses. The code is `src/mapstyle/node_levels.py`; the page is drawn by roadstyle's `casing_level_col` /
`fill_level_col`.

## The problem

A road is drawn as a casing (the outline) and a fill. If all casings of a layer come before all fills, two roads that
meet at a junction merge cleanly. But a road that goes over another one (a bridge) must be drawn after it, casing
included, and its ramp must still merge with the ground roads it is joined to. One layer per level cannot do both:
a joint between two layers shows a ring.

## The model

Every road gets an interval `[a, b]` of integers in `[-20, 20]`: `a` is the position where its casing is drawn,
`b` the position where its fill is drawn. At each position all casings come before all fills. Both directions of a
segment are one road.

- **Roads that share a node** have intersecting intervals. Their casings and fills then interleave, so they merge.
- **An overpass** is a pair of roads whose lines cross, with no node in common and different levels (the `layer` tag;
  else bridge = 1, tunnel = -1, else 0). Their intervals are disjoint and the upper road's is later: it is drawn over
  the lower road, with its own casing.
- Same-level crossings are not in the model.

## How it is solved

1. **Candidates:** a grid on the roads' boxes, then the exact test (`ST_Crosses`), give the overpass pairs.
2. **Only the roads near an overpass are in the problem** (within 4 nodes of an overpass road). Every other road is
   `[0, 0]`. Roads at the border of the problem must contain 0.
3. **Solver:** OR-Tools CP-SAT minimises the number of overpass pairs it must give up. A heuristic (a level per node from
   the crossings) starts it, and is used alone when OR-Tools is not installed (`pip install mapstyle[solver]`).
4. **Pairs still given up** are examined:
   - a crossing within 0.3 m of an end node of either road is a junction missing a node, not an overpass: the pair is dropped;
   - otherwise the lower road, if it is joined to a road whose level differs by 2 or more, is cut at its crossing with
     the upper road. The piece next to the node stays.
5. The intervals are compacted and doubled, so crossings sit at +1 and sidewalks at -1, between the positions.

Monaco: 561 overpass pairs, 3 given up and fixed as in step 4, about 5 s. The county of Stockholm: 11 s.

## In the page

`render_map` gives roadstyle two columns, `_cl` (casing position) and `_fl` (fill position). roadstyle draws one casing
layer and one fill layer per position, in order. A road that was cut keeps its row; its other pieces are extra rows
marked `_piece` (the dashboard counts skip them).

## Limits

- `tiles=True` is not supported: roadstyle's bands are used and a warning is logged.
- Pairs that share a node and also cross, and roads that only overlap in width without crossing, are not constrained.
- The result is optimal, but the solver runs with several workers, so the intervals can differ between runs.

`render_map(order=False)` draws with roadstyle's bands; `pieces=True, order=False` is the older way, cutting every road
with a level into pieces (`levels_plan.md`).
