# Suggestions for roadstyle (from the roads-as-overlays experiment)

**Status:** suggestions only, 2026-10-04. Nothing here is built, and roadstyle is not changed (Kaveh's rule: mapstyle
uses roadstyle from outside; lanestyle's `AGENTS.md` allows one roadstyle change, already used for the metre widths).
They come from [roads_as_overlays.md](roads_as_overlays.md), where the roads' fill was drawn by edge-attached overlays
(`road_fill=False`), the way lanestyle draws lanes. Each one names what was seen, what is proposed, and what was **not** checked.
Numbers are from Monaco (12,941 edges), measured in headless Chromium with software WebGL, so only ratios mean something.

## 1. An overlay that draws edges of the roads' own source (no copy of the geometry)

- **Seen:** an edge overlay is its own GeoJSON source: the edge's geometry is copied in and joined to the road by `edge_id`.
  For all roads that is +12,941 features (40,286 to 53,227, +32 %) and +1.5 MB, and an `edge_id` that is not among the roads is an error.
- **Proposal:** an overlay that selects edges of the roads' source (by a filter on a property, or by ids) and takes its look
  from the overlay (`color`, `width`, `opacity`, `dash`, by `order`). No data of its own; the edge's place in the drawing order is
  already known.
- **Helps:** any overlay that restyles or marks edges (a highlighted route, colour by flow, a lane look on chosen roads), and
  lanestyle where its items are one per edge.
- **Not checked:** how the page's click, hover and `rsFilter` would treat such a layer; whether the roads' source can be filtered per layer
  the way the casing layers already filter it (it can: they use `filter` on the same source).

## 2. Fewer layers: `line-sort-key` for the order

- **Seen:** an edge overlay makes one map layer for each `(fill number, order)` that occurs, for each kind of layer. The experiment's
  page had 239 layers against 129 (+85 %), and 34.2 against 57.5 frames per second at zoom 17 (software WebGL, one run).
- **Proposal:** one layer per fill number and kind, with `order` as the layer's `line-sort-key` / `symbol-sort-key` (MapLibre orders
  the features of one layer by it). The result is the same global order, with fewer layers.
- **Helps:** every edge overlay; lanestyle most, since it has many orders (connector, lane, lines, zebra, arrows, names).
- **Not checked:** `fill` and `circle` layers have no sort key in MapLibre (a polygon overlay would still need a layer for each order);
  whether the cost is in the layer count or in the features (my test changed both at once).

## 3. Overlay lines with a per-feature width and a line offset

- **Seen:** `overlay_styles.md` lists "a different width for each feature (a column)" as not yet. An `Overlay` has one `width`,
  and no `line-offset`. The two lanes of a two-way street (each 0.6 of the width, shifted 0.28 of it) could not be drawn, so both
  directions lay on the centre line and the fill was about 2 px narrower than roadstyle's own (see the note above).
- **Proposal:** `width_col` (a property holding the width, px or metres) and `offset_col` or `offset_m` (a line offset).
- **Helps:** lanes or lane lines as lines, not only as polygons buffered in Python; and a faithful twin look from overlays.
- **Not checked:** whether a data-driven width fits the zoom-exact metre expression (`_wm_width_expr`).

## 4. Public functions for what an outside library needs to know

- **Seen:** to draw the fill I had to use `render_web._width_expr` and `render_web.ROAD_Z` (private), call
  `build_styler(...).resolve_frame(roads)` for each edge's colour and opacity, and guess which edges roadstyle fades as tunnels
  (my first version used the `tunnel` tag and got 109 `building_passage` edges wrong; the script now reads the faded group from the opacity).
  Nothing tells an outside caller which edges roadstyle treats as a two-way pair (`__rs_twoway`).
- **Proposal:** a public `resolve_edges(roads, palette, settings)` that returns, for each edge, the fill, casing, width and opacity,
  and the tunnel, bridge and two-way flags, as the page bakes them; and a documented way to get the width expression of a road class.
- **Not checked:** the width expression passed as `Overlay.width` only works because roadstyle copies it into `line-width`; it is
  not documented. If it is meant to stay, say so in the `Overlay` docstring.

## 5. Say in the `Overlay` docstring that `order_col` is global

- **Seen:** `order_col` orders the features inside one fill number **across all edges** (`edge_overlays.md`: "global, not per edge").
  Both Kaveh and I read it at first as an order among the features of one edge. The docstring says "the property with its order"
  and does not say which features it orders.
- **Proposal:** one sentence in the docstring and in `edge_overlays.md`'s table: global inside one fill number; features of
  different edges at one fill number are ordered by it.

## 6. Stored levels with other parameters

- **Seen:** `duckosm levels --head-m 25` stored levels that `rs.load_levels(con, roads, ...)` refuses (`head_m: stored 25.0, expected 5.0`),
  and `render_edges(head_m=...)` must equal the stored value for the heads to be drawn where they were solved. mapstyle's
  `stored_levels` therefore only accepts the defaults (`stored_levels.md`).
- **Proposal:** `load_levels(..., accept_stored=True)` that skips the parameter check but still checks the edges (count and hash),
  and returns the stored parameters; or `render_edges(levels=table)` that takes `head_m` from the table's metadata.
- **Not checked:** what else depends on the parameters (`band_dist`, `margin`, `max_level`) once the numbers are stored.

## Order of work

1 and 2 remove the cost that was measured and help lanestyle most; 5 is one sentence; 4 and 6 make outside libraries safer;
3 widens what an overlay can draw. None is needed for mapstyle's own roads, which keep roadstyle's own drawing.
