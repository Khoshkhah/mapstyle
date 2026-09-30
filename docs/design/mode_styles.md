# Styles for each travel mode (walking, cycling), and routes you can see

**Status:** proposal, for sign-off before implementation. **roadstyle is not changed** (Kaveh,
2026-09-30): everything here is done in mapstyle, with roadstyle's existing `settings=`,
`palette=`, `include=`, `color_options` and the page's `window.map`.

## Problem

roadstyle's palettes were made for **driving** networks. On a walking or cycling network (duckOSM's
`viz` and `route-map`), the paths people walk and cycle on almost disappear:

- In every palette, `footway`, `path` and `cycleway` are 1.2–1.5 px dashed lines at the bottom of
  the draw order; in `mono` they're light grey (`#ABABAB`). At city zoom they vanish.
- `steps`, `corridor`, `platform` and `bridleway` (and `pedestrian` in `mono`) are in no palette, so
  they fall back to the `unclassified` style: a flight of steps is drawn like a road.
- Highlighting a set (`rsColor`) changes only the fill colour and keeps the class width, so a route
  along a footway stays a thin dashed line (seen in duckOSM's `route-map`: walking legs nearly invisible).

## Proposal

### 1. A palette per travel mode, owned by mapstyle

roadstyle settings can add palettes ("a new name adds a palette", per road class, with `fill`,
`casing`, `width`, `dash`, …) and change the draw order (`roads.z_order`). mapstyle ships them as
data (next to `styles/osm_carto.yaml`) and passes them with `settings=` and `palette=`:

| Mode | The network you use is drawn | Roads for cars |
|---|---|---|
| `driving` | the carto look | as today |
| `walking` | footway, pedestrian, path, steps, corridor, platform, living_street: solid, ~3 px, on top; steps with their own dash | thinner and lighter, underneath |
| `cycling` | cycleway: solid, ~3 px, cycling blue; roads by class as usual | footways (where you push the bike) thin and dashed |

Every OSM path class (steps, pedestrian, corridor, platform, bridleway) gets an entry, so nothing
falls back to a road look.

```python
ms.render_map("monaco.duckdb", mode="walking")     # -> rs.render_edges(..., palette="ms_walking", settings=...)
```

### 2. Switching mode in the page

`msSetMode("walking")`: mapstyle's own JS. Options, to settle while building (check roadstyle's
layer ids in a built page first):

- a) `rsFilter` to the mode's edges (the `driving` / `walking` / `cycling` flags) plus
  `window.map.setPaintProperty` on roadstyle's road layers with the mode's widths and colours;
- b) one page per mode, linked (simplest; no live switch).

### 3. Routes you can see on any road

roadstyle's `rsColor` keeps the class width. mapstyle's route planner draws the route's width itself:
a `window.map` line-width expression on roadstyle's road layers keyed on the route's feature ids
(still recolouring the road, not drawing a second line over it), or it relies on the mode palette
(1) making footways wide enough.

## Checks

- Tests: every mode palette covers every class in the walking and cycling networks; `mode=` reaches
  `render_edges`.
- In a browser (snapshots, before and after): Monaco walking and cycling at city zoom, and a route
  along footways.
