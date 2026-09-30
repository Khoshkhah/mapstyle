# mapstyle

A [duckOSM](../duckOSM) database as one full, interactive HTML map: the roads styled for a travel
mode (driving / walking / cycling) over the base map duckOSM builds into `features.*` (landcover,
water, buildings, railways, POIs, crossings). The page is a [roadstyle](../roadstyle) page, so its
whole JavaScript API, 3D, Street View and vector tiles come with it.

```bash
pip install -e ../roadstyle -e .          # + '.[tiles]' for --tiles
mapstyle monaco.duckdb --mode walking     # -> monaco_walking.html
mapstyle tartu.duckdb -o tartu.html --tiles --basemap positron
```

```python
import mapstyle as ms

ms.render_map("monaco.duckdb", mode="cycling").save("monaco.html")
ms.render_map(db, "walking", layers=["buildings", "crossings"])   # a subset of the feature layers
ms.render_map(db, layers=False, tiles=True)                       # roads only, as vector tiles
roads = ms.load_roads(db)      # one row per edge_id, with driving / walking / cycling flags
fcs = ms.load_layers(db)       # {layer name: GeoJSON FeatureCollection}
```

Every other keyword goes to `roadstyle.render_edges`. A db built without `features.*` gives
roads only, with a logged hint.

- The look is data: `src/mapstyle/styles/modes.yaml` (per-mode palettes and road widths),
  `osm_carto.yaml` (road colours, feature-layer styles), `layers.yaml` (which `features.*` layers,
  draw order, filters).
- Design: [`docs/design/`](docs/design/); work plan: [`docs/PLAN.md`](docs/PLAN.md).
- Tests: `.venv/bin/pytest` (builds a Monaco db with `../duckOSM`).
