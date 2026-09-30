# mapstyle — work plan

**What mapstyle becomes** (approved 2026-09-30, design: [`design/full_map_library.md`](design/full_map_library.md)):
the **full-map library on top of roadstyle**. Its only input is a **duckOSM database**; it decides
what is on the map and how it looks, and roadstyle draws it (one offline HTML page, roadstyle's JS
API, 3D, Street View, tiles). Like roadstyle, it is for **building dashboards**, not only a picture.
duckOSM's `duckosm viz` and `duckosm route-map` become mapstyle pages.

Decided: roadstyle's road widths (the physical width model is not ported); duckOSM builds
`features.*` by default; the route planner moves here; the PyPI name "mapstyle" is ours already.

## Status before this plan (2026-09-30 review)

- Reads a duckOSM db already (`merge.merge_modes`, `render_tartu.py` + `layers.yaml` for `features.*`).
- The viewer is its own deck.gl app (`render_merge`): a folder + `serve.py`, CDN JS, 60 MB for
  Tartu, none of roadstyle's JS API. It gets replaced by roadstyle's page.
- Dead code: `io.load_layer` (duckmap's `basemap.*`), folium / lonboard `render_basemap`, Tartu paths
  in the scripts, route-viewer `/api/route` hooks. duckmap (the sibling) is superseded by duckOSM's
  `features.*` and will be archived; only its MVT code (`duckmap/src/duckmap/tiles.py`) is a reference.
- No tests. `.venv` has a stale roadstyle metadata (0.2.0.dev1): `pip install -e ../roadstyle` first.
- Branch `viewer-more-info` (2 commits, info-panel fields in the deck.gl viewer) is unmerged; it
  goes away with that viewer.

## Steps

### 1. Mode styles and map layers, in mapstyle (roadstyle is not changed)

roadstyle stays as it is (Kaveh, 2026-09-30). mapstyle builds on what it already offers:
`settings=` (new palettes, per-class styles, draw order), `overlays=`, `color_options`, the JS API,
and its own JS on the page's `window.map` (MapLibre).

- [x] **Styles per travel mode:** mapstyle's own walking / cycling palettes (every OSM path class:
      steps, pedestrian, corridor, platform, bridleway), passed as roadstyle settings
      (`styles/modes.yaml`, `mapstyle.map.render_map(db, mode)`), one page per mode. Design:
      [`design/mode_styles.md`](design/mode_styles.md). Routes visible on footways: checked with
      the route planner (step 2).
- [x] **Feature layers beyond roadstyle's overlays:** colour by a column (one overlay per value, or a
      `window.map` layer), point icons with rotation (crossings), area textures (`patterns.py`),
      zoom ranges: mapstyle's own MapLibre layers added through `window.map`. Design note for
      sign-off: [`design/feature_layers.md`](design/feature_layers.md). Done: `render_map(db, mode,
      layers=True)`, `styles/layers.yaml`, `layers.js`.
- [ ] **Multi-mode roads:** one feature per `edge_id` with `driving` / `walking` / `cycling` flags
      (`merge_modes`); the mode style picks what to draw.

### 2. mapstyle on roadstyle

- [ ] `ms.load(db, modes=None, layers=None)` → roads (one row per `edge_id`, `driving`/`walking`/
      `cycling` flags), `layers[name]` GeoDataFrames from `layers.yaml`, `boundary` from
      `main.boundary`. Missing `features.*` / table / column → skip with a hint, never fail.
- [ ] `ms.render_map(data_or_db, mode=None, layers=None, style="carto", **roadstyle_keywords)` →
      `rs.render_edges(..., overlays=[...])`. `osm_carto.yaml` + `layers.yaml` become roadstyle
      settings / overlay styles.
- [ ] JS: layers via `rsSetOverlay`, clicks via `rs:select` (modes are one page each, see
      `design/mode_styles.md`).
- [ ] `ms.render_route_planner(db)`: move `../duckOSM/src/duckosm/route_map.py` here (routing in
      the browser over `edge_graph` / `mm.*`; checked on Monaco against duckOSM's `route()` /
      `route_multimodal()`: 8 of 8 trips).
- [ ] CLI: `mapstyle db.duckdb -o map.html [--mode walking] [--tiles]`.
- [ ] Delete: the deck.gl viewer (`render_merge` / `render_web.py`), `render_basemap` + folium /
      lonboard, `io.load_layer`, `render_tartu.py`, `render_route.py`, the width model, stale docs
      (`PROCESS.md`, `rendering.md`, `width-model.md` as needed).
- [ ] Tests on a Monaco db (build below): load, missing features, keywords reaching roadstyle,
      the planner's graphs. Browser checks (playwright, `rs.snapshot`): all modes,
      walking, cycling, POIs/crossings clickable, a footway route visible.
- [ ] Size: Monaco / Södermalm inline < ~10 MB; bigger areas with roadstyle's `tiles=True` for the roads (feature layers: simplify, or mapstyle's own tiles, see duckmap's `tiles.py`).

### 3. duckOSM (repo `../duckOSM`)

- [ ] `build_features` default `true` (config.py, template, docs).
- [ ] **Extract the sea:** duckOSM builds no sea (OSM has only `natural=coastline` lines, land on
      their left), so mapstyle draws feature layers over a raster base map. Clip the precomputed
      sea polygons (osmdata.openstreetmap.de "water polygons", built from the world coastline; what
      openstreetmap-carto uses) to the area into `features.water_polygons` (`kind = 'sea'`). Building
      them from the extract's own coastline lines is the offline alternative, but fragile (open ends
      at the clip edge, one gap floods the land). Then mapstyle's default base map goes back to
      `blank` (`design/feature_layers.md` §3).
- [ ] `viz` extra → `mapstyle`; `duckosm viz` and `duckosm route-map` call mapstyle; docs (Draw a
      map, Route).

### 4. Publish

- [ ] README + docs site (mkdocs, like roadstyle / duckOSM), pyproject (`roadstyle>=0.9.1`, fix
      `package-data`), repo public, PyPI (after duckOSM 0.1.0).
- [ ] Archive duckmap; freeze route-viewer on its last mapstyle commit (or port it to the planner).

## Test data

```bash
cd ../duckOSM && .venv/bin/duckosm build -c config/sample_monaco.yaml   # add build_features: true until it's the default
```

`../duckOSM/data/db/tartu.duckdb` has `features.*`; `sodermalm.duckdb` has none (the missing-features case).
