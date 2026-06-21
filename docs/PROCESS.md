# Building mapstyle — process & architecture

How `mapstyle` came to be, what each piece does, and the cartographic decisions behind it.
This is the "why", step by step; for the API see the code and `docs/PLAN.md`.

## 1. Goal

Render an OSM "base layer" (the openstreetmap.org **Standard** look) from our own data, and
in particular show the **multi-modal road network** (driving / walking / cycling) the way
OSM draws roads. [`roadstyle`](../../roadstyle) already styles *road edges* beautifully but is
line-only; `mapstyle` generalizes that idea to a full map and adds the multi-modal merge.

## 2. The data pipeline (three projects)

```
OSM .pbf ──duckOSM──> routing .duckdb        (driving/walking/cycling .edges, stable edge_id)
                          │
                          ▼
              duckmap (basemap.* schema)      roads_* tables copied from the routing edges;
                          │                    water/landcover/buildings from the PBF
                          ▼
                       mapstyle                merge the 3 modes -> 1 edge set, style + render
```

- **duckOSM** parses the PBF and builds a routing graph per mode. Each edge has a **stable
  `edge_id`** = `hash(osm_id, source, target, is_reverse)`, plus `highway`, `oneway`,
  `service`, `layer`, `bridge`, `tunnel`, geometry, … (several of those columns were added
  *during* this work — see §6).
- **duckmap** lifts the mode edges into `basemap.roads_{driving,walking,cycling}` (and builds
  the area layers from the PBF). It's the data-prep stage.
- **mapstyle** reads `basemap.*` and produces the styled, interactive viewer.

Tartu (no-merge build) is the working extract throughout.

## 3. The merge — one multi-modal edge set

The three mode networks overlap heavily (a residential street is drivable, walkable and
cyclable). `merge_modes()` collapses them by `edge_id`:

```sql
SELECT edge_id, any_value(class), any_value(geom), …,
       bool_or(mode='driving') AS driving,
       bool_or(mode='walking') AS walking,
       bool_or(mode='cycling') AS cycling
FROM (driving ∪ walking ∪ cycling) GROUP BY edge_id
```

Result on Tartu: **106k overlapping rows → ~68k distinct edges**, each tagged with three mode
flags (51% walk-only sidewalks, 17% all-three, …). This is the model that should eventually
live in duckOSM as a single `edges` table with `access_*` flags; mapstyle validates it first.

## 4. Rendering architecture

The viewer (`render_merge`) is a single self-contained HTML: **MapLibre GL** for the basemap +
**deck.gl** (`MapboxOverlay`) for our layers, with the geometry baked to `data/*.geojson`.

- **Basemap selector**: OSM Standard (raster `tile.openstreetmap.org`), Carto Positron/Dark,
  Esri Satellite, or **None** (our layers only). The OSM raster is the reference; "None" is
  what the map becomes once area layers are styled.
- **Roads** are drawn as deck `GeoJsonLayer` line layers — a **casing** pass under a **fill**
  pass (the OSM "geometry sandwich").
- **Interactivity**: per-mode filter checkboxes, color-by **OSM class** vs **mode
  combination**, click-to-inspect (name/class/length/modes/edge_id), hover highlight, live
  zoom readout.

## 5. OSM-Carto fidelity — the cartographic decisions

Each of these was driven by the openstreetmap-carto standard (the default osm.org style):

| Aspect | What OSM does | What mapstyle does |
|---|---|---|
| **Road colors** | per-class palette (secondary yellow, residential white, footway salmon dashed, cycleway blue dashed…) | `roads.py:ROAD_CARTO` — exact carto fills/casings/dashes |
| **Widths** | per-class **pixel width by zoom**, growing as you zoom in | a per-group **width table by zoom** (`styles/osm_carto.yaml`), smoothly interpolated, with per-group growth above the table top (`hi_rate`) |
| **Casing** | thin darker outline | `casing = fill × casing_ratio` |
| **Paths** | thin fixed-ish dashed lines | path group stays thin (low growth); dashes via deck `PathStyleExtension` |
| **Draw order** | `z_order` by class; **links below all roads**; `+10×layer` so **bridges draw over, tunnels under** | `road_z` (links −20) + `10×layer`; rendered in 3 **elevation bands** (tunnel / ground / bridge) as separate deck layer pairs, since deck only guarantees order *between* layers |
| **Service roads** | `driveway`/`parking_aisle`/`drive-through` narrower than general service/`alley` | `service` subtag splits into `service` vs `service_minor` width groups |
| **Oneway arrows** | line-placed from ~z16, spaced, travel direction | deck `TextLayer` "▶" per oneway edge at its midpoint, rotated to bearing, z≥16 (approximation — see §7) |
| **Names** | line-placed text, white halo, by-class zoom | one deduped label per road name, white halo, z≥14 |

### Why a raster basemap can't be width-matched exactly
A long detour: the OSM **raster** tiles are pre-rendered per integer zoom and *scaled* between
them (≈2×/zoom, snapping at tile boundaries). A smooth vector width curve is always thinner
than the scaled tile mid-band; matching the snap produces a visual "sawtooth" (roads getting
*thinner* as you zoom). Conclusion: **don't pixel-match the raster** — use smooth, monotonic
vector widths and compare on a **vector** base (Positron) or **None**. The widths here are
that smooth curve.

## 6. duckOSM changes made for this (shipped to `main`)

To style faithfully, the edges needed tags duckOSM wasn't carrying. Each was threaded through
`road_filter` → `graph_simplifier` (segment build, self-loop split, merge predicate, reverse
edges, rekey) and the merge-test fixtures, then run on Tartu:

- **`layer`, `bridge`, `tunnel`** — for the bridge/tunnel draw order (PR #1).
- **`service`** — for the narrow/wide service split (PR #2).

The bridge case is the clearest payoff: an elevated trunk (`bridge=yes, layer=1`) was *looking*
connected to a roundabout it actually passes over; with `layer` on the edge and `+10×layer`
in the z-order, it now renders above.

## 7. Known approximations
- **Labels/arrows** use deck (point placement at a midpoint), not Mapnik/MapLibre
  `symbol-placement: line`, so they don't follow curves, repeat along long roads, or do
  collision detection. A faithful version would render them as MapLibre symbol layers
  (needs a glyphs source and an interleaved overlay).
- Widths are a transcription of the openstreetmap-carto table, interpolated — close, tunable
  in the YAML, not byte-identical.

## 8. Configuration
Tunable cartographic numbers live in **`src/mapstyle/styles/osm_carto.yaml`** (`roads.width` /
`hi_rate` / `casing_ratio`), loaded by `style.py` and injected into the viewer. Edit and
re-render — no code change. Colors (road palette, landuse, combo) are next to move there.

## 9. Run / extend
```bash
python -m mapstyle ...            # (library; see merge.py)
# merged viewer:
python -c "from mapstyle import merge_modes, render_merge; \
  render_merge(merge_modes('<basemap>.duckdb'), 'render/tartu', basemap='osm')"
python render/tartu/serve.py      # -> http://localhost:8080/...
```
Add a new style by copying `styles/osm_carto.yaml`. Add an area layer by extending the
duckmap `basemap.*` set and giving it a deck layer in the viewer.

## 10. The journey (chronological)
scaffold → multi-modal merge (`edge_id`) → OSM-class colors → smooth vector widths (after a
raster-matching dead-end) → per-mode distinct vs OSM coloring → bridge/tunnel & link z-order
(+ duckOSM `layer/bridge/tunnel`) → service narrow/wide (+ duckOSM `service`) → widths to a
YAML config → oneway arrows + street-name overlays.
