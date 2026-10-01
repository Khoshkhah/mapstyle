# Junctions and road ends: the complete plan

**Status:** complete draft, for sign-off before any code (Kaveh, 2026-09-30: "every time just try
to fix one issue and create another one").

**How we work on this** (memory: rendering-fixes-need-complete-plan):
- the case catalogue and gallery come from `scripts/junction_gallery.py`, which writes
  `render/junctions/`;
- 23 kinds of junction and road end, 3 real Monaco examples each, plus every edge Kaveh reported;
- every change is judged on the **whole** gallery (before / after), never on one spot.

## Part A: the data (fix first: drawing can't repair topology)

| # | Problem | Monaco | Where | Fix |
|---|---|---|---|---|
| A1 | **Done in duckOSM** (paths cut at global junctions too: `split_here = j OR gj`; fresh Monaco build: 0 left). A path is not cut where it meets a road. The crossing `5645184677067318427` passes the road's node 5601806444 (a global junction) without a node of its own in the walking network. duckOSM cuts **roads** at every node another way uses (`split_at_every_way.md`), but a path only at junctions of its own mode, and here the road isn't in the walking network (sidewalks mapped separately) | 106 nodes in 90 path ways (walking), 16 in 15 (cycling) | duckOSM `graph_simplifier._segment_ways` | cut path ways at every `main.global_junctions` node too, as roads are: `split_here = gj OR j` for paths. Every crossing then shares its node with its road, which is where walk + drive transfer. Ids change once for those paths (as in `split_at_every_way.md`) |
| A2 | **Dropped** (Kaveh: solve it generally): the overlap is fixed by rule 2 below (a square's outline along a road becomes a lane of that road); filled squares are a cosmetic extra for later. Pedestrian squares (`highway=pedestrian` + `area=yes`) and platform areas have only their **outline** in the network, drawn as a thick street. It overlaps the roads next to it (`9144234404296452426` 0.6 m from Allée Lazare Sauvaigo) | 17 squares (210 edges), 3 platform areas (18 edges); none in `features.*` | duckOSM `features.*`, then mapstyle | duckOSM fills Shortbread's **`street_polygons`** layer (the pedestrian / platform areas as polygons); mapstyle draws it as a pale fill under the roads (openstreetmap-carto: `#dddde8`, thin outline). The outline edges stay in the network for routing, drawn thin (path width) |
| A3 | A one-way street has a walking-only reverse edge (pedestrians may walk both ways), so it looked two-way | 640 streets | data is right; drawing | done: roadstyle's `directed_col` + mapstyle's `is_directed` (open to cars or bikes, not a path). The reverse edge lies exactly on the one-way edge. Open: whether it should be drawn at all (a click picks one of the two) |
| A4 | A car road carries `walk_type=sidewalk` (you walk on its own sidewalk) | 708 edges | mapstyle | done: bands move paths only |
| A5 | `layer` tags without bridge / tunnel (a raised walkway, a road under a building) | 159 contact points | data is OSM's; drawing | roadstyle's plain high / low bands (0.9.2). Part B decides how their ends meet ground roads |

## Part B: the drawing, per case

Kaveh's marks on the gallery (cases 5, 48, 49, 63, 76) all show one problem: **a road at ground
level ends in a round cap exactly where it continues into its tunnel**, so it reads as a dead end
(also Rue du Castelleretto, `5990211243552773545` / `7910395095814073287`). Every other kind in the
gallery was left unmarked and keeps its look. The rules below are judged on the whole gallery.

### Rule 1. A tunnel is an ordinary road with a tunnel style (Kaveh, 2026-09-30)

"Why is the algorithm different for tunnels and ordinary roads? They should act the same; the only
difference is the colour style."

**Why it differs today.** roadstyle, like openstreetmap-carto, draws every tunnel, along its whole
length, in a lower band (its own casing + fill pair under the ground roads). That is right where a
tunnel **passes under** a street without joining it: otherwise the tunnel's fill would cut the
street's casing and look like a junction. But it is wrong where a tunnel **joins** a road at its
mouth: the ground road's round end lies over the tunnel, giving the dead-end look. The 3 m
tunnel-mouth pieces (`tunnel_portals`) only patch it.

**The rule.** A tunnel draws exactly like an ordinary road, with the tunnel's colours: the faded
fill and the two-tone dashed casing. It goes to the lower band **only for the stretch where it
actually passes under another road**.

- **A tunnel that passes under nothing is drawn with the ground roads, end to end**, in the tunnel
  style. Monaco: 279 of 546 tunnel edges.
- **A tunnel that passes under roads is cut, for drawing only**, into stretches:
  - from each mouth to the first road it passes under, less a 4 m clearance, it is drawn with the
    ground roads (the clearance keeps its fill off that road's casing, up to z20);
  - the stretch under the road(s) is drawn in the lower band, as today. At a shallow crossing
    that is the whole stretch within 4 m of the road, not only 4 m either side of the crossing
    point (Kaveh: the tunnel `1494951369778192963` painted its casing over Avenue de la Porte
    Neuve's), but never into a mouth (a mouth beside the road keeps its ground stretch: the
    gallery's cases 66 and 81 got their dead-end caps back without that limit).

  Monaco: 267 edges. The edge stays one feature in `roads`: clickable, filterable, recoloured.
  The stretches are drawing pieces, like the portal pieces today, each carrying its edge's id.
- **Joints:**
  - at a mouth, the tunnel's first stretch meets the ground road like any road continuing: the
    fills merge, and the casings stay under the fills;
  - the ground-level tunnel stretches have their own casing / fill layers, with **butt** caps,
    just above the ground casings and just under the ground fills;
  - so the ground road's round casing end is covered by the tunnel's casing (tunnel colours), and
    nothing round crosses the mouth;
  - where a ground-level stretch meets its lower-band stretch inside the tunnel, both are in the
    tunnel style, so the seam is the same colour.
- **The dash.** MapLibre can't change `line-dasharray` per feature, so the dashed tunnel casing of
  the ground-level stretches is a sibling layer, as the dashed classes have today.
- **Replaces** `tunnel_portals` (the 3 m mouth pieces and `tunnel_portal_m`).
- **With the other rules:**
  - drawing order: class, `band_col`, and the link order (done) apply to the ground-level
    stretches like any ground road;
  - twin end caps: a ground-level tunnel stretch counts as ground (`rank`), so a two-way road's end
    at a tunnel mouth gets its full cap, and the cap's ring lies under the tunnel's casing;
  - the bridge and tunnel toggles still hide every stretch of a tunnel.
- **Roads with only a `layer` tag** (no bridge / tunnel tag; Kaveh, 2026-09-30: Boulevard
  Charles III `8575527472885888522`, a 4.7 m `layer=-1` tunnel approach, looked cut off from
  Rond-Point Canton `851168964544725370`, though they share a node) act the same, in the plain look:
  - one that passes under / over no road is drawn with the ground roads, whole (Monaco: all 92 at
    `layer<0`, 154 of 190 at `layer>0`);
  - one that does (Monaco: 36, all raised footways / pedestrian ways over a street) is cut into
    stretches like a tunnel: over the road (± 4 m, the same clearance) in its own band, the rest
    with the ground roads, in its ordinary look, round caps;
  - "passes under" counts only a road above (a path above is drawn over the ground stretch
    anyway, as for tunnels); "passes over" counts any road or path below (a raised walkway must
    still show over a footpath it crosses);
  - a caller's `band_col` value (mapstyle's sidewalks / crossings) wins: such an edge is left as
    the caller put it.
- **Bridges keep their band.** The cut-off look comes from a *lower* road under a ground road's
  round end. A bridge is drawn over the ground roads with square deck ends, so its ends already
  join; the gallery's bridge-end cases were not marked.
- **Dashed classes** (steps in mapstyle's default style, every path in `osm`): the stretch layers
  get the dashed sibling layers that the whole-edge layers have (a dashed tunnel stretch was drawn
  solid or not at all).

Where: roadstyle (`render_web.py`: the stretches, the layers, the toggles; the portal code goes).
mapstyle: nothing new.


### Rule 2. Every path alongside a road is a lane of that road (Kaveh, 2026-09-30)

**Status: not agreed.** The design below is Claude's reading of "one frame"; Kaveh, after the
mockup (`render/sidewalk_mockup/`): "it is not what I meant". Don't build it; start again from
Kaveh's own description or example.

"It is the same as what we did for twin edges: add the sidewalks to them too", and "do it as general
for every road": every path edge that runs alongside a road (a mapped sidewalk, a plain footway next
to a road, the stretch of a pedestrian square's outline along a road) is drawn the way a two-way
road's lanes are:

- **on its road's own line, shifted sideways** by a zoom-based offset: the road's outer half-width
  plus half the sidewalk's width, the same kind of expression as `_offset_expr` /
  `_end_radius_expr`. So it sits right beside the drawn road at every zoom, whatever the road's
  width in pixels. Today it lies on the road's casing or floats off it, because roads are drawn
  wider than they are;
- **still its own edge**: clickable, filterable, recoloured by `rsColor`, so a walking route along
  a sidewalk lights up its strip;
- **the road's casing is the divider** between the roadway and the sidewalk strip.

**Today** (measured on Monaco, 646 physical sidewalks, each stored both ways): a sidewalk lies at
its real place, 6 m from its street's centre line (median; 10 %–90 %: 3.7–8.8 m), and is drawn
under its street (`band_col` −1). Streets are drawn wider than they are (half-widths at z17:
residential 4.8 m, primary 7.6 m; at z18: 3.5 m, 4.8 m), so the street covers it; in the default
`google` look (white footway, light grey edge) what shows reads as the street's outline. Kaveh:
"I didn't see any sidewalk on the map."

**The design:**

1. **Matching (mapstyle).** Any path (every path class but a crossing; Kaveh: "as general for
   every road") belongs to the street (a road open to cars or bikes) it runs along: parallel
   (within 25°), within 15 m, over at least 70 % of its length; the side is the side of the
   street it lies on. Monaco (each path counted once, not per direction):
   - mapped sidewalks: 549 of 644 (85 %; 80 % of their length);
   - other paths alongside a street: 561 footways, 118 steps, 65 pedestrian ways, 16 paths, 1
     corridor.

   The rest keep their real line and today's look (sidewalks: 84 follow a street only partly,
   at corners and bends; 12 have no street alongside).
2. **Drawing line (mapstyle).** A matched sidewalk is drawn on its street's line, from where its
   two ends project onto the street, in its own direction. Only the drawing changes: the edge,
   its data, clicks, filters and `rsColor` are its own, and so are its width and colour.
3. **One frame around the street and its sidewalks** (Kaveh, 2026-09-30, choosing among three
   sketches: "one frame, wider street"):

   ```
   ┌──────────────────────────────┐  one outer edge line (the frame)
   │  sidewalk                    │
   ├╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┤  thin divider
   │  lane  →                     │
   │  lane  ←                     │
   ├╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┤  thin divider
   │  sidewalk                    │
   └──────────────────────────────┘
   ```

   - the street keeps its width; each sidewalk adds a strip on its side, so the street with its
     sidewalks is wider;
   - the strip's fill lies right outside the street's fill, a thin gap away (the divider: the
     gap shows the frame's colour); its outer edge is the frame;
   - drawn like twin lanes, from zoom-based widths (`_width_expr`, `_offset_expr`), so it fits
     at every zoom: the strip (an edge with the street's class and the side, two optional
     columns, roadstyle, new and generic) is shifted by the street's half fill width + the
     divider + its own half width, and its casing (the frame's colour: the street's casing)
     reaches from inside the divider to its outer edge;
   - all casings are under all fills, so the street's and the strips' casings merge into one
     frame, and the strip's fill and the street's fill stay apart by the divider;
   - where a street has a sidewalk on one side only, or for part of its length, the frame is
     wider only there;
   - drawn with the ground roads, not under them (no `band_col` −1 for a matched sidewalk).
4. **Ends, corners, crossings: judged in the gallery, not designed blind.**
   - a strip ends where the sidewalk's ends project onto the street; around a corner the next
     strip starts on the cross street, and the partly matched corner piece between them keeps
     its real line;
   - a crossing keeps its real line (over the street, `band_col` +1); its ends are at the real
     sidewalks, close to the strips at z18+ and inside the street at lower zooms.

   The gallery's sidewalk, crossing, corner and junction cases (before / after) show whether
   these need more (e.g. snapping a crossing's ends to the strips).

For each kind in the gallery: what's wrong today, the target look, and the rule that gives it. The
rules are order (class, band, strokes), end caps, casings and tunnel mouths, and above all **how the
rules interact**. That interaction is what broke before:

- caps ↔ bands (a ring across a tunnel);
- bands ↔ car roads with sidewalks;
- caps ↔ tunnel mouths (a dead-end look).

### B3. Already done, kept

- links below every street (roadstyle, junction plan step 1);
- crossings over / sidewalks under (paths only);
- one-way streets with a walking reverse drawn as one line (`directed_col`);
- twin end caps, with no ring where a lower band meets: with B2 that is only real underpasses;
- strokes (the through road on top within a class): later, after B1 / B2, if the gallery still
  shows wrong T junctions.

## Order of work (each step: its tests, then the whole gallery before / after)

1. Rule 1: tunnels as ordinary roads with a tunnel style (fixes all of Kaveh's gallery marks).
2. Rule 2: every path alongside a road is a lane of that road.

The gallery is rebuilt on a fresh Monaco build (duckOSM with A1) as the "before" of rule 1.

## Part C: checks

The whole gallery before / after (Kaveh reviews every case); a test per rule on small synthetic
junctions; the browser checks on five page kinds (plain, dashboard, planner, tiles, 3D) with no page
errors.
