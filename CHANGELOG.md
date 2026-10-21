# Changelog

All notable changes to **mapstyle** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Layers `raceway` and `other_ways`**: the OSM ways of `features.streets` that no mode network holds (not in `<mode>.edges`, `private_edges` or
  `edge_id_map`). The page draws its roads from the networks, so these ways were not on the map. `raceway` is the Circuit de Monaco and
  its pit lane, in OSM-Carto's pink. `other_ways` is a thin grey dashed line for small pieces that touch no network, platforms and lifts (Monaco: 10 and 41 ways).
  A layer row has the new key `outside_networks: true`. A database with no mode network skips both layers.
- **A layer `background`** (unticked): the boundary polygon of the database (`main.boundary`), drawn under everything in the land colour of the theme (the `landcover` default). It adds no OSM data. It only fills the places that OSM has no area for, so that a satellite base map does not show through. The sea is drawn over it.
  A layer row can have `schema: main` to read a table outside `features`.
- A line style can have `width_zoom` (px by zoom): the raceway is as wide as a road.

## [0.8.0] — 2026-10-21

### Added
- **A layer `paved`** from duckOSM's new `features.paved` (duckOSM 0.6.0): squares (Place du Casino), pedestrian areas, piers and quays, helipads and
  marketplaces, drawn as filled areas between the waterways and the buildings. In Monaco it fills 83 places that were empty. An older
  database has no such table, and the layer is left out. It is a group of the export, so a row in the GeoLibre plugin.
- Colours for the new `landcover` classes `beach_resort`, `shrubbery` and `zoo` (from `leisure=beach_resort`, `natural=shrubbery`, `tourism=zoo`). The
  swimming pools of `features.water_polygons` are water.

## [0.7.1] — 2026-10-21

### Fixed
- **3D buildings: no block is higher than `max_height`** (200 m, `features.buildings_3d` in `osm_carto.yaml`). A typo such as `building:levels=100` gave a 300 m tower.
- **3D buildings: units.** A `height` in feet (`40 ft`, `40'`) is converted to metres, and a decimal comma (`12,5`) is read.
- **A database with no `tags` column in `features.buildings`** (an older duckOSM) keeps its buildings: they get the height of their kind. Before, the whole buildings layer was skipped.

### Added
- **A building button** under the 2D/3D button (in 0.7.0, not in its notes): it turns the 3D buildings on and off, like the
  "Buildings 3D" row of the Layers box. The docs now name it.

## [0.7.0] — 2026-10-21

### Added
- **Buildings in 3D**: a "Buildings 3D" row in the Layers box and `rsSetBuildings3D(on)` / `rsGetBuildings3D()` (event `ms:buildings3d`).
  Each building is a block above the roads. Its height: `building:levels` x 3 m, else its `height` tag (2 m or more), else a height
  for its kind, else 9 m (`features.buildings_3d` in `osm_carto.yaml`). `load_layers` gives each building a `height` property.
  Design: `docs/design/buildings_3d.md`.
- **`mapstyle.export` has the 3D buildings too**: a layer `ov<i>-3d` (type `fill-extrusion`, group `buildings 3D`) over the roads and under the
  arrows, off at first, with the `height` of each building. The roadstyle GeoLibre plugin shows it as a row.

## [0.6.0] — 2026-10-21

### Added
- **`mapstyle.export`: the map for other apps.** `export_style(db, out_dir, base_url=...)` writes the map as `style.json` + vector
  tiles + sprite (for GeoLibre with the roadstyle plugin, RustGIS, QGIS), and `export_inline(db)` returns one style with the data
  inside (GeoJSON sources, no files), which the GeoLibre plugin makes in the browser with Pyodide. Command line:
  `mapstyle DB --export DIR --base-url URL`. The base map's layers carry the values of `layers.yaml` (colour by kind, outlines,
  dashes, textures, icons, zoom ranges); a layer that is unticked there starts hidden.
- A look for the base map (`export_look`) and the hover and popup of a layer read from the config: the popup columns are in
  `layers.yaml` now.

### Changed
- **Needs roadstyle 0.24.0** (`export_style` and `export_inline`).

## [0.5.1] — 2026-10-20

### Changed
- **Needs roadstyle 0.22.2.** roadstyle sizes the arrows of a tilted (3D) map by the zoom now, so `layers.js` no longer scales the arrow thresholds
  (with both, a tilted map had too many arrows). `render_map(only=True)` reads the stored drawing order with `load_area_levels(subset=True)`.

## [0.5.0] — 2026-10-19

### Fixed
- **The colours of private roads, bus lanes, pedestrian streets and delivery-only streets** show on every road layer: `roads-simple` draws them in pieces
  with no `access`, so its rule is by the road's number (`__rs_edge`).
- **Private roads and bus lanes have arrows** (they are directed roads in `is_directed`, and in roadstyle's `driving_col`); pedestrian streets, being paths, have none.
- **Arrows in 3D**: the road-length thresholds of roadstyle's arrows follow the tilt (a tilted map squashes the pixels per degree), so a 3D map keeps
  as many arrows as the flat one. roadstyle is not changed.

### Changed
- **Layers**: `layers.yaml` has `ticked: false` (the page opens with the layer unticked). Open by default: ocean, landcover, water, waterways,
  buildings; the others (railways, parking, stops, signals, crossings, …) are in the Layers box, unticked.

### Added
- **`render_map(only=True)` / `mapstyle --only`**: the map of one mode with just its `edges` and `private_edges` (a driving map has no walking or
  cycling edges). Not with the planner or the dashboard; the file's stored drawing order (duckosm levels, the level editor) is used. `load_roads(db, only=[...])` reads the same roads.
- **Pedestrian streets and Delivery only** rows in the Roads box (`access` `pedestrian` / `delivery`, from duckOSM's `driving.private_edges`).

### Changed
- **The drawing order is the file's level area** (roadstyle 0.17, duckOSM's `duckosm levels`: one area for all modes, your edits, heads and caps kept
  next to the file): `render_map` reads the numbers and each road end's head and shape from `visualization.edge_levels`; without them roadstyle computes
  the order while it draws. mapstyle gives roadstyle no band any more. A table solved for other roads is an error that says to run `duckosm levels` again.

- **roadstyle 0.18** (`roadstyle>=0.18.0`): the pages are in its simple mode by default (one `roads-simple` layer). The private and bus colours
  go on the fill pieces of `roads-simple` (the full look: the fill layers), by edge id read with `rsQuery`, not by the `access` property: they now
  show on tiled pages (`tiles=True`) too, which do not carry `access`.

### Fixed
- A database without `edge_ref` (an all-NULL column came back as pandas NA, which roadstyle 0.18 cannot test) gives text NULLs.

### Removed
- `render_map(pieces=...)` (it raises an error) and `mapstyle.levels`: a road is fixed by hand in the level area (`roadstyle-levels edit`) instead.
- **Faster:** the `access` of the roads and the dashboard's `modes` column are computed without pandas row loops and a back-fill of the whole table (the same values). A city of 64,000 roads: `render_map` is about 40% faster together with roadstyle's faster pages.

## [0.4.0] — 2026-10-04

### Changed
- **The drawing order of the roads is roadstyle's** (`docs/design/stored_levels.md`). Every road has a casing number (start, main, end) and a fill number; `render_map` reads them from `visualization.edge_levels`
  when the file has them (`duckosm levels`, duckOSM 0.2.0), else roadstyle computes them while it renders. A stored table computed for other roads or with other options is an error that says to run `duckosm levels` again.
  `tiles=True` now draws by the numbers too. Needs roadstyle 0.14.0 (0.13.1 for the numbers; 0.14.0 also hides a road's arrows and street names with the road).
- **The band given to roadstyle is complete**: the level from the tags (the `layer`, else a bridge 1, a tunnel -1), a path's sidewalk -1 and crossing 1. It was only the sidewalks and crossings, so tunnels and bridges were band 0
  wherever roadstyle computed the numbers.

### Removed
- mapstyle's own solver (`mapstyle.node_levels`), the argument `order` (it raises an error), the `solver` extra, and the prototype scripts `scripts/node_levels*.py`. `pieces=True` stays.

## [0.3.0] — 2026-10-03

### Added
- **The drawing order of the roads is solved** (`render_map(order=True)`, the default; `docs/design/node_levels.md`,
  `mapstyle.node_levels`). Each road gets an interval: where its casing and its fill are drawn. Roads that
  share a node have intersecting intervals (no ring at a joint), and a road that passes over another without
  a shared node is drawn after it. Solved exactly with OR-Tools when installed (`pip install mapstyle[solver]`),
  else by a heuristic; the county of Stockholm takes 11 s. Needs a roadstyle with `casing_level_col` /
  `fill_level_col`. `order=False` gives roadstyle's bands; `tiles=True` is not supported yet.
- The dashboard panel: Filter in cards (Roads; the layers grouped by meaning, with all / none), one row per layer with a ⚙ for its switches and kinds, the legend dropped when colouring by class (Road type is the legend), modes as chips.
- The planner: labelled Start / End markers, their positions, swap, a panel in cards; its default look is `all`.

### Changed
- A one-way street's walking-only reverse edge comes before the street's own edge in `load_roads`, so a click, Street View and the planner get the directed edge.
- (Older, now opt-in with `pieces=True, order=False`.)
- **A road with a level is drawn at ground level except where it passes over or under a road**
  (`docs/design/levels_plan.md`). A road with a `layer` tag and no bridge tag, and a tunnel, is cut for
  drawing into ground pieces and the stretch that really crosses another road (lines cross, no
  shared node, a level apart), 4 m clear of that road's drawn width. The stretch is a square-ended
  piece in its own band (roadstyle's `band_col`, `cap_col`), so every joint is at ground level and
  its casings merge: no ring or broken casing where a raised path, a plaza edge or a tunnel meets
  ground roads. The database and `edge_id` are unchanged; the extra pieces are appended rows marked
  `_piece`. `render_map(pieces=False)` turns it off; the dashboard and planner count and follow
  edges, not pieces. Needs a roadstyle with `cap_col` (square ends are round on an older one).
  Replaces the first attempt (`level_band`, a band per whole edge, `layer_bands.md`).

## [0.2.0] — 2026-10-01

### Added
- **Themes:** `theme=` / `--theme` gives the whole map its colours: `osm` (today's, the default),
  `google` (clean: light land, white streets, yellow main roads, light blue water) and `grey` (a
  quiet map for your data on top). A theme is a short YAML in `styles/themes/`: a background, a
  transform for every colour of the `osm` look, and the colours that differ. Your own colours
  (`rsColor`, colour options, the planner's route) are never themed.

- **Private roads and bus lanes** (duckOSM's `private_edges`): drawn grey and muted blue, with
  **Private roads** / **Bus lanes** rows in the Roads box and switches on the dashboard; which ones
  depend on the map's mode. `load_roads` reads them (`access_driving` / `_walking` / `_cycling`);
  `rsSetAccess(kind, on)`, `rsGetAccess()`, `RS_ACCESS`. Never routed or snapped to.
- **The route planner has the Roads box** (classes, bridges, tunnels, private roads, bus lanes).

### Fixed
- `layers.js` waits for the roads to be loaded, not only the map style (the restricted-road rows
  could miss them).
- An empty colour or texture list (a theme can empty one) no longer breaks the page.

## [0.1.0] — 2026-10-01

The first release: a whole OpenStreetMap map in one offline HTML page, from a
[duckOSM](https://github.com/Khoshkhah/duckOSM) database, drawn by
[roadstyle](https://pypi.org/project/roadstyle/) (0.10 or later).

### Added
- **`render_map(db, mode, layers, planner, dashboard, interaction, paths, **kwargs)`** and the
  `mapstyle` command: every road of the database over its base-map layers, in one page.
- **Travel modes** `all` (default), `driving`, `walking`, `cycling`: which network stands out; and
  **path styles** `google` (default), `osm`, `komoot`, `cyclosm`.
- **The base map** from duckOSM's `features.*`: the sea (`features.ocean`), land use with
  openstreetmap.org's textures, water, buildings, railways, parking, transit, traffic signals and
  crossings, with icons and zoom ranges. Each layer can be hidden, made clickable, and filtered by
  kind.
- **Roads drawn right at junctions** (with roadstyle 0.10): two-way roads as two lanes and one-way
  streets and paths as one line (`is_directed`), crossings over their street and sidewalks under
  it, tunnels and roads with only a `layer` tag drawn below ground only where they pass under a
  road.
- **A route planner** (`planner=True`): drive, walk, cycle, or walk + drive; between the two
  points, with an off-road walk within a set radius that never crosses a road, the first and last
  edges by the part travelled, turn-by-turn directions, total time and distance. The same answers
  as duckOSM's `route_points()` / `route_multimodal_points()`.
- **A dashboard** (`dashboard=True`): filter by mode, road class and layer, colour by mode, inspect
  what you click.
- **A JavaScript API** on every page: roadstyle's, plus `rsSetModes`, `rsSetKinds`,
  `rsSetInteraction` and the `ms:ready` event.
- `load_roads(db)` and `load_layers(db)` for the data alone; the look as data in
  `src/mapstyle/styles/*.yaml`.
- For AI agents: a skill (`skills/mapstyle/SKILL.md`), a Claude Code plugin, `llms.txt` on the
  [docs site](https://khoshkhah.github.io/mapstyle/), and `AGENTS.md`.
