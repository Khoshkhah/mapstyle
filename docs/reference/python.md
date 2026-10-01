# Python API

```python
import mapstyle as ms
```

## `render_map`

```python
ms.render_map(db, mode=None, layers=True, planner=False, dashboard=False,
              interaction=None, paths="google", **kwargs)
```

The whole map of a duckOSM database as one page. Returns roadstyle's map object: `.save(path)`
writes the HTML file, `.html` is the page as a string, and in Jupyter it shows itself.

| Argument | Default | |
|---|---|---|
| `db` | | path of a duckOSM `.duckdb` file |
| `mode` | `"all"` (`"walking"` with `planner=True`) | which network stands out: `all`, `driving`, `walking`, `cycling` ([guide](../guides/modes.md)) |
| `layers` | `True` | the base-map layers: `True` = all, a list of names, or `False` = roads only ([guide](../guides/base-map.md)) |
| `paths` | `"google"` | how paths look: `google`, `osm`, `komoot`, `cyclosm` |
| `planner` | `False` | add the [route planner](../guides/planner.md) |
| `dashboard` | `False` | make it a [dashboard](../guides/dashboard.md) |
| `interaction` | `None` | how a layer opens: `{"crossings": {"clickable": True, "tooltip": True, "popup": False}}` |
| `**kwargs` | | passed to [`roadstyle.render_edges`](https://khoshkhah.github.io/roadstyle/reference/parameters/): e.g. `tiles=True`, `basemap="positron"`, `view_3d=True`, `arrows=False` (not `palette` or `settings`: the mode sets those) |

```python
ms.render_map("tartu.duckdb", mode="cycling", tiles=True).save("tartu.html")
ms.render_map("monaco.duckdb", layers=["buildings", "water"], basemap="positron")
```

## `load_roads`

```python
roads = ms.load_roads(db)     # a GeoDataFrame
```

One row per `edge_id` over the database's mode networks, with `driving` / `walking` / `cycling`
flags (which modes can use the edge), the OSM tags mapstyle draws by (`highway`, `name`, `bridge`,
`tunnel`, `layer`, `oneway`, …) and duckOSM's `walk_type` (sidewalk, crossing, …). `edge_id` and
`osm_id` are strings: duckOSM's hashed ids can pass 2⁵³, more than JavaScript numbers hold.

## `load_layers`

```python
fcs = ms.load_layers(db)                   # {layer name: GeoJSON FeatureCollection}
fcs = ms.load_layers(db, ["buildings"])    # a subset
```

The base-map layers of `styles/layers.yaml`, in drawing order, each with `kind`, `name` and the
OSM id per feature. A layer whose `features.*` table is missing is skipped with a logged hint.

## `MODES`

`("driving", "walking", "cycling")`: the travel modes of a duckOSM database.
