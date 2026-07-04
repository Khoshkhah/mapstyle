# mapstyle rendering

mapstyle turns loaded OSM layers into interactive maps. There are **3 render entry points** plus
**2 backends** that one of them dispatches to.

## What we have

| Function | File | Output | Status |
|---|---|---|---|
| **`render_merge`** | `merge.py` | The merged multi-modal viewer — MapLibre GL + deck.gl. Per-zoom road widths, casing, street names, oneway arrows, driving/walking/cycling filters, **base-map feature layers** (`feature_layers=`), and **SVG category icons**. | **Main viewer — use this.** |
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

## `render_merge` — the one to use

It started as the merged road viewer and now renders a complete, filterable map:

- **Roads** — per-zoom widths + casing from `styles/osm_carto.yaml` (`roads.width` / `hi_rate` /
  `casing_ratio`), coloured by OSM class or mode combination, with link/bridge/tunnel z-order.
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

## Inputs

`render_merge` reads roads via `merge_modes(db)` and takes feature `Layer`s from `load_layer(...)`.
Today those come from a **duckmap** basemap db, except the **river polygon**, which needs a
**duckOSM** `smart`-clip features db (duckmap's water lacks it). The clean long-term target is a
single duckOSM db built with `options.build_features` holding routing + `features.*` — then
everything comes from one place.
