<p align="center">
  <img src="https://raw.githubusercontent.com/Khoshkhah/mapstyle/main/docs/img/logo.svg" alt="mapstyle" width="96">
</p>

<h1 align="center">mapstyle</h1>

<p align="center">
  <b>A whole OpenStreetMap map in one offline HTML page:<br>
  the roads for driving, walking and cycling over a full base map, from one duckOSM database.</b>
</p>

<p align="center">
  <a href="https://pypi.org/project/mapstyle/"><img alt="PyPI" src="https://img.shields.io/pypi/v/mapstyle"></a>
  <a href="https://github.com/Khoshkhah/mapstyle/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Khoshkhah/mapstyle/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://khoshkhah.github.io/mapstyle/"><img alt="Docs" src="https://img.shields.io/badge/docs-khoshkhah.github.io%2Fmapstyle-0f9488"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776AB">
  <img alt="License MIT" src="https://img.shields.io/badge/license-MIT-blue">
</p>

<p align="center">
  <a href="https://khoshkhah.github.io/mapstyle/"><b>Documentation</b></a> ·
  <a href="https://khoshkhah.github.io/mapstyle/maps/all.html">Live map</a> ·
  <a href="https://khoshkhah.github.io/mapstyle/get-started/">Get started</a> ·
  <a href="https://khoshkhah.github.io/mapstyle/gallery/">Gallery</a> ·
  <a href="https://khoshkhah.github.io/mapstyle/reference/javascript/">JavaScript API</a>
</p>

---

<p align="center">
  <img src="https://raw.githubusercontent.com/Khoshkhah/mapstyle/main/docs/img/hero.jpg" alt="Monaco drawn by mapstyle: streets, paths, buildings, parks, the port and the sea" width="900">
</p>

## Quick start

```bash
pip install mapstyle "duckosm @ git+https://github.com/Khoshkhah/duckOSM"

curl -LO https://download.geofabrik.de/europe/monaco-latest.osm.pbf
duckosm build --pbf monaco-latest.osm.pbf -o monaco.duckdb \
              -m driving -m walking -m cycling
mapstyle monaco.duckdb          # -> monaco_all.html: one file, opens offline
```

```python
import mapstyle as ms

ms.render_map("monaco.duckdb").save("monaco.html")                    # the whole map
ms.render_map("monaco.duckdb", mode="walking", paths="komoot")        # paths in front
ms.render_map("monaco.duckdb", theme="grey")                          # a quiet map for data
ms.render_map("monaco.duckdb", planner=True).save("planner.html")     # a route planner demo
ms.render_map("monaco.duckdb", dashboard=True).save("dashboard.html") # a dashboard
```

## What you get

- **Every travel mode on one map**, or one brought to the front: `all`, `driving`, `walking`,
  `cycling`; four looks for paths (`google`, `osm`, `komoot`, `cyclosm`); and three **themes**
  for the whole map: `osm` (detailed), `google` (clean), `grey` (quiet, for your data on top).
- **A full base map from the same database**: the sea, land use with openstreetmap.org's textures,
  water, buildings, railways, parking, transit, traffic lights and crossings. No tile server, no API key.
- **Roads drawn right at junctions**: two-way roads as two lanes, bridges over, tunnels under only
  where they really pass under a road, raised walkways, crossings over their street.
- **A route planner demo**: drag a start and an end and see duckOSM's route on the map (routing
  itself is duckOSM's job).
- **A dashboard**: filter by mode, road class and layer, colour by mode, inspect what you click.
- **A JavaScript API**: every page is a [roadstyle](https://github.com/Khoshkhah/roadstyle) page
  (`rsQuery`, `rsFilter`, `rsColor`, …) plus `rsSetModes`, `rsSetKinds` and `rsSetInteraction`;
  3D, Street View and vector tiles for large areas come with it.

<table>
  <tr>
    <td><img src="https://raw.githubusercontent.com/Khoshkhah/mapstyle/main/docs/img/mode_walking.jpg" alt="The walking mode"><br><sub>Walking: paths in front</sub></td>
    <td><img src="https://raw.githubusercontent.com/Khoshkhah/mapstyle/main/docs/img/roads_walkway.jpg" alt="A raised walkway over a roundabout"><br><sub>A raised walkway over a roundabout</sub></td>
  </tr>
  <tr>
    <td><img src="https://raw.githubusercontent.com/Khoshkhah/mapstyle/main/docs/img/planner.jpg" alt="The route planner"><br><sub>The route planner demo</sub></td>
    <td><img src="https://raw.githubusercontent.com/Khoshkhah/mapstyle/main/docs/img/dashboard.jpg" alt="The dashboard"><br><sub>The dashboard</sub></td>
  </tr>
</table>

## How it fits together

| Project | Its part |
|---|---|
| [**duckOSM**](https://github.com/Khoshkhah/duckOSM) | OpenStreetMap → one DuckDB file: the driving, walking and cycling networks and the base-map layers |
| **mapstyle** | reads that file (with `duckdb` only) and styles all of it as one map |
| [**roadstyle**](https://github.com/Khoshkhah/roadstyle) | draws the page: MapLibre GL, the road styling, the JavaScript API |

The look is data: four YAML files in [`src/mapstyle/styles/`](https://github.com/Khoshkhah/mapstyle/tree/main/src/mapstyle/styles/) (travel modes,
path styles, colours, layers). See [Styles](https://khoshkhah.github.io/mapstyle/reference/styles/).

## Command line

```text
mapstyle DB [-o OUT] [--mode {all,driving,walking,cycling}] [--paths {google,osm,komoot,cyclosm}]
            [--theme {osm,google,grey}]
            [--no-layers] [--planner] [--dashboard] [--tiles] [--basemap BASEMAP]
```

## For AI agents

- **Using mapstyle:** the agent skill [`skills/mapstyle/SKILL.md`](https://github.com/Khoshkhah/mapstyle/blob/main/skills/mapstyle/SKILL.md) has the
  install, the one call, the options, the JavaScript API and the traps in one page. In Claude Code:
  `/plugin marketplace add Khoshkhah/mapstyle`, then `/plugin install mapstyle@mapstyle`.
- **The docs as text:** [`llms.txt`](https://khoshkhah.github.io/mapstyle/llms.txt) and
  [`llms-full.txt`](https://khoshkhah.github.io/mapstyle/llms-full.txt) (every page, one file).
- **Changing mapstyle:** [`AGENTS.md`](https://github.com/Khoshkhah/mapstyle/blob/main/AGENTS.md) has the commands and the project's rules.

More: [AI agents](https://khoshkhah.github.io/mapstyle/guides/agents/).

## Development

```bash
git clone https://github.com/Khoshkhah/mapstyle && cd mapstyle
python -m venv .venv && .venv/bin/pip install -e ".[dev,tiles]"
.venv/bin/pytest          # builds a Monaco database with a duckOSM checkout next to this one
```

Tests look for duckOSM in `../duckOSM` (with its `.venv`), or wherever `DUCKOSM_DIR` /
`DUCKOSM_EXE` point; `MAPSTYLE_TEST_DB` reuses a database you already built. Design notes are in
[`docs/design/`](https://github.com/Khoshkhah/mapstyle/tree/main/docs/design/).

## License

MIT. Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL); the
sea from [Overture Maps](https://overturemaps.org/), built from OpenStreetMap's coastline.
