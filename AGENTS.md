# AGENTS.md

Rules for AI coding agents (Codex, Cursor, Copilot, Gemini, Claude Code, …) working on this
repository. To *use* mapstyle rather than change it, read the agent skill
[`skills/mapstyle/SKILL.md`](skills/mapstyle/SKILL.md).

**Start at [`docs/PLAN.md`](docs/PLAN.md)** (the work plan) and
[`docs/design/full_map_library.md`](docs/design/full_map_library.md) (the approved design), then the
feature notes in `docs/design/`. The old deck.gl viewer is deleted; it is in git history (e.g.
`git show 18e4a23:src/mapstyle/merge.py`).

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
  roads from `load_roads(db)` (one row per `edge_id`, mode flags) in `mode_settings(mode, paths)`:
  palette + `settings=` from `styles/modes.yaml` (`all`/driving/walking/cycling: which network is
  on top) and `styles/paths.yaml` (path styles, default `google`); crossings over / sidewalks
  under their street from duckOSM's `walk_type` (roadstyle's `band_col`, a roadstyle feature added
  for this at Kaveh's request); paths and one-way streets drawn as one line, not two lanes,
  from `is_directed` (roadstyle's `directed_col`) (design:
  `docs/design/mode_styles.md`); base map `blank` (Kaveh's choice; the sea is duckOSM's `features.ocean`); themes (`theme=`: `osm`,
  `google`, `grey`; `styles/themes/*.yaml` over osm_carto.yaml via `style.load_theme`; design:
  `docs/design/themes.md`); feature layers
  from `load_layers(db)` (`styles/layers.yaml`: which `features.<table>` layers, draw order,
  `where`) as one `rs.Overlay` each, styled from `osm_carto.yaml` `features`, plus `layers.js`
  (injected before `</body>`) for what overlays can't draw: colour by `kind`, zoom ranges,
  dashes, textures (`patterns.py`), icons (`icons/*.svg`) (design: `docs/design/feature_layers.md`).
  `planner=True` adds `planner.html` (the route planner, from duckOSM's `route_map.py`, with the
  graphs from `planner_data`; design: `docs/design/route_planner.md`; browser check:
  `scripts/planner_check.py`). Re-extract it when duckOSM's planner changes. `layers.js` is on
  every page, folds the Roads / Layers boxes (Layers under Roads; unseen until placed), and also defines mapstyle's `rs*` functions (`rsSetModes`, `rsSetKinds`,
  `rsSetInteraction`; README's JavaScript table); `dashboard=True` renders roadstyle's
  `render_report` + `dashboard.js` (design: `docs/design/dashboard.md`). Private roads and bus lanes
  (`private_edges`): `load_roads`' `access_<mode>`, the page's `access` by mode (`_access`), drawn
  and toggled by `layers.js` (`rsSetAccess`; design: `docs/design/private_and_bus.md`).
- The drawing order of the roads is roadstyle's (`docs/design/stored_levels.md`): `render_map` reads `visualization.edge_levels` when duckOSM's `duckosm levels` stored it, else roadstyle
  computes the casing and fill numbers while it renders, from the complete band (`_band`). `levels.py` is the older cutting into pieces (`pieces=True`).
- `patterns.py` (landcover texture tiles), `icons/*.svg` (point icons), `style.py` (`load_style`).

## Docs site, CI, agent files

- The site (https://khoshkhah.github.io/mapstyle/) is `mkdocs.yml` + `docs/` (Material for
  MkDocs); `docs/design/` and `docs/PLAN.md` stay off it. Its live maps (`docs/maps/`, git-ignored)
  are built in CI from duckOSM's Monaco sample by `docs/build_maps.py`; its pictures
  (`docs/img/*.jpg`) by hand with `docs/build_images.py DB` (playwright). Check a change with
  `mkdocs build --strict` (needs `.[docs]`). It also publishes `/llms.txt` and `/llms-full.txt`.
- CI (`.github/workflows/ci.yml`): the tests on Python 3.10 and 3.12 against a duckOSM checkout
  (`DUCKOSM_DIR`, `DUCKOSM_EXE`); `docs.yml` deploys the site on pushes to `main` that touch it.
- When the API, a style or a command changes, update the skill (`skills/mapstyle/SKILL.md`), the
  README and the matching `docs/` page with it. The Claude plugin is `.claude-plugin/`.
- The repository is public: commits use the GitHub no-reply address (repo-local `user.email`).
