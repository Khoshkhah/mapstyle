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
.venv/bin/pytest                             # no tests yet (the plan adds them, on a Monaco db)
.venv/bin/pytest tests/test_x.py::test_y     # a single test, once they exist

# test data: a small duckOSM db with features.*
cd ../duckOSM && .venv/bin/duckosm build -c config/sample_monaco.yaml   # needs build_features: true

# the current (to-be-replaced) viewer, from ../duckOSM/data/db/tartu.duckdb
.venv/bin/python render_tartu.py [db] [out_dir] [--debug]   # -> render/basemap (gitignored)
.venv/bin/python render/basemap/serve.py                    # -> http://localhost:8080/index.html
```

`../duckOSM/data/db/tartu.duckdb` has `features.*`; `sodermalm.duckdb` has none (the
missing-features case).

## What is where today

- `merge.py` — the live code: `merge_modes(db)` merges duckOSM's driving/walking/cycling networks
  into one row per `edge_id` with mode flags (kept by the plan as `ms.load`); `render_merge` is the
  ~860-line deck.gl viewer (to be deleted).
- The look: `src/mapstyle/styles/osm_carto.yaml` (road widths/colours, arrows, `features.*`
  styles keyed by layer `name`) + `layers.yaml` (which duckOSM `features.<table>` layers to show,
  draw order, `where` filters). Both survive the port: as roadstyle `settings=` / overlays where
  those fit, otherwise as mapstyle's own MapLibre layers on `window.map`.
- `patterns.py` (landcover textures) and `icons/*.svg` are cartography to carry over.
- `roads.py` — the openstreetmap-carto road palette by `highway` class (from `osm_carto.yaml`).
- Dead per the plan: `io.load_layer` (duckmap `basemap.*`), `render.py` / `render_folium.py` /
  `render_lonboard.py` / `render_web.py`, the physical width model (`merge._base_m` /
  `roads.width_model`, replaced by roadstyle's widths), `render_tartu.py`, `render_route.py`.
