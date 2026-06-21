# mapstyle — plan

Generalize `roadstyle` (line/edge styling) into a full OSM base-map renderer.

## Why a new package (not extending roadstyle)

roadstyle is a clean, column-agnostic styling brain but **line-only** in two places: the
spec-JSON and `roadstyle.js` bake/draw only line casing+fill. Extending it in place would
break its single responsibility and its backward-compatible spec. So `mapstyle` is a sibling
that **imports roadstyle** for the road layers and adds what roadstyle lacks.

## What we reuse vs add

| Concern | Reuse from roadstyle | New in mapstyle |
|---|---|---|
| Styling brain | `resolve(class, palette, theme)`, `PALETTES`, `THEMES`, `Styler`s | `PolygonStyler` (fill+outline), `PointStyler` (marker) |
| Road layers | the whole line pipeline | — |
| Composition | — | `render_basemap(layers)` — many layers, one map, z-ordered |
| Backends | folium / lonboard patterns | polygon + point rendering per backend |
| Frontend (later) | `roadstyle.js` casing/fill | polygon outline + point markers branch |

## Layers (z-order, bottom → top)

landcover → water → waterways → buildings → roads(_driving/_walking/_cycling) → railways →
places/POIs. Each is a `Layer(name, gdf, kind, palette, z)`.

## Incremental build (matches the layer-by-layer workflow)

1. **driving roads** via roadstyle, composed on a shared folium map ← *increment 1 (done)*
2. **+ cycling**, **+ walking** (distinct palettes / toggles)
3. **+ water, + landcover, + buildings** (PolygonStyler — fills now, outlines/refinement next)
4. **+ places / POIs** (PointStyler — markers + labels)
5. **web (mapstyle.js) + lonboard** backends for scale

## Open questions

- Per-mode road styling: same carto palette, or cycling/walking highlighted differently?
- Polygon palette: reuse the duckmap OSM-carto colors (done) vs a roadstyle-style palette table.
- Frontend: extend `roadstyle.js` in place vs a `mapstyle.js` fork (deferred until backends matter).
