# Roads as overlays: an experiment, and what it says

**Status:** experiment, 2026-10-04 (Kaveh: "we can first test something simple: pass the edges as overlay and see
if it works"). **Result: it works, but mapstyle does not need it.** The recipe is for a library that draws the
fill itself (lanestyle). The script is `scripts/roads_as_overlays.py`; nothing in `src/mapstyle` changed.

## The question

roadstyle draws a road in two parts: the **casing** and the **fill**, each from the road's own line. Since roadstyle 0.12 an
`rs.Overlay` can also be **attached to edges** (`edge_col`, `order_col`; roadstyle `docs/design/edge_overlays.md`): each of its
features is drawn at the place of its edge in the drawing order. With `road_fill=False` roadstyle draws only the casing, and
the fill is whatever the overlays draw. Can the roads' fill be drawn by overlays, and look the same as roadstyle's own?

## The two approaches

| | **A. roadstyle draws the roads** (today) | **B. the roads' fill is overlays** (the experiment) |
|---|---|---|
| call | `rs.render_edges(roads, ...)` | the same, plus `road_fill=False` and one `rs.Overlay(edge_col="edge_id", order_col="order", color_col="fill", kind="line", width=<expression>)` per opacity group |
| casing | roadstyle's | roadstyle's, unchanged |
| fill colour, opacity | roadstyle's per-edge `__rs_fill`, `__rs_op` | the same numbers, read with `rs.build_styler(...).resolve_frame(roads)` and baked in a `fill` property; a tunnel's faded fill is blended onto the canvas colour (roadstyle's opaque underlay) |
| fill width | roadstyle's per-class zoom expression (`_width_expr`), 12 to 20 | the **same expression**, passed as `Overlay.width` (roadstyle copies it into `line-width` as given) |
| order | the fill number of the edge, then the class | `edge_col` gives the fill number; `order_col` is roadstyle's class order (`ROAD_Z`) |
| two-way streets | two lanes, each 0.6 of the width, shifted 0.28 of the width to its side, with end caps | **not reproduced**: an overlay has no line offset, so both directions lie on the centre line at full width |
| dashes (steps), caps, arrows | roadstyle's | not reproduced (the arrows stay roadstyle's) |
| private names used | none | `render_web._width_expr`, `render_web.ROAD_Z` |

How the edges reach the overlay (`scripts/roads_as_overlays.py`): one GeoJSON feature per row of the roads (one per `edge_id`,
both directions of a two-way street), with the edge's **own geometry** and its `edge_id` as text (it can pass 2**53). roadstyle
looks the `edge_id` up in the roads and draws the feature at that edge's fill number; an id that is not among the roads is an error.
Nothing tells roadstyle which edges are twins: it finds them itself from the geometry (`_mark_twoway`), and `directed_col`
only turns the pair look off.

### What roadstyle does with twin edges (read from the code)

- Each twin is its own feature and has its **own casing line**; they look like one outline because the two casings overlap and
  the fills are drawn over the middle. Only a pair's end gets one extra round cap, as wide as the whole road (`twin_ends.md`).
- A pair at full split (zoom 17 and up): each lane is 0.6 of the width and shifted 0.28 of the **fill** width, so a primary road
  (15 px at zoom 17) has a fill of 17.4 px and a casing of 19.0 px over both lanes; a single edge has a fill of 15 px and a casing of 17.7 px.
- Given one twin only, roadstyle finds no pair: one casing and one fill at full width on the centre line, no offset.
- Both twins with `is_directed` false: not a pair; each is drawn at full width on the centre line, so the two lie on the same place.

## Measured (Monaco, `duckOSM/monaco.duckdb`, 12,941 edges)

Headless Chromium with **software WebGL**, 480×320 px, one run each. The absolute frame rates mean nothing on a GPU; the
ratios are what was compared. The overlay page is the first version of the script (it drew 109 `building_passage` edges as faded
tunnels, which roadstyle does not); the script now takes the faded group from roadstyle's own opacity.

| | A (`monaco.html`) | B (roads as overlays) |
|---|---|---|
| file | 4.88 MB | 6.44 MB (+32 %) |
| load | 1.6 s | 2.2 s |
| layers | 129 | 239 (+85 %) |
| GeoJSON sources / features | 19 / 40,286 | 22 / 53,227 (+32 %) |
| frames per second while panning, zoom 15 | 18.8 | 13.3 (−29 %) |
| frames per second while panning, zoom 17 | 57.5 | 34.2 (−41 %) |
| JS heap after the test | 170.6 MB | 258.0 MB (+51 %) |

GPU memory was not measured. The extra cost has two causes: every edge's geometry is in the page twice (the roads' own source and
the overlay), and an edge overlay makes one map layer for each `(fill number, order)` that occurs.

## Looks

At zoom 17, in one view, B is close to A: white streets, the same casing, tunnels faded, the olive secondary road. It was
not compared at other zooms. Three differences are known:

1. **The fill is narrower.** B draws both twins at 15 px on the centre line (±7.5 px) over a casing that roadstyle draws for
   the pair (±9.5 px); A's fill spans ±8.7 px. So a grey ring of about 2 px shows in B, against 0.8 px in A. This made B look darker.
2. **The doubled fill.** Both directions are drawn at opacity 0.9 on the same line, so B is slightly more opaque than A.
3. No dashes, no lane split, no extra end caps.

## Conclusion

- **mapstyle keeps approach A.** For plain roads B costs more (file, layers, memory, frames) and shows nothing A does not.
- **Edge overlays are for things that sit on a road**: a zebra crossing, a signal, a lane marking. The next step for mapstyle is
  `features.traffic` (crossings, signals) with an `edge_id`: duckOSM writing it, or mapstyle matching a node to its edge. That needs its own note.
- **B is the right shape for a library that draws the fill itself.** lanestyle already calls `render_edges(roads, road_fill=False,
  overlays=[Overlay(edge_col=..., order_col=...)])`. What this experiment adds for it:
  - `Overlay.width` takes a MapLibre expression, not only a number (not documented in roadstyle; it works because the value is copied
    into `line-width`). lanestyle does not need it, because a lane is a polygon of its width in metres.
  - One road row per link (not per direction) avoids the doubled fill and the doubled casing.
  - Measure the same four numbers on a lanestyle page, and set `min_zoom` on its overlays (lanes are only drawn from zoom 16), so
    the extra layers cost nothing at low zoom.
- **Not tried:** one overlay row per two-way street at the pair's full width (17.4 px), to get the fill width of A without a
  line offset; other zooms (14 and 18 were too slow to measure in software WebGL); a real GPU.
