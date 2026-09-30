# Feature layers: the rest of the base map (landcover, water, buildings, POIs, crossings)

**Status:** proposal, for sign-off before implementation. **roadstyle is not changed**: every layer
is a roadstyle `Overlay`; what an overlay can't draw, mapstyle's own script adds on the page's
`window.map`.

## Problem

`render_map(db, mode)` draws only roads, on a raster base map. duckOSM builds the rest of the map
into `features.*` (Monaco: `land` 237 polygons, `water_polygons` 27, `water_lines` 4, `buildings`
1262, `sites` 79, `streets` 3496, `traffic` 575 crossings / signals with a `bearing`,
`public_transport` 107, `pois` 1645, `place_labels` 10; every table has `osm_id`, `kind`, `name`,
`tags`, `geom`). mapstyle already says *which* layers to draw and *how*:

- `layers.yaml` (repo root, read by `render_tartu.py`): 15 layers in draw order, each a
  `features.<table>` with an optional `where` (e.g. railways = `streets` where `kind IN ('rail', …)`),
  `centroid` (a point from a polygon), `bearing` (oriented crossings), `merge_into` (school / hospital
  grounds drawn in one sort with landcover).
- `osm_carto.yaml` `features`: fills / outlines / opacity / `min_zoom` per area layer, landcover
  colour **by `kind`** (~60 classes), textures by kind (`patterns.py`: trees, graves, waves, …),
  outlines by kind, line colour / width / dash, point icons (`icons/*.svg`) with colour, size by
  zoom and `min_zoom`.

The deck.gl viewer draws all of this; it is being deleted, so the look has to move onto
roadstyle's page.

## What a roadstyle overlay can and can't do

An `rs.Overlay` is one source + a fill (+ outline), line or circle layer, `under` or `over` the
roads (under-overlays keep list order, first = bottom), with one colour, opacity, width, radius, a
click popup, a hover tooltip, a row in the *Layers* control, `rsSetOverlay(label, on)` and
`rs:select`. It can't: colour by a column, dash a line, hide below a zoom, fill with a texture,
draw an icon, rotate one.

## Proposal

### 1. One overlay per layer

`layers.yaml` moves to `src/mapstyle/styles/` (package data). Each entry becomes one `rs.Overlay`:
polygons and lines `under` the roads, points `over`; `label` = the layer name; the colour, outline,
opacity and width from `osm_carto.yaml`. `merge_into` stays: the merged rows are one overlay,
sorted largest area first so a school's pitch draws over the school. `centroid` is done in SQL.

The data is GeoJSON built by DuckDB (`ST_AsGeoJSON`), not a GeoDataFrame round trip: shorter
coordinates, and no geopandas cost for 10k buildings.

Clickable (popup `name`, `kind`): buildings, sites, points. Landcover, water and lines are
decoration (`popup=[]`), so a click on a park still selects the road on top of it.

So the *Layers* control, `rsSetOverlay`, hover and `rs:select` work for every layer with no
mapstyle code.

### 2. mapstyle's script for the rest

One `<script>`, added before `</body>` the way roadstyle's own `render_dashboard` adds its sidebar,
run on `map.on("load")`. For each layer it finds the overlay through `window.RS_OVERLAYS` (by
label: source `ov<i>`, layer ids) and:

| Needs | Done with |
|---|---|
| landcover colour and outline by `kind` | `setPaintProperty` with a `match` on `kind` (keeping roadstyle's hover / select `case` for clickable layers) |
| `min_zoom` | `setLayerZoomRange` |
| railway dash | `line-dasharray` |
| textures | the `patterns.py` tiles, tinted per class in Python (MapLibre can't tint a `fill-pattern`), `map.addImage`, one extra `fill` layer with `fill-pattern` on the landcover source |
| icons | the SVGs tinted in Python, `map.addImage`, a `symbol` layer on the point overlay's source: `icon-size` by zoom (`features.icon.size`), `icon-rotate` from `bearing` (crossings). The overlay's circle stays as the click target, made transparent. |

Every layer the script adds is pushed into that overlay's `layers` list in `RS_OVERLAYS`, so the
*Layers* checkbox and `rsSetOverlay` hide the textures and icons with their layer.

### 3. API

```python
ms.render_map(db, mode="walking", layers=True)    # True = every layers.yaml layer; a list of names; False = roads only
```

- `features.*`, a table or a column missing → that layer is skipped with a logged hint, never an
  error (Södermalm has no `features.*`: roads only, as today).
- With feature layers the default base map is `voyager_nolabels`, drawn under them. `blank` was
  the plan (the features *are* the base map), but duckOSM has no sea: `water_polygons` holds lakes
  and basins, and the sea is only implied by coastline lines, so on `blank` Monaco's sea was
  land-coloured. `blank` stays in the switcher and becomes the default once duckOSM builds sea
  polygons (PLAN step 3). Without feature layers, the default stays roadstyle's.
- `load_layers(db, names=None)` → `{name: FeatureCollection}` for dashboards that want the data.

### 4. Size

GeoJSON from DuckDB: Monaco ~1.9 MB for all of `features.*` (buildings 0.5, of which the page
uses a subset), Tartu ~15 MB (buildings 7.3, land 2.6, streets 3.8 of which only railways are
drawn). Monaco and Södermalm fit the plan's ~10 MB page. Tartu-size areas need the plan's size
item (simplify, or tiles), not this note.

## Not in this note

Place labels (`place_labels`), 3D buildings, per-mode feature styles (e.g. bicycle parking bolder
in `cycling`): later, if wanted.

## Checks

- Tests: every `layers.yaml` layer has a style in `osm_carto.yaml`; each `where` finds rows on
  Monaco; a db without `features.*` renders roads only with a hint; `layers=` picks overlays by
  name; the page has one overlay per layer and the script's layer ids.
- In a browser (snapshots, Monaco z14 and z17): landcover colours and textures, water, buildings,
  crossings rotated along the road, bus-stop icons; unticking *crossings* in the Layers control
  hides its icons; a click on a building shows its popup.
