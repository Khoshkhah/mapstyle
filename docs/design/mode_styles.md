# Styles for each travel mode (walking, cycling), and routes you can see

**Status:** proposal, for sign-off before implementation. **roadstyle is not changed** (Kaveh,
2026-09-30): everything here is done in mapstyle, with roadstyle's existing per-call `settings=`
(palettes, `roads`, `config`), `palette=` and the page's `window.map`.

**Update 2026-09-30, after trying it (Kaveh):** the look of the paths is now its own choice, the
*path style*, separate from the mode:

- `render_map(db, mode, paths=...)`, `mapstyle --mode ... --paths ...`. Modes (`styles/modes.yaml`):
  **`all`** (the whole map: every network at its own width, none on top, nothing faded; the
  default), `driving`, `walking`, `cycling` (that network in the path style's `em` width group, on
  top; the roads for cars fade; every road one centred line, roadstyle's `offset_frac=0`).
- Path styles (`styles/paths.yaml`): **`google`** (default: thin solid white paths with a grey
  edge, green cycleways), `osm` (openstreetmap.org: dotted salmon / blue), `komoot` (bold colours
  with a white halo), `cyclosm` (solid blue cycleways, thin dark dashed footways). Kaveh compared
  them on the whole map and liked google and osm; google is the default because a highlighted
  route recolours a solid line completely, a dotted one only in its dots.
- Fixed on the way: a class the base palette lacks (pedestrian) inherited footway's dash and drew
  as broken grey blocks; see-through car roads showed their dark casing (now mixed with white).
- The planner's default stays `walking` (a walking leg must show).

## Problem

roadstyle's palettes were made for **driving** networks. On a walking or cycling network (duckOSM's
`viz` and `route-map`), the paths people walk and cycle on almost disappear. In the web renderer:

- Widths come from `roads.width` by `roads.group`, not from the palette's `width` (that one is
  folium/lonboard only). `footway`, `path`, `cycleway`, `steps`, `corridor` and `bridleway` are in
  the `path` group: 0.4 px at z12 up to 3 px at z19.
- Dashed classes (footway, path, cycleway in every palette) are always drawn under the solid road
  casing (`render_web.py`), whatever `z_order` says. In `mono` they are also light grey (`#ABABAB`).
- `steps`, `corridor`, `platform` and `bridleway` (and `pedestrian` in `carto` and `mono`) are in
  no palette, so they take the `unclassified` colours and casing. `platform` is also missing from
  `roads.group`, so it gets *residential* width: a platform is drawn like a road.
- Highlighting a set (`rsColor`, `rsHighlight`) changes only the colour and keeps the class width, so
  a route along a footway stays a thin line (seen in duckOSM's `route-map`: walking legs nearly
  invisible).

## Proposal

### 1. A settings set per travel mode, owned by mapstyle

A mode is one roadstyle `settings=` dict, shipped as data next to `styles/osm_carto.yaml`, with
two parts, because the width and the colour live in different places:

- `palettes.ms_<mode>`: a new palette (colour, casing, dash) with an entry for every OSM path
  class (steps, pedestrian, corridor, platform, bridleway), so nothing falls back to `unclassified`;
- `roads`: a width group for the mode's own network (`width`, `casing_ratio`), `group` entries
  mapping its classes to it (including `platform`), and `z_order` putting them on top.

(`config.minzoom` would hide paths at city zoom, but it is opt-in, `minzoom=True`; mapstyle leaves
it off.)

| Mode | The network you use is drawn | Roads for cars |
|---|---|---|
| `driving` | the carto look | as today |
| `walking` | footway, pedestrian, path, steps, corridor, platform, living_street: **solid** (a dashed class always draws under road casings), ~3 px at city zoom, on top; steps in their own colour | thinner and lighter, underneath |
| `cycling` | cycleway: solid, ~3 px, cycling blue; roads by class as usual | footways (where you push the bike) thin and dashed |

```python
ms.render_map("monaco.duckdb", mode="walking")
# -> rs.render_edges(..., palette="ms_walking", settings=MODES["walking"])
```

`settings=` applies to that render only and rebuilds roadstyle's width tables, so modes don't leak
into each other.

### 2. One page per mode

Each mode is its own page, linked to the others. No live switch in the page: in roadstyle the width
expression is built in Python and the dash layers exist only for the dash values present at render
time, so switching mode live would mean rebuilding both in JS. (Colours alone could switch live
through `color_options` + `rsSetColorField`; that's not enough for a mode.) Add a live switch when
someone needs one.

### 3. Routes you can see on any road

First rely on (1): with footways ~3 px, a route recoloured with `rsColor` should be visible. If it
isn't, the route planner widens the route's roads itself: `window.map.setPaintProperty` on
roadstyle's road layers with a `line-width` keyed on the route's feature ids (still recolouring the
road, not drawing a second line over it). MapLibre needs the zoom `interpolate` at the top level, so
the `case` on the route ids goes inside every zoom stop, not around roadstyle's expression.

## Checks

- Tests: for every mode, the palette and `roads.group` cover every class in the walking and
  cycling networks; `mode=` reaches
  `render_edges` with the mode's palette and settings.
- In a browser (snapshots, before and after): Monaco walking and cycling at city zoom, and a route
  along footways.
