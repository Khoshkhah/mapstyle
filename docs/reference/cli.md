# Command line

```text
mapstyle DB [-o OUT] [--mode {all,driving,walking,cycling}] [--paths {google,osm,komoot,cyclosm}]
            [--no-layers] [--planner] [--dashboard] [--tiles] [--basemap BASEMAP]
```

| Option | |
|---|---|
| `DB` | a duckOSM `.duckdb` file |
| `-o`, `--out` | the HTML file to write (default: `<db name>_<mode>.html`) |
| `--mode` | which network stands out (default: `all`; `walking` with `--planner`) |
| `--paths` | how walking and cycling paths look (default: `google`) |
| `--no-layers` | roads only, no base-map layers |
| `--planner` | add the [route planner](../guides/planner.md) |
| `--dashboard` | a [dashboard](../guides/dashboard.md): filter by mode, class, layer and kind |
| `--tiles` | the roads as vector tiles inside the page, for large areas (needs `mapstyle[tiles]`) |
| `--basemap` | a roadstyle base map to open on, e.g. `blank` (default), `positron`, `satellite` |

```bash
mapstyle monaco.duckdb
mapstyle monaco.duckdb --mode cycling --paths cyclosm -o cycling.html
mapstyle stockholm.duckdb --tiles --basemap positron
```
