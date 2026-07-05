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

## Merged multi-modal viewer (names, oneway arrows, boundary)

The main output: merge the three mode networks into one OSM-styled, interactive viewer
(deck.gl + MapLibre). `overlays=` turns on the **street names** / **oneway arrows** overlays and
`boundary=` adds a **city-boundary** outline (all toggleable in the viewer panel).

```python
from mapstyle import merge_modes, render_merge

DB = "../duckmap/data/db/tartu_basemap.duckdb"        # a duckmap basemap db
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

### Base map vs debug viewer — `interactive=`

`render_merge` produces two flavours of the **same** baked base map, controlled by `interactive=`:

| `interactive` | viewer | what you get |
| --- | --- | --- |
| `False` (default) | **base map** | Lean & fast: the styled base map (roads + features + names/arrows) as a **static, display-only** backdrop. **No picking, no hover, no info panel** — the panel has only the **Base layer** selector. Nothing per-feature is embedded, so it stays light. Use it as a backdrop under your own overlays (e.g. a routing layer). |
| `True` | **debug viewer** | Everything interactive: **hover-highlight**, **click-to-inspect** (an info panel with each object's `osm_id` / class / name / full OSM tags), per-mode and per-feature **toggles**, colour-by-mode, and the legend. |

```python
render_merge(merged, "render/basemap")                     # base map (default) — fast static backdrop
render_merge(merged, "render/debug", interactive=True)     # full inspectable debug viewer
```

The bundled Tartu driver defaults to the **base map** and takes `--debug` for the inspectable one:

```bash
python render_tartu.py                 # -> render/basemap (lean base map)
python render_tartu.py --debug         # -> render/debug_visualization (hover / click / toggles)
python render_tartu.py --guidance      # -> render/guidance (base map + turn-by-turn side panel)
python render_tartu.py --plan          # -> render/planner (INTERACTIVE: click endpoints, pick modes)
python render/basemap/serve.py         # -> http://localhost:8080/index.html
```

The `--plan` planner is served with a live routing backend (it fetches `/api/route` on each click) —
run it via the sibling **route-viewer** project: `route-viewer --serve --build-base`. `render_merge`'s
`plan=True` adds the mode checkboxes + click-to-place markers; `route_panel=True` alone gives the
static guidance side panel (turn list from a pre-written `data/route.geojson`).

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
