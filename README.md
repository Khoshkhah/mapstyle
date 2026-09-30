# mapstyle

A [duckOSM](../duckOSM) database as one full, interactive HTML map: the roads styled for a travel
mode (driving / walking / cycling) over the base map duckOSM builds into `features.*` (landcover,
water, buildings, railways, POIs, crossings). The page is a [roadstyle](../roadstyle) page, so its
whole JavaScript API, 3D, Street View and vector tiles come with it.

```bash
pip install -e ../roadstyle -e .          # + '.[tiles]' for --tiles
mapstyle monaco.duckdb                    # -> monaco_all.html: the whole map
mapstyle monaco.duckdb --mode walking     # the walking network on top, roads for cars faded
mapstyle monaco.duckdb --paths osm        # paths as on openstreetmap.org (default: google)
mapstyle tartu.duckdb -o tartu.html --tiles --basemap positron
mapstyle monaco.duckdb --planner          # + a route planner: drag start and end (Drive, Walk, Cycle, Walk + drive)
mapstyle monaco.duckdb --dashboard        # a dashboard: filter by mode, road class, layer and kind
```

```python
import mapstyle as ms

ms.render_map("monaco.duckdb", mode="cycling").save("monaco.html")
ms.render_map(db, "walking", layers=["buildings", "crossings"])   # a subset of the feature layers
ms.render_map(db, layers=False, tiles=True)                       # roads only, as vector tiles
roads = ms.load_roads(db)      # one row per edge_id, with driving / walking / cycling flags
fcs = ms.load_layers(db)       # {layer name: GeoJSON FeatureCollection}
```

`mode`: `all` (default), `driving`, `walking`, `cycling`: which network stands out. `paths`: how
paths look (`styles/paths.yaml`: `google` default, `osm`, `komoot`, `cyclosm`). The base map is
`blank` (the db's own map; duckOSM has no sea yet, so a coast's sea is land-coloured); the raster
maps are in the switcher. Every other keyword goes to `roadstyle.render_edges`. A db built without `features.*` gives
roads only, with a logged hint. `interaction={"crossings": {"tooltip": True}}` sets how a layer opens.

## JavaScript

Every mapstyle page is a roadstyle page, so roadstyle's whole API works (`rsQuery`, `rsFilter`,
`rsSetClasses`, `rsSetOverlay`, `rs:select`, … see its `docs/reference/javascript.md`). mapstyle adds,
in the same style (and only where the page has none yet):

| function | does | fires |
|---|---|---|
| `rsSetModes(list)` | show the roads any of these modes can use (`["walking", "cycling"]`); `null` = all. Combines with `rsSetClasses`; it uses `rsFilter` on the roads, so a later `rsFilter(ids)` replaces it | `rs:filterchange` (`modes`) |
| `rsGetModes()` | the modes shown, or `null` for all | |
| `rsSetKinds(labelOrIndex, list)` | show only these `kind`s of a feature layer (`["park", "grass"]`); `null` = all | `rs:filterchange` (`overlay`, `kinds`) |
| `rsGetKinds(labelOrIndex)` | the kinds shown, or `null` for all | |
| `RS_KINDS` | `{layer label: {kind: count}}` | |
| `rsSetInteraction(labelOrIndex, {clickable?, tooltip?, popup?})` | switch a feature layer's clicks, hover tooltip and click popup; keys left out keep their state. Roads are always clickable | `rs:interactionchange` (`overlay`, `clickable`, `tooltip`, `popup`) |
| `rsGetInteraction(labelOrIndex)` | `{clickable, tooltip, popup}` of a layer | |

`ms:ready` fires once they are all defined (the feature layers' images load first).

- The look is data: `src/mapstyle/styles/modes.yaml` (which network stands out, per mode),
  `paths.yaml` (path styles),
  `osm_carto.yaml` (road colours, feature-layer styles), `layers.yaml` (which `features.*` layers,
  draw order, filters).
- Design: [`docs/design/`](docs/design/); work plan: [`docs/PLAN.md`](docs/PLAN.md).
- Tests: `.venv/bin/pytest` (builds a Monaco db with `../duckOSM`); browser checks, by hand:
  `scripts/planner_check.py`, `scripts/dashboard_check.py`.
