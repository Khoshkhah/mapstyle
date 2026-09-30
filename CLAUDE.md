# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Start at [`docs/PLAN.md`](docs/PLAN.md)** (the work plan) and
[`docs/design/full_map_library.md`](docs/design/full_map_library.md) (the approved design). The code
in `src/mapstyle/` is mostly the old deck.gl viewer that the plan replaces; `README.md`,
`docs/PROCESS.md`, `docs/rendering.md` and `docs/width-model.md` describe that old state.

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
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest                             # builds a Monaco db with ../duckOSM (~10 s) per session
MAPSTYLE_TEST_DB=monaco.duckdb .venv/bin/pytest tests/test_modes.py::test_load_roads   # reuse a built db

# the current (to-be-replaced) viewer, from ../duckOSM/data/db/tartu.duckdb
.venv/bin/python render_tartu.py [db] [out_dir] [--debug]   # -> render/basemap (gitignored)
.venv/bin/python render/basemap/serve.py                    # -> http://localhost:8080/index.html
```

`../duckOSM/data/db/tartu.duckdb` has `features.*`; `sodermalm.duckdb` has none (the
missing-features case).

## What is where today

- `map.py` — the new code. `render_map(db, mode, layers=True)` → `rs.render_edges` with:
  roads from `load_roads(db)` (one row per `edge_id`, mode flags) in the mode's palette +
  `settings=` from `styles/modes.yaml` (design: `docs/design/mode_styles.md`); feature layers
  from `load_layers(db)` (`styles/layers.yaml`: which `features.<table>` layers, draw order,
  `where`) as one `rs.Overlay` each, styled from `osm_carto.yaml` `features`, plus `layers.js`
  (injected before `</body>`) for what overlays can't draw: colour by `kind`, zoom ranges,
  dashes, textures (`patterns.py`), icons (`icons/*.svg`) (design: `docs/design/feature_layers.md`).
- `merge.py` — `merge_modes(db)` + `render_merge`, the ~860-line deck.gl viewer (to be deleted;
  `load_roads` replaces `merge_modes`).
- `src/mapstyle/styles/osm_carto.yaml` also still holds the old viewer's width model and route
  style (dead with it).
- `roads.py` — the openstreetmap-carto road palette by `highway` class (from `osm_carto.yaml`).
- Dead per the plan: `io.load_layer` (duckmap `basemap.*`), `render.py` / `render_folium.py` /
  `render_lonboard.py` / `render_web.py`, the physical width model (`merge._base_m` /
  `roads.width_model`, replaced by roadstyle's widths), `render_tartu.py`, `render_route.py`.
