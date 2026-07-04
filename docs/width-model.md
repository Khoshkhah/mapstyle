# Road width model — physical, config-fixed lanes

> **Status: implemented.** Road width is physical (`lanes × lane_m`) with the **lane count fixed per
> class in config**, not read from OSM. All numbers live in `styles/osm_carto.yaml` →
> `roads.width_model`.

## Why

Width used to be a per-class-per-zoom **pixel table** (copied from OpenStreetMap-Carto). Two problems:
class-to-class ratios **drifted with zoom** (widths looked "random" per zoom), and width ignored the
physical road. So we moved to a physical model: `width = base_metres × scale(zoom)`.

We first drove `base_metres` from the OSM `lanes` tag — but that data is too noisy for a clean base map:

- **91% of roads are untagged** for `lanes` (Tartu) → mostly duckOSM's `1/1` defaults anyway.
- duckOSM stores lanes **per direction** and forces ≥1 each, so it **can't represent single-track**
  (a `lanes=1` road comes through as `1/1` = total 2).
- On the tagged minority, widths **bulge at junctions** (turn lanes: a segment jumps `2 → 3 → 2`).

So the lane count is now a **fixed per-class value in config** — uniform, predictable, tunable. The raw
OSM `lanes` tag is shown in the click-info **for reference only** (`OSM lanes: N total (not used)`).

## The model

```
base_metres = lanes[class] × lane_m[class]                 # both from config
width_px    = base_metres × (1 / mpp) × zoom_boost(zoom)
```

- **`lane_m[class]`** — physical width of one lane, in metres.
- **`lanes`** — lane count, fixed per class, resolved by direction (below).
- **`zoom_boost(zoom)`** — ONE global legibility curve, shared by every class, so class width ratios
  are constant at every zoom. `→ 1.0` (true physical size) at high zoom; lifted at low zoom so thin
  roads stay visible. (It *decreases* with zoom — see note below — yet net width still grows.)
- **`mpp`** = `156543.03 × cos(lat) / 2^(z+1)` — MapLibre's true metres-per-pixel. The `z+1` is
  essential (512-px tiles) — see the offset section.

### One-way vs two-way

A class can be **either** — a secondary is two-way as a street but one-way as a dual-carriageway
carriageway — so the lane count comes from **two tables**:

- **two-way road** → each of its two directed edges uses **`lanes`** = lanes *per direction*
  (`0.5` = single-track, one lane shared by both ways), offset **±`base_metres/2`** so the two
  directions sit edge-to-edge.
- **one-way road** → its single directed edge uses **`lanes_oneway`** = *total* lanes of the
  carriageway, drawn centred.

So a **secondary** renders **6 m** one-way (2-lane carriageway) vs **3 m/dir** two-way. Paths/footways
(`path` group) are never split — single dashed line.

## Two-way offset calculation (and the 512-tile scale gotcha)

**Offset (baked into geometry, metres).** In `_offset_two_way`, each two-way directed edge is shifted
sideways in a local UTM (metre) CRS with shapely `offset_curve`:

```
offset_metres = base_metres / 2
```

Forward and reverse edges are each offset to *their own* left; the reverse geometry runs the opposite
way, so the two directions end up `base_metres` apart, centre-to-centre, and — drawn `base_metres` wide
each — tile edge-to-edge into the road's physical width.

**The scale gotcha (what caused the earlier gap).** Offset is **metres** (baked once); width is
**pixels** (recomputed per frame). They stay consistent — and the two directions meet without a gap —
only if `mpp` is the scale **MapLibre itself uses**. MapLibre GL renders with **512-px tiles**, so its
true scale is one zoom finer than the classic 256-tile formula:

```
mpp(z) = 156543.03 × cos(lat) / 2^(z+1)      # 512-tile: note the z+1
```

We first used `/2^z` (256-tile) — **2× too large** → widths rendered at **half** physical while the
metre-offset projected at **true** size → the fills couldn't reach each other → a real background gap.
Verified live at z21: MapLibre projects 3 m = **151.8 px**, but `/2^z` said 76.6 px. After the `z+1`
fix a 3 m road computes to 176 px → the two directions overlap (`lane_overlap`), no gap.

## Why `zoom_boost` *decreases* with zoom (net width still grows)

`zoom_boost` is a **correction on top of** the physical term, not the width itself:

```
width_px = base_metres × (1 / mpp) × zoom_boost(zoom)
                          └ physical: grows 2×/zoom   └ correction: fades toward 1.0
```

`1/mpp` already grows strongly with zoom; `zoom_boost` only stops roads becoming *too thin to see* when
zoomed out, fading to `1.0` (true physical scale) once legible. Net width still increases every zoom
(6 m road, Tartu: 2.7 → 6.2 → 21 → 77 px across z12→z20). Keeping physical (`1/mpp`, latitude-correct,
computed at render time) and legibility (`zoom_boost`) as separate factors means one `zoom_boost` curve
works at any latitude without re-tuning.

## All numbers → config (`osm_carto.yaml` → `roads.width_model`)

```yaml
  width_model:
    lane_m:            # physical metres per lane, by class
      major: 3.5   trunk: 3.5   primary: 3.25   secondary: 3.0   tertiary: 3.0
      residential: 2.75   living_street: 2.75   service: 2.75   service_minor: 2.5
      pedestrian: 2.5   path: 1.5   default: 3.0
    lanes:             # lanes PER DIRECTION of a TWO-WAY road (0.5 = single-track)
      major: 2   trunk: 2   primary: 1.5   secondary: 1   tertiary: 1   residential: 1
      living_street: 0.5   service: 0.5   service_minor: 0.5   pedestrian: 0.5   path: 0.5   default: 1
    lanes_oneway:      # TOTAL lanes of a ONE-WAY road/carriageway (a dual-carriageway arterial ~2)
      major: 2   trunk: 2   primary: 2   secondary: 2   tertiary: 1   residential: 1
      living_street: 1   service: 1   service_minor: 1   pedestrian: 1   path: 0.5   default: 1
    zoom_boost:        # ONE global legibility multiplier over physical, by zoom (interp; ->1.0 high z)
      12: 9.0   14: 4.0   15: 2.6   16: 1.8   17: 1.3   18: 1.1   20: 1.0
    lane_overlap: 1.15 # two directional lanes overlap this much at the centre (no seam, no gap)
```

Unchanged config: `roads.colors`, `roads.casing_ratio`, `roads.min_zoom`.

**`service` / `service_minor` split.** Service roads split by the OSM `service=*` subtag — `driveway`,
`parking_aisle`, `drive-through` use the narrower `service_minor` group; through service roads use
`service`. It's an OSM-Carto convention and carries straight into the `lane_m` / `lanes` tables above.

## Code (all in `mapstyle`)

- **`_base_m(hw, svc, oneway, wm)`** — `lanes[...] × lane_m[class]`, picking `lanes_oneway` vs `lanes`
  by the `oneway` flag. No OSM lane data.
- **`merge_modes`** — computes `bm` per edge from `_base_m`; offsets two-way edges by `bm/2`
  (`_offset_two_way`); joins `ways` only to surface the raw OSM `lanes` tag for the info popup.
- **Viewer** — `widthPx(bm, z, isLane) = bm / mppAt(z) × interp(zoom_boost, z) × (isLane ? lane_overlap : 1)`,
  shared by roads, oneway arrows and name-labels. `mppAt` uses the 512-tile `2^(z+1)`.

## Open items

- **Widths are true-physical at high zoom** (a 6 m road ≈ 6 m on screen) — wider than the old stylised
  OSM-Carto pixels. Tune with `zoom_boost` / `lane_m` if a different feel is wanted.
- `lane_overlap` is applied to the **width** only, so a two-way road ends ~`lane_overlap` wider than
  exact physical; folding it into the offset (`offset = base × (2−lane_overlap)/2`) would keep the road
  exactly physical (makes `lane_overlap` a re-render knob).
- `path` / `pedestrian` at `0.5` lanes read thin; bump if desired.
