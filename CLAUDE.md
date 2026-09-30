# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Start at [`docs/PLAN.md`](docs/PLAN.md)** (the work plan) and
[`docs/design/full_map_library.md`](docs/design/full_map_library.md) (the approved design), then the
feature notes in `docs/design/`. The old deck.gl viewer is deleted; it is in git history (e.g.
`git show a53abd0:src/mapstyle/merge.py`).

- mapstyle = the full-map library on top of **roadstyle** (`../roadstyle`, read its `AGENTS.md`);
  its only input is a **duckOSM db** (`../duckOSM`), read with `duckdb`, never by importing duckOSM.
- **Don't change roadstyle** (Kaveh's rule): use its `settings=` / palettes, `overlays=`, JS API and
  the page's `window.map` from mapstyle.
- `edge_id` is a BIGINT content hash that can pass 2**53: JS calls take roadstyle feature ids
  (`rsQuery`), never `edge_id`.
- Design note first, sign-off, then code (Kaveh's rule for non-trivial features).

## Setup and commands

```bash
.venv/bin/pip install -e ../roadstyle        # .venv's roadstyle metadata is stale; do this first
.venv/bin/pip install -e '.[dev,tiles]'
.venv/bin/pytest                             # builds a Monaco db with ../duckOSM (~10 s) per session
MAPSTYLE_TEST_DB=monaco.duckdb .venv/bin/pytest tests/test_map.py::test_load_roads   # reuse a built db

.venv/bin/mapstyle ../duckOSM/data/db/tartu.duckdb --mode walking -o render/tartu.html   # render/ is gitignored
```

`../duckOSM/data/db/tartu.duckdb` has `features.*`; `sodermalm.duckdb` has none (the
missing-features case).

## What is where today

- `map.py` — the library; its `main()` is the `mapstyle` CLI. `render_map(db, mode, layers=True)` → `rs.render_edges` with:
  roads from `load_roads(db)` (one row per `edge_id`, mode flags) in the mode's palette +
  `settings=` from `styles/modes.yaml` (design: `docs/design/mode_styles.md`); feature layers
  from `load_layers(db)` (`styles/layers.yaml`: which `features.<table>` layers, draw order,
  `where`) as one `rs.Overlay` each, styled from `osm_carto.yaml` `features`, plus `layers.js`
  (injected before `</body>`) for what overlays can't draw: colour by `kind`, zoom ranges,
  dashes, textures (`patterns.py`), icons (`icons/*.svg`) (design: `docs/design/feature_layers.md`).
  `planner=True` adds `planner.html` (the route planner, from duckOSM's `route_map.py`, with the
  graphs from `planner_data`; design: `docs/design/route_planner.md`; browser check:
  `scripts/planner_check.py`). Re-extract it when duckOSM's planner changes.
- `patterns.py` (landcover texture tiles), `icons/*.svg` (point icons), `style.py` (`load_style`).
