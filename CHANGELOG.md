# Changelog

All notable changes to **mapstyle** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
