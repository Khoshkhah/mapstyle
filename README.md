# mapstyle

OSM **full-base-map styling** — [`roadstyle`](../roadstyle)'s engine generalized from road
edges to a complete base map (landcover / water / buildings polygons + roads/rail/water
lines + place/POI points), composed onto one interactive map.

`roadstyle` styles *lines* (a `highway` column → casing+fill, palettes, themes, folium/lonboard
backends). `mapstyle` **reuses that styler** for the road layers and adds **polygon** (fill +
outline) and **point** (marker) stylers, plus **multi-layer composition** (`render_basemap`).

It pairs with [`duckOSM`](../duckOSM) / [`duckmap`](../duckmap): duckmap produces the
`basemap.*` data layers; mapstyle renders them.

```python
from mapstyle import load_layer, render_basemap

driving = load_layer("../duckmap/data/db/tartu_basemap.duckdb", "roads_driving", "line")
render_basemap([driving], theme="light").save("driving.html")

# build up layer by layer
water     = load_layer(DB, "water", "polygon")
landcover = load_layer(DB, "landcover", "polygon")
render_basemap([landcover, water, driving], theme="light").save("tartu.html")
```

## Merged multi-modal viewer (with names & oneway arrows)

The main output: merge the three mode networks into one OSM-styled, interactive viewer
(deck.gl + MapLibre). `overlays=` turns on the **street names** and **oneway arrows** overlays
(both are also toggleable checkboxes in the viewer panel).

```python
from mapstyle import merge_modes, render_merge

DB = "../duckmap/data/db/tartu_basemap.duckdb"        # a duckmap basemap db
merged = merge_modes(DB)                               # 1 edge set, with mode flags

# choose what starts ON: "names", "arrows", both, or none
render_merge(merged, "render/tartu", basemap="osm", overlays=("names", "arrows"))
render_merge(merged, "render/tartu", overlays=("arrows",))   # just arrows
render_merge(merged, "render/tartu")                         # neither (toggle in-viewer)
```

Then serve and open:

```bash
python render/tartu/serve.py        # -> http://localhost:8080/index.html
```

In the viewer's **Overlays** box: tick **street names** (shows at zoom ≥ 13) and/or
**oneway arrows** (zoom ≥ 15). `basemap=` picks the underlay (`osm` | `positron` | `dark` |
`satellite` | `none`), also switchable in the panel. Road widths/casing are tunable in
[`src/mapstyle/styles/osm_carto.yaml`](src/mapstyle/styles/osm_carto.yaml). Full architecture
and decisions: [`docs/PROCESS.md`](docs/PROCESS.md).

## Status

Merged multi-modal viewer with OSM-Carto road styling (per-zoom widths from a YAML config,
casing, dashes, link/bridge/tunnel z-order, narrow/wide service split) + names/arrows overlays.
Area layers (water/landcover/buildings) are next. See [`docs/PLAN.md`](docs/PLAN.md).

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ../roadstyle      # the styling brain (sibling repo)
pip install -e ".[duckdb,dev]"
```
