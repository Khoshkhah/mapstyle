# mapstyle

OSM **full-base-map styling** — [`roadstyle`](../roadstyle)'s engine generalized from road
edges to a complete base map (landcover / water / buildings polygons + roads/rail/water
lines + place/POI points), composed onto one interactive map.

`roadstyle` styles *lines* (a `highway` column → casing+fill, palettes, themes, folium/lonboard
backends). `mapstyle` **reuses that styler** for the road layers and adds **polygon** (fill +
outline) and **point** (marker) stylers, plus **multi-layer composition** (`render_basemap`).

It reads a [`duckOSM`](../duckOSM) `.duckdb` directly: duckOSM extracts the OSM base map into a
`features.*` schema (Shortbread vector-tile layers — `streets`, `water_polygons`, `land`,
`buildings`, `pois`, …) alongside the routing graphs, and mapstyle renders those. No separate
build step — point it at the same db (`options.build_features` on the duckOSM side).

```python
from mapstyle import load_layer, render_basemap

DB = "../duckOSM/data/db/tartu.duckdb"       # a duckOSM db built with options.build_features

# build up layer by layer (Shortbread layer names, bottom -> top)
land      = load_layer(DB, "land", "polygon")
water     = load_layer(DB, "water_polygons", "polygon")
buildings = load_layer(DB, "buildings", "polygon")
streets   = load_layer(DB, "streets", "line")          # roads + rail merged (Shortbread)
render_basemap([land, water, buildings, streets], theme="light").save("tartu.html")
```

## Merged multi-modal viewer (names, oneway arrows, boundary)

The main output: merge the three mode networks into one OSM-styled, interactive viewer
(deck.gl + MapLibre). `overlays=` turns on the **street names** / **oneway arrows** overlays and
`boundary=` adds a **city-boundary** outline (all toggleable in the viewer panel).

```python
from mapstyle import merge_modes, render_merge

DB = "../duckOSM/data/db/tartu.duckdb"                 # a duckOSM db (reads <mode>.edges directly)
merged = merge_modes(DB)                               # 1 edge set, with mode flags

# choose what starts ON: "names", "arrows", both, or none
render_merge(merged, "render/tartu", basemap="osm", overlays=("names", "arrows"))
render_merge(merged, "render/tartu", overlays=("arrows",))   # just arrows
render_merge(merged, "render/tartu")                         # neither (toggle in-viewer)

# + a city-boundary outline (a .geojson path or a shapely geometry)
render_merge(merged, "render/tartu", overlays=("arrows",),
             boundary="../duckOSM/data/boundaries/tartu.geojson")
```

Then serve and open:

```bash
python render/tartu/serve.py        # -> http://localhost:8080/index.html
```

In the viewer's **Overlays** box: tick **street names** (zoom ≥ 13), **oneway arrows**
(zoom ≥ 16), and the **city boundary**. `basemap=` picks the underlay (`osm` | `positron` |
`dark` | `satellite` | `none`), also switchable in the panel. Road **widths, colors, and the
oneway arrows** are tunable in
[`src/mapstyle/styles/osm_carto.yaml`](src/mapstyle/styles/osm_carto.yaml) (`roads.width` /
`roads.colors` / `arrows.*`) — edit and re-render. Full architecture and decisions:
[`docs/PROCESS.md`](docs/PROCESS.md).

## Status

Merged multi-modal viewer with OSM-Carto road styling — per-zoom widths, colors, and oneway
arrows all from a YAML config (`roads.width` / `roads.colors` / `arrows.*`), plus casing,
dashes, link/bridge/tunnel z-order, narrow/wide service split — and names / arrows / city-boundary
overlays. Area layers (water/landcover/buildings) are next. See [`docs/PLAN.md`](docs/PLAN.md).

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ../roadstyle      # the styling brain (sibling repo)
pip install -e ".[duckdb,dev]"
```
