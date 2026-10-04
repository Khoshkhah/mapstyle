# The drawing order from roadstyle

**Status:** implemented. Replaces the old `node_levels` design (mapstyle's own solver, deleted).

Every road is drawn with a **casing number** (in three parts: start, main, end) and a **fill number**: the casings and fills are painted number by number,
lowest first, and at each number all casings come before all fills. mapstyle used to compute these numbers itself (`node_levels.py`: one interval per road,
OR-Tools or a heuristic). roadstyle now computes them (`compute_levels`, roadstyle 0.13.1) with a model that has the heads of a casing, stacks and the class order, and
duckOSM can store them in the file (`duckosm levels`, schema `visualization`). So mapstyle stops solving: it **reads the stored numbers, or lets roadstyle compute them**, and draws.

## What changes

`render_map` (the drawing order is always roadstyle's; the argument `order` is removed):

1. The roads get the **band** (below, on, or over the ground) that roadstyle needs, in the column `band` (see below).
2. **The numbers.**
   - If the file has `visualization.edge_levels`, they are read with `roadstyle.load_levels(con, roads, band_col="band", order="class")`. The reader checks that the options and the edges are those the numbers were computed for.
     If they are not (the file was rebuilt, or `duckosm levels` was run with other options), `render_map` stops with the reader's message and says: run `duckosm levels` again. It never recomputes silently.
   - If the file has no such table, roadstyle computes them while it renders (`render_edges` with `band_col="band"`, its defaults). They are not stored: mapstyle only reads the file.
3. The page is drawn with `casing_level_col`, `fill_level_col`, `casing_start_col`, `casing_end_col` and `head_m` (the stored one), roadstyle's columns for numbers.
4. `tiles=True` works with the numbers (roadstyle 0.13 puts them in the tiles), so the warning "the drawing order is not supported with vector tiles" goes.

## The band

The band is an input of the optimization, and roadstyle's `band_col` **replaces** the level from the tags: a road with no value in it is band 0. So the column must be complete.
It is the same as duckOSM's (`duckosm.levels.load_roads`), so that the stored numbers and mapstyle's agree:

- the level from the tags: the OSM `layer` if that is a number, else 1 for a bridge, −1 for a tunnel, else 0;
- except for a path (`footway`, `path`, `cycleway`, `steps`, `pedestrian`, `bridleway`, `corridor`) with a `walk_type`: a `sidewalk` is −1 (under its street) and a `crossing` is 1 (over it).

**This is a fix.** mapstyle passed `_band` with values only for sidewalks and crossings and nulls for every other road, so wherever roadstyle computed the numbers (`tiles=True`, `order=False`),
tunnels, bridges and layers were band 0. On Monaco roadstyle then saw only the bands −1, 0, 1 instead of −4 to 3.

## What is removed

- `src/mapstyle/node_levels.py`, with its OR-Tools / heuristic solver, and `with_cuts`; the argument `order`; `docs/design/node_levels.md`; the prototype scripts `scripts/node_levels*.py`; their tests; the `solver` extra.
  A road is no longer cut at the place where it passes over another road: roadstyle gives a road one fill number and a casing in three parts. A change of level in the middle of a long road is not followed
  (roadstyle's design, section 13, point 2).
- `render_map(..., order=...)` is refused with a message, not ignored.
- Not removed: `pieces=True` (the older approach, `levels.py`), which is not the default.

## What stays

`load_roads` (one row per `edge_id` over the modes, with the flags and `walk_type`), the styles, themes, layers, planner and dashboard. The roads' geometry and `edge_id` are what duckOSM wrote.

## Dependencies

roadstyle 0.14.0 or later (it brings the solver, the stored-numbers reader, and arrows and street names that follow the roads' filters). The stored numbers need duckOSM 0.2.0 or later (`duckosm levels`); without them nothing else is needed.

## Tests

- The band: complete (tunnels, bridges, layers, sidewalks, crossings), the same as duckOSM's on the Monaco sample.
- A file with the table: the page is drawn with the stored numbers; a table that does not match (other options, other edges) is an error that names `duckosm levels`.
- A file without the table: the page is drawn with the numbers roadstyle computes.
- `tiles=True`; `pieces=True` still renders; `order=` is refused.

## Open points

1. A road that changes level in the middle (a ramp that starts on the ground and rises over a street) gets one level for the whole road: roadstyle's model gives a road one fill number and a casing in three parts, and mapstyle no longer cuts roads where they pass over another.
2. A file computed with `--no-min-positions` is refused by the reader (the options differ); `render_map` has no option to read it.
