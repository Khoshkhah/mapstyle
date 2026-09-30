# The route planner moves into mapstyle

**Status:** approved 2026-09-30 and implemented (`render_map(planner=True)`, `mapstyle --planner`,
`src/mapstyle/planner.html` ported from duckOSM commit `dbbbe3e`). **roadstyle and duckOSM are not
changed.**

## Today

`duckosm route-map db` (duckOSM, `src/duckosm/route_map.py`, 394 lines; design:
`../duckOSM/docs/design/route_map.md`) writes one page where you drag a start and an end marker and
see the route, with no server:

- **Python** reads the routing graphs from the db and embeds them as JSON (`const RM = …`): per mode
  the turn graph (`<mode>.edge_graph`, weight `cost_s` or `length_m`), and for walk + drive the
  `mm.edges` / `mm.transfers` tables (`duckosm multimodal`). Node ids are remapped to small
  integers (some pass 2**53).
- **JavaScript** (~250 lines) runs Dijkstra in the page, giving the same answers as duckOSM's
  `route()` / `route_multimodal()` (checked on Monaco: 8 of 8 trips); snaps each marker to the
  nearest road of the mode; draws the route by recolouring its roads per leg (`rsColor`); a side
  panel shows the mode menu (Drive, Walk, Cycle, Walk + drive), fastest / shortest, time, length,
  turn-by-turn directions (added in duckOSM on 2026-09-30, `a22b272`) and `edge_id`s.
- **The map** is roadstyle's `mono` palette on a raster base map. Walking legs are hard to see:
  footways are 1.2 px dashed lines, and `rsColor` keeps the class width (`mode_styles.md`).

Monaco: 0.9 MB of graphs (1.2 MB with walk + drive), a 3.2–3.5 MB page.

## Proposal

### 1. A flag on `render_map`, not a second function

```python
ms.render_map(db, planner=True)                 # the full map + the planner panel
ms.render_map(db, mode="cycling", planner=True) # the cycling look
```
```bash
mapstyle monaco.duckdb --planner                # -> monaco_walking.html
```

The planner page is the mapstyle page (mode style, feature layers, every roadstyle keyword) plus
the panel, so it is one flag, not the plan's separate `render_route_planner`. With `planner=True`
the default `mode` is **walking**: its style draws every path solid and ~3 px, so a walking leg is
as visible as a driving one. The mode menu in the panel still offers every mode the db has; `mode`
only picks the look (one page per look, as in `mode_styles.md`).

### 2. What moves, what changes

- The graph export moves to `map.py` (`planner_data`: the same SQL and JSON). The roads come from
  `load_roads` (all modes' edges) and carry a `k` property, their row index, which the graphs point
  to, as `route_map.py`'s own edge list does.
- The panel (HTML, CSS, JS) moves to one file, `src/mapstyle/planner.html`, injected before
  `</body>` like `layers.js`. The JS is unchanged (it already waits for the map by polling) but for
  one line: without the `mm` tables the panel says that Walk + drive needs `duckosm multimodal`.
- **Every mode:** Drive, Walk and Cycle whenever the db has their `edge_graph` (a normal build);
  Walk + drive when it has the `mm` tables. Those come from a separate `duckosm multimodal` run
  today; building them by default is a duckOSM change (PLAN step 3), not part of this move.
- `planner=True` with `tiles=True` is an error: snapping reads the roads from the page's inline
  source, which tiles replace.

### 3. duckOSM and route-viewer

- `duckosm route-map` keeps working as it is until PLAN step 3 makes duckOSM's `viz` / `route-map`
  call mapstyle; then `route_map.py` and its design note are deleted from duckOSM. Until then the
  code exists twice.
- route-viewer (turn-by-turn from the private route-guidance) is frozen on its last working
  mapstyle commit (PLAN step 4); the planner now has its own directions.
- While both copies exist, a change to duckOSM's planner is ported by re-extracting its panel
  (the `planner.html` header names the duckOSM commit it came from).

## Not in this note

Compressing the embedded graphs (the page's `RM` JSON is not gzipped the way roadstyle gzips its
sources; worth it once a city's graphs pass a few MB), real multimodal routing (bike-share,
parking, public transport: duckOSM's own list).

## Checks

- Tests: duckOSM's graph test ported (a small db whose node ids pass 2**53: the embedded graph
  matches `edge_graph`, node ids remapped); on Monaco the page embeds the three modes' graphs, and
  with `duckosm multimodal` run on a copy, the walk + drive graph; `planner=True, tiles=True` raises.
- In a browser: duckOSM's `scripts/route_map_stress.py` (random trips at zoom 13.5, 16, 17)
  ported to `scripts/planner_check.py`; a walking route along footways is visible (the
  `mode_styles.md` check left open).
