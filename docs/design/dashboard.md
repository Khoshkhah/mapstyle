# A dashboard: every mode on one page, filtered by mode and category

**Status:** approved 2026-09-30 and implemented (`render_map(dashboard=True, interaction=)`,
`mapstyle --dashboard`, `layers.js`, `dashboard.js`; browser check `scripts/dashboard_check.py`).
**roadstyle and duckOSM are not changed.**

## Goal

One page for exploring a duckOSM db: all modes' roads and the feature layers, a side panel to
filter by **mode** (driving / walking / cycling) and by **category** (road class, feature layer),
colour by class or by mode, numbers, search, and what you clicked.

## What roadstyle already has

`rs.render_report(gdf, **render_edges keywords)` is a page with a side panel: summary numbers,
*Colour by* + legend (from `color_options`), a *Filter* with a checkbox per overlay layer
(`rsSetOverlay`) and per road class (`rsSetClasses`), search, and the clicked road's fields. It takes
every `render_edges` keyword, so mapstyle's palette, `settings=`, overlays and `layers.js` work with it.

Missing: filtering by mode, and colouring by mode.

## Proposal

```python
ms.render_map(db, dashboard=True)       # the report page with mapstyle's roads, layers and mode panel
```
```bash
mapstyle monaco.duckdb --dashboard      # -> monaco_dashboard.html
```

1. **The page is roadstyle's report** (`render_report` instead of `render_edges`), with mapstyle's
   roads (all modes), mode style and feature layers.
2. **Filter by mode:** three check boxes, Driving / Walking / Cycling, with a count each, added at
   the top of the report's *Filter*. The map shows the roads any ticked mode can use, from the flags
   `load_roads` already gives every road; roadstyle applies it together with the class boxes, so
   "walking + only footways and steps" works. The boxes are UI over `rsSetModes` (below).
3. **Filter by category**, at three levels:
   - road classes (footway, primary, …): the report's own boxes, `rsSetClasses` (roadstyle);
   - whole layers (buildings, crossings, …): the report's own boxes, `rsSetOverlay` (roadstyle);
   - the kinds inside a layer (only parks and grass in landcover, only restaurants among the POIs):
     a list with counts that opens under each layer's box, UI over `rsSetKinds` (below).
4. **Colour by:** *Road class* (the mode's look) and *Modes*: which modes can use a road, one
   colour per combination (all three grey, walking only green, driving only red, cycling only blue,
   and the mixed ones), from `color_options`, so it switches in the page with a legend.
5. **Look:** the walking style by default (every path drawn), `mode=` picks another, as for the
   planner.
6. **Clickable / tooltip / popup per layer.** Like the mode filter, these are **library functions
   on every mapstyle page**, not dashboard code; the dashboard's switches are UI over them.

### The JavaScript API mapstyle adds

Defined the way roadstyle defines its own (`docs/reference/javascript.md` there): `rs*` functions on
`window` that take an overlay label or index like `rsSetOverlay`, each firing an `rs:*` event, so a
mapstyle page reads as one API. mapstyle defines one only when the page doesn't already have it: if
roadstyle ever adds the same function, roadstyle's wins.

| function | does | fires |
|---|---|---|
| `rsSetModes(list)` | show the roads any of these modes can use (`["walking", "cycling"]`); `null` = all. Combines with `rsSetClasses`; it uses `rsFilter` on the roads, so a later `rsFilter(ids)` replaces it | `rs:filterchange` (`modes`) |
| `rsGetModes()` | the modes shown, or `null` for all | |
| `rsSetInteraction(labelOrIndex, {clickable?, tooltip?, popup?})` | switch a feature layer's clicks, hover tooltip and click popup; keys left out keep their state | `rs:interactionchange` (`overlay`, `clickable`, `tooltip`, `popup`) |
| `rsGetInteraction(labelOrIndex)` | `{clickable, tooltip, popup}` of a layer | |
| `rsSetKinds(labelOrIndex, list)` | show only these `kind`s of a feature layer (`["park", "grass"]`); `null` = all | `rs:filterchange` (`overlay`, `kinds`) |
| `rsGetKinds(labelOrIndex)` | the kinds shown, or `null` for all | |
| `RS_KINDS` | `{layer label: {kind: count}}` | |

```python
ms.render_map(db, interaction={"landcover": {"clickable": True}, "crossings": {"tooltip": False}})
```

`interaction=` sets the state the page opens with (the defaults stay as today: no layer tooltips;
landcover, water and lines not clickable; the other layers clickable with a popup). How it works
with roadstyle unchanged: every layer is built clickable with a tooltip (`name`, `kind`), so each
switch can go both ways; the functions then set what roadstyle reads on every click and hover,
`RS_OVERLAYS[i].interactive` (clicks) and `.tooltip` (hover). roadstyle opens a popup for every
clicked layer, so `popup: false` closes it as it opens (on the `rs:select` roadstyle sends right
after); the click still selects and still sends `rs:select`.

`rsSetKinds` adds its `kind` filter to each of the layer's own filters (the texture layer keeps
its own), so it doesn't use roadstyle's `rsFilter`, which would replace them.

**Roads are always clickable**; their tooltip and popup are chosen when the page is built
(`road_tooltip=`, `road_popup=`, roadstyle's keywords).

The table goes into mapstyle's README (and its docs site later), in roadstyle's format.

mapstyle's part: the functions above in `layers.js` (every mapstyle page), `color_options`, and
one short script (`dashboard.js`) that adds the mode box and the per-layer switches to the report's
panel. That script uses the report's element ids (`#rp-ovs`), which are
roadstyle's page, not its API: if roadstyle renames them, the mode box moves to the page's corner
(it looks for the panel and falls back).

`dashboard=True` with `planner=True` is an error for now: both are a panel on the right.

## Not in this note

Charts, a dashboard across several areas.

## Checks

- Tests: the page is the report (its panel is there), carries the *Modes* colour option and the
  mode script; `dashboard` + `planner` raises; `interaction=` reaches the page; `rsSetModes` /
  `rsSetInteraction` / `rsSetKinds` are defined on a plain `render_map` page too.
- In a browser (Monaco): unticking Driving leaves only walking / cycling roads; with Walking ticked
  and only `steps` among the classes, only steps show; *Colour by → Modes* recolours with a legend;
  a layer box hides its layer (icons too); only `park` ticked under landcover leaves only parks,
  with their texture; a layer's clickable / tooltip switches stop its clicks /
  hover tooltips while the roads under it stay clickable.
