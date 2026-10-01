---
name: mapstyle
description: Draw a whole OpenStreetMap map as one offline interactive HTML page with mapstyle - the roads for driving, walking and cycling over a full base map (sea, land use, water, buildings, railways, transit, crossings) - from a duckOSM database, optionally with a route planner or a dashboard, and script the page from JavaScript. Use when making a map, base map, travel-mode map (walking, cycling, driving), route planner or map dashboard from OpenStreetMap data or a duckOSM .duckdb file, or when filtering, colouring or querying roads and layers on a mapstyle or roadstyle page.
---

# mapstyle

A duckOSM database in, one self-contained HTML map out (MapLibre GL, drawn by roadstyle). Docs:
https://khoshkhah.github.io/mapstyle/ (all pages as one text file: `/llms-full.txt`; the Python
API: `/reference/python/`; JavaScript: `/reference/javascript/`).

## Install

```bash
pip install mapstyle "duckosm @ git+https://github.com/Khoshkhah/duckOSM"   # duckOSM: not on PyPI yet
pip install "mapstyle[tiles]"                                               # + vector tiles
```

Python 3.10+. roadstyle (>= 0.10) comes from PyPI.

## 1. A database (duckOSM)

mapstyle's only input is a duckOSM `.duckdb`: the mode networks plus `features.*` (the base map).

```bash
curl -LO https://download.geofabrik.de/europe/monaco-latest.osm.pbf
duckosm build --pbf monaco-latest.osm.pbf -o monaco.duckdb -m driving -m walking -m cycling
duckosm multimodal monaco.duckdb      # only for the planner's "Walk + drive"
```

A city takes seconds to a minute. The sea (`features.ocean`) comes from Overture Maps while
building: it needs the network.

## 2. The map

```bash
mapstyle monaco.duckdb                          # -> monaco_all.html
mapstyle monaco.duckdb --mode walking --paths komoot -o walk.html
mapstyle monaco.duckdb --planner                # route planner (default mode: walking)
mapstyle monaco.duckdb --dashboard              # side panel: filters, colour by mode
mapstyle region.duckdb --tiles                  # big areas: roads as vector tiles in the page
```

```python
import mapstyle as ms
m = ms.render_map("monaco.duckdb", mode="cycling", paths="cyclosm")
m.save("cycling.html")        # m.html is the page as a string; in Jupyter m displays itself
```

| `render_map` argument | Values |
|---|---|
| `mode` | `all` (default), `driving`, `walking`, `cycling`: which network stands out |
| `paths` | `google` (default), `osm`, `komoot`, `cyclosm`: how paths look |
| `layers` | `True` (all), a list (`["buildings", "crossings"]`), `False` (roads only) |
| `planner` / `dashboard` | `True` adds the route planner / makes it a dashboard |
| `interaction` | `{"crossings": {"clickable": True, "tooltip": True, "popup": False}}` |
| other keywords | to `roadstyle.render_edges`: `tiles=True`, `basemap="positron"`, `view_3d=True`, `arrows=False` |

Layers: `ocean`, `landcover`, `water`, `waterways`, `buildings`, `railways`, `parking`,
`parking_p`, `bus_station`, `platform`, `traffic_signals`, `crossings`, `bus_stations`,
`train_stations`, `bicycle`.

Data only: `ms.load_roads(db)` (GeoDataFrame, one row per `edge_id`, `driving` / `walking` /
`cycling` flags, `walk_type`), `ms.load_layers(db)` (`{layer: FeatureCollection}`).

## 3. Script the page (JavaScript)

Every page is a roadstyle page: `rsQuery(p => bool)` returns feature ids, then `rsFilter(ids)`,
`rsColor(ids, "#hex")`, `rsSetClasses([...])`, `rsSetOverlay("buildings", false)`, event
`rs:select`; `window.map` is the MapLibre map. mapstyle adds `rsSetModes(["walking"])`,
`rsSetKinds("landcover", ["park"])`, `rsSetInteraction("crossings", {tooltip: true})` and their
`rsGet*`, and `RS_KINDS`. Wait for `ms:ready` before calling them:

```js
document.addEventListener("ms:ready", () => {
  rsSetModes(["cycling"]);
  rsColor(rsQuery(p => p.name === "Boulevard du Larvotto"), "#e11d48");
});
```

To put your own script on the page: `m = ms.render_map(...)`, then write
`m.html.replace("</body>", "<script>...</script></body>")` to a file.

## Traps

- **`edge_id` is a 64-bit hash** (above 2**53): mapstyle gives it as a string. In JavaScript never
  pass `edge_id` numbers: select with `rsQuery(p => p.edge_id === "1494951369778192963")` and use
  the ids it returns.
- `planner=True` can't be combined with `dashboard=True` (both use the side panel) or `tiles=True`
  (it snaps to roads in the page): `ValueError`.
- No **Walk + drive** in the planner without `duckosm multimodal DB` first (the page says so).
- The planner routes between the two **points**: a marker joins the roads within "Off-road up to …
  m" (default 50) by a walk; none in reach -> "no road within R m". Scripted:
  `rmRoute([lon, lat], [lon, lat])`, then `window.rmLast` = `{modes, res}` or `{modes, error}`.
- A db built with `--no-features` (or by an old duckOSM) draws roads only (logged hint); one built
  offline has no sea (the coast's water is land-coloured).
- `palette` and `settings` aren't `render_map` keywords: the mode sets them. Change the look in
  `src/mapstyle/styles/*.yaml` (modes, paths, osm_carto, layers).
- Pages are self-contained and big (Monaco 3.4 MB, a city ~12 MB): above a city, use `tiles=True`.
- Layers are hidden until styled and the ROADS / LAYERS boxes start folded: a screenshot right
  after load can miss them; wait for `ms:ready`, then `map.once("idle", ...)`.
- To look at a page headlessly (playwright): open it, wait for `window.map && map.isStyleLoaded()`
  and `ms:ready`, `map.jumpTo({center: [lon, lat], zoom})`, wait for `idle`, screenshot. Don't
  return the `map` object from `page.evaluate` (it is huge): wrap calls in `() => { ...; }`.
