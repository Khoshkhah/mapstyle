# mapstyle rendering

mapstyle turns loaded OSM layers into interactive maps. There are **3 render entry points** plus
**2 backends** that one of them dispatches to.

## What we have

| Function | File | Output | Status |
|---|---|---|---|
| **`render_merge`** | `merge.py` | The **"Debug Visualization"** — a MapLibre GL + deck.gl inspection viewer (mode filters, zoom readout, click-to-inspect edge_id/lanes/width, colour-by-mode). Per-zoom road widths, casing, street names, oneway arrows, **base-map feature layers** (`feature_layers=`), **SVG category icons**. | **Dev/debug viewer in use — NOT a product render.** |
| **`render_web`** | `render_web.py` | Self-contained MapLibre + deck.gl viewer with per-layer toggles. Simpler; road styling is fixed-width (no per-zoom curve). | Fallback / simpler web export. |
| **`render_basemap`** | `render.py` | Composes loaded `Layer`s onto one map, dispatching to a backend (`folium` or `lonboard`). | Older per-layer compositor. |

**Backends** (called *via* `render_basemap`, not directly):

| Backend | File | Engine |
|---|---|---|
| `render_folium.render()` | `render_folium.py` | folium / Leaflet |
| `render_lonboard.render()` | `render_lonboard.py` | lonboard / deck.gl (WebGL) |

> **Removed:** `render_web_features` was an earlier standalone "all features + per-zoom widths +
> names/arrows" renderer. It's gone — `render_merge` + `feature_layers` now does everything it did,
> reusing render_merge's proven name/arrow placement instead of a from-scratch copy.

## `render_merge` — the Debug Visualization

A **development / inspection** viewer (titled "Debug Visualization" in the side panel), **not a
product render**. It renders a complete, filterable map with debug affordances (mode checkboxes, live
zoom readout, click a road to see its edge_id / lanes / physical width):

- **Roads** — physical, config-fixed widths (`styles/osm_carto.yaml` → `roads.width_model`, see
  [width-model.md](width-model.md)) + casing, coloured by OSM class or mode combination, with
  link/bridge/tunnel z-order.
- **Overlays** — street-name labels (fitted per road, collision-placed) and oneway arrows (z≥16).
- **Feature layers** (`feature_layers=[...]`) — water / land / buildings / rail drawn *under* the
  roads, and **point categories** (parking, traffic signals, bus / bicycle / train stations,
  crossings) drawn *on top* as **SVG icons** from `src/mapstyle/icons/`.
- Everything about the features is **config-driven** in `styles/osm_carto.yaml` under `features:`
  (see below) — colours, sizes, icons, per-zoom sizing, per-category `min_zoom`.

```python
from mapstyle import merge_modes, render_merge, load_layer
merged = merge_modes(DB)                       # roads with mode flags
feats  = [load_layer(DB, "water", "polygon"), load_layer(DB, "buildings", "polygon"), ...]
render_merge(merged, "render/tartu", basemap="none",
             overlays=("names", "arrows"), feature_layers=feats,
             zoom=16, center=[26.72, 58.38])   # optional initial view
# then: python render/tartu/serve.py 8080  ->  http://localhost:8080/index.html
```

The driver script **`render_tartu.py`** wires this up end to end (roads + all feature categories +
icons + oriented crossings) — a good copy-paste starting point.

## Feature styling lives in the config

All feature-layer look lives in `src/mapstyle/styles/osm_carto.yaml` → `features:` — edit and
re-render, no code:

- `features.areas` — polygon fills (per layer, or per `class` for `landcover`) + outline + opacity.
- `features.lines` — line colour / width / dash.
- `features.points` — per category: `color` (tints the SVG), `size` (multiplier), `icon` (an SVG
  file in `src/mapstyle/icons/`), `min_zoom` (hidden below it).
- `features.icon` — the shared icon **size-by-zoom curve** (`size: {12:5, 14:9, 16:14, …}`,
  interpolated like `roads.width`), plus `hi_rate` and `opacity`.

Icons are monochrome SVG *masks*, so each category's config `color` tints it. Crossings carry a
`bearing` (the road direction) and are rotated so the marking lies across the road.

## Inputs — one duckOSM db, nothing else

Everything comes from a **single duckOSM db** built with `options.build_features: true` (no duckmap):

- **Roads** — `merge_modes(db)` reads the per-mode routing graphs `driving.edges` / `walking.edges`
  / `cycling.edges` directly. These are *directed* (a two-way segment keeps both its forward and
  reverse rows); `_offset_two_way` fans that pair into two parallel lanes. `highway`/`geometry` are
  aliased to the `class`/`geom` the styling expects.
- **Base map** — the feature `Layer`s are read from the `features.*` schema (Shortbread `kind`):
  `water_polygons` (incl. the river — needs the `smart` clip that `build_features` auto-enables),
  `water_lines`, `land`, `buildings`, `streets` (rail), `sites` (parking polygons), `public_transport`
  (bus/train), `pois` (bicycle), and duckOSM's `traffic` extension (`traffic_signals` + `crossing`,
  the latter carrying a road `bearing` so the marking is oriented).

`render_tartu.py` is the end-to-end driver: point it at `duckOSM/data/db/tartu.duckdb` and it
loads roads + every feature layer from that one file.
