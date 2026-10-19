# A map of one mode: its roads and its private roads only

**Status:** approved by Kaveh and implemented 2026-10-19 (`only=True`, `--only`, the Pedestrian and Delivery rows). `duckosm viz` makes its per-mode pages with it. Norrmalm driving page: 4.1 MB (was 5.5 MB).

## Problem

`render_map(db, mode="driving")` draws the roads of every mode. `mode` only decides which network
stands out. The driving page and the all-modes page hold the same roads, and every page is 5.5 MB
for Norrmalm. A driving map shows walking paths and cycleways too.

Kaveh wants a driving map with only two sources: `driving.edges` and `driving.private_edges`.

## Design

- `load_roads(db, modes=None)` takes an optional list of modes. With a list, `_roads_union` stacks
  only `<mode>.edges` and `<mode>.private_edges` for those modes. Without it, nothing changes.
- `render_map(db, mode="driving", only=True)` calls `load_roads(db, [mode])`. `only` is False by
  default, so a page made today is the same.
- With `only=True`, a road has the access label of that mode. These are the values in
  `private_edges.access` (duckOSM design `pedestrian_private_edges.md`):

  | `access` | Row in the Roads box | Colour |
  |---|---|---|
  | `private` | Private roads (as today) | `#c8c8c8` |
  | `bus` | Bus lanes (as today) | `#9db8d9` |
  | `pedestrian` | Pedestrian streets (new) | `#dddde8` (the pedestrian fill of the OSM style) |
  | `delivery` | Delivery only (new, only if the table has the value) | `#e8d2b0` |

  A row shows only when the map has roads of that value. It hides and shows them, as the other
  rows do. The code is in `layers.js`. roadstyle does not change.
- The CLI gets `--only` (`mapstyle db.duckdb --mode driving --only`).
- The features layers (water, land, buildings) do not change.
- The all-modes page does not change. It gets the same new rows when its db has these labels.

## Effect

- A driving page has no walking and no cycling edges. Its file is smaller. (To measure on Norrmalm.)
- A road is not in two modes on this page, so the `access_<mode>` columns have one used column.
- The planner and the dashboard need all modes. `only=True` with `planner` or `dashboard` raises an
  error.

## Test

- Norrmalm `--only` driving: the edge ids on the page are the ids of `driving.edges` and
  `driving.private_edges`. No other id is on the page.
- Without `--only`, the page is the same as before the change.
- The Pedestrian row appears only when the db has `access = 'pedestrian'` edges.
