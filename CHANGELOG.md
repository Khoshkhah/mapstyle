# Changelog

All notable changes to **mapstyle** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
