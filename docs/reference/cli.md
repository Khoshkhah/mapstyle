# Command line

```text
mapstyle DB [-o OUT] [--mode {all,driving,walking,cycling}] [--paths {google,osm,komoot,cyclosm}]
            [--theme {osm,google,grey,roadstyle}]
            [--no-layers] [--planner] [--dashboard] [--tiles] [--basemap BASEMAP]
```

| Option | |
|---|---|
| `DB` | a duckOSM `.duckdb` file |
| `-o`, `--out` | the HTML file to write (default: `<db name>_<mode>.html`) |
| `--mode` | which network stands out (default: `all`; `walking` with `--planner`) |
| `--paths` | how walking and cycling paths look (default: `google`) |
| `--theme` | the whole map's colours: `osm` (default), `google`, `grey`, `roadstyle` ([Themes](../guides/themes.md)) |
| `--no-layers` | roads only, no base-map layers |
| `--planner` | add the [route planner](../guides/planner.md) |
| `--dashboard` | a [dashboard](../guides/dashboard.md): filter by mode, class, layer and kind |
| `--tiles` | the roads as vector tiles inside the page, for large areas (needs `mapstyle[tiles]`) |
| `--basemap` | a roadstyle base map to open on, e.g. `blank` (default), `positron`, `satellite` |
| `--export DIR` | write the map as `style.json` + vector tiles + sprite into `DIR` for another app (GeoLibre, RustGIS, QGIS), not a page; needs `--base-url` |
| `--base-url` | with `--export`: the URL where `DIR` is served |

```bash
mapstyle monaco.duckdb
mapstyle monaco.duckdb --mode cycling --paths cyclosm -o cycling.html
mapstyle stockholm.duckdb --tiles --basemap positron
mapstyle monaco.duckdb --export out/monaco --base-url http://localhost:8000/monaco/
```
