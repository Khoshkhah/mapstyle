# Private roads, bus lanes, and the planner's Roads box

**Status:** approved by Kaveh 2026-10-01 ("go ahead") and implemented. The two gaps before
`duckosm viz` / `duckosm route-map` can call mapstyle (memory: duckosm-switch-parity-gaps;
agreed with Kaveh in a duckOSM session).

## Problem

1. duckOSM keeps roads you may not use in `<mode>.private_edges`: private roads
   (`access = 'private'`: driveways, gated streets) and, in driving, bus-only roads and bus lanes
   (`access = 'bus'`, e.g. the contraflow bus lane of Boulevard des Moulins, edge
   1964280132851416298). duckOSM's own maps draw them grey and muted blue, each with a row in the
   Roads box. mapstyle never reads `private_edges`: they aren't on its map.
2. The planner page has no Roads box (`render_map` turns roadstyle's `filter_control` off).

Monaco: driving 196 private + 18 bus, walking 154 private, cycling 133 private. But on mapstyle's
one map of every mode they overlap with the usable roads: **all 18 bus edges are usable by bikes
or on foot** (cyclists may use the bus lane), and 91 of the 243 private edges are private in one
mode and open in another (private for cars, walkable). duckOSM's maps show one mode each, so
there it's simple.

## Design

- **`load_roads` reads `private_edges` too**, one row per `edge_id` as today, with a column per
  mode saying the edge's restriction there (`access_driving`, … : `private` / `bus` / null). The
  mode flags (`driving`, …) keep meaning "this mode can use it".
- **What the page shows as restricted depends on its mode** (one `access` column on the page, for
  the popup and the colour):
  - `driving` / `walking` / `cycling`: the edge's restriction in that mode, when that mode can't
    use it (Monaco driving: 196 private grey, 18 bus blue, as duckOSM's driving map);
  - `all`: **bus** when it is a bus road or lane for cars (all 18, though bikes may use them:
    it is still a bus lane), **private** when no mode can use it (152); the 91 private for one
    mode but open to another are drawn as the roads they are for the others.
- **Colours**, duckOSM's: private `#c8c8c8`, bus `#9db8d9`, painted over the road colours of every
  theme (again after `rsColor`, as duckOSM does). Your own colours (`rsColor`) still win.
- **Rows "Private roads" and "Bus lanes"** in the Roads box after Bridges / Tunnels, each with its
  swatch, hiding and showing them; only when the map has such roads. On the dashboard, the same
  two switches in its Modes box. They combine with `rsSetModes` (both are one `rsFilter`).
- **Never routed or snapped to:** the planner's graphs and candidates come from `<mode>.edges`
  only, so a restricted road can't start, end or carry a route. The walk to the road may still
  cross it (it is not a road you could join).
- **The planner page gets its Roads box** (roadstyle's, under it the Layers box, as on every other
  page): hiding a class hides it on the map, not from routing (as duckOSM's planner).
- In `layers.js` (it already owns `rsSetModes` and the boxes), roadstyle unchanged.

## Checks

- Tests: `load_roads` has the 152 + 91 private and 18 bus rows with the right per-mode columns;
  the page's `access` per mode (driving 196 / 18; all 152 / 18); the planner page has
  `filter_control` on; no restricted edge is a planner candidate.
- Browser: Boulevard des Moulins' bus lane blue in driving and all; the two rows hide and show
  them, together with `rsSetModes`; the colours survive `rsColor` and the themes; the planner's
  Roads box hides classes; no page errors on the five page kinds. Previews before pushing.
