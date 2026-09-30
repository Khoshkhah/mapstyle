# mapstyle as a full-map library, on top of roadstyle

**Status:** approved 2026-09-30 (decisions at the end). Work plan: [`../PLAN.md`](../PLAN.md).

## Goal

roadstyle draws **roads** from any road table. mapstyle draws the **whole map** from a **duckOSM
database**: every travel mode, POIs, crossings, landcover, water, buildings, rail. Like roadstyle, it
is a library you **build dashboards with**, not only a picture:

```python
import mapstyle as ms

m = ms.render_map("monaco.duckdb")              # one offline HTML page, the full map
m.save("monaco.html")
```

The page has roadstyle's JavaScript API (`rsQuery`, `rsColor`, `rsSelect`, `rs:select`, …) plus a
few map-level calls, so a dashboard adds its own panel exactly as roadstyle dashboards do.

Who uses it: duckOSM (`duckosm viz`, `duckosm route-map`), SonoFlow-style dashboards over a duckOSM
area, and anyone with a duckOSM build.

## Where mapstyle is today (2026-09-30 review)

- **Already right:** reads a duckOSM db directly (mode networks + `features.*`, since 2026-07-03);
  merges the three mode networks into one road per `edge_id` (`merge_modes`); the cartography: which
  feature layers to show (`layers.yaml`), their look (`styles/osm_carto.yaml`), SVG icons, crossings
  turned to the street, landcover textures, construction roads.
- **To replace:** its own deck.gl viewer (`render_merge`, ~860 lines in one function). It writes a
  folder that needs a server, loads JS from a CDN, is 60 MB for Tartu, and has none of roadstyle's JS
  API, 3D, Street View or tiles. It also re-implements what roadstyle now does (base-map switcher,
  arrows, labels, boundary, click panel).
- **To delete:** the duckmap-era code (`io.load_layer` reads `basemap.*`), the folium / lonboard
  `render_basemap`, the Tartu scripts and paths, the `/api/route` planner hooks.
- No tests; v0.0.1; private.

## The design

### 1. One job each

| | Input | Does |
|---|---|---|
| **roadstyle** | any road table | the page: MapLibre, road cartography, overlays, tiles, JS API, 3D, Street View, one offline file |
| **mapstyle** | a duckOSM db | reads the db, decides **what** is on the map and **how it looks**, hands it to roadstyle |
| **duckOSM** | a PBF | builds the db; its `viz` and `route-map` are mapstyle pages |

mapstyle reads the db file with `duckdb`; it never imports duckOSM. The dependency runs one way:
`duckosm[viz]` → mapstyle → roadstyle.

**roadstyle is not changed** (Kaveh, 2026-09-30): mapstyle uses it as it is (see 4).

### 2. Python API

```python
data = ms.load("monaco.duckdb", modes=None, layers=None)   # read once, change, render
data.roads            # GeoDataFrame: one row per edge_id, columns driving / walking / cycling (bool)
data.layers["pois"]   # GeoDataFrame per feature layer (from layers.yaml)
data.boundary         # main.boundary, if the db has one

m = ms.render_map(data_or_db, mode=None, layers=None, style="carto", **roadstyle_keywords)
```

- `ms.load` exists so a dashboard can **join its own columns** onto the roads (flow, speed, cluster)
  before rendering, the same data contract as roadstyle.
- `mode=None` shows every mode; `"driving"`, `"walking"`, `"cycling"` shows that mode's network in
  its style (the others fade or hide).
- `layers=` picks feature layers by name (default: `layers.yaml`'s `show: true`).
- Every other keyword goes to `rs.render_edges` (`color_options`, `tooltip`, `basemap`, `tiles`,
  `view_3d`, …), so everything roadstyle can do, a mapstyle page can do.
- A db built without `features.*` (duckOSM's default today) gives a roads-only map with a one-line
  hint (`build_features: true`); a missing table or column skips that layer, never fails.
- CLI: `mapstyle monaco.duckdb -o monaco.html [--mode walking] [--tiles]`.

### 3. JavaScript API

The whole roadstyle API, plus:

| Call | Does |
|---|---|
| `rsSetOverlay("POIs", false)` | already in roadstyle: each feature layer is an overlay |
| `rs:select` with `e.detail.overlay` | already in roadstyle: a click on a POI / crossing |

Kept small on purpose: a new `ms*` call only when roadstyle's can't do it.

### 4. Built on roadstyle as it is (no roadstyle changes)

1. **Styles per travel mode**: mapstyle's own walking / cycling palettes, passed as roadstyle
   `settings=` ("a new name adds a palette"); every OSM path class gets an entry. One page per mode
   (no live switch). Details: [`mode_styles.md`](mode_styles.md).
2. **Feature layers**: roadstyle overlays where they fit (one style per layer); what they can't do
   (colour by a column, icons, rotation, textures, zoom ranges) is mapstyle's own MapLibre layers
   added through the page's `window.map`.
3. **Multi-mode roads:** one feature per `edge_id` with mode flags (`merge_modes`); the mode style
   picks which ones to draw and how.

### 5. The look

mapstyle's `osm_carto.yaml` + `layers.yaml` stay the source of the look and become roadstyle
settings / overlay styles when the page is built. Two things to settle while porting:

- **Road widths:** roadstyle's zoom-width tables (decided). mapstyle's physical width model
  (`docs/width-model.md`) is not ported.
- **Street names and arrows:** roadstyle's native MapLibre placement (line-following) replaces
  mapstyle's JS placement.

### 6. Size

Tartu is 60 MB today. Targets: a city (Monaco, Södermalm) inline in one file under ~10 MB; a larger
area with `tiles=True` (roads **and** feature layers as PMTiles in the page). duckmap's MVT code
(`duckmap/src/duckmap/tiles.py`) is the reference for layer tiling, then duckmap is archived.

## Ready-made pages

Like roadstyle's `render_dashboard` / `render_street_view`:

- `ms.render_map` (above).
- **Route planner** (decided: moves here): today `duckosm route-map`
  (`duckOSM/src/duckosm/route_map.py`, routing in the browser over the db's `edge_graph` / `mm.*`).
  Its input is a duckOSM db, so it becomes `ms.render_route_planner(db)`, and `duckosm route-map`
  calls it. Until mapstyle is published it stays in duckOSM (driving only in duckOSM's docs).

## Checks

- Tests on a small duckOSM db built in the test (Monaco sample): `load` (merge by `edge_id`, flags,
  every layer, missing `features.*`), `render_map` keywords reaching roadstyle.
- In a browser (playwright snapshots): Monaco all modes, walking, cycling; POIs and crossings
  visible and clickable; `route-map` routes along footways visible.
- File size on Monaco, Södermalm, Tartu (inline and tiled).

## Steps

1. mapstyle: mode palettes and feature layers on roadstyle as it is (4).
2. mapstyle: `load` + `render_map` on roadstyle; port the look; delete the deck.gl viewer, the folium /
   lonboard backends, duckmap and Tartu leftovers; tests; CLI.
3. duckOSM: `viz` extra → mapstyle; `duckosm viz` and `route-map` use it; docs.
4. mapstyle: README + docs site, make the repo public, PyPI (after duckOSM's 0.1.0).
5. Archive duckmap; freeze route-viewer on its last mapstyle commit (or port it to `route-map`).

## Decisions (2026-09-30)

- Road widths: roadstyle's. The physical width model is not ported.
- duckOSM builds `features.*` **by default** (`build_features: true`), so every map has POIs.
- The route planner moves into mapstyle (`ms.render_route_planner`).
- Name: "mapstyle" is already ours on PyPI (0.0.1 placeholder, links to Khoshkhah/mapstyle).
