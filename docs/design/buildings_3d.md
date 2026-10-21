# Buildings in 3D

**Status:** approved and implemented 2026-10-21. **roadstyle is not changed.**

Decisions made on 2026-10-21:

- A separate "Buildings 3D" checkbox. The 2D/3D camera button of roadstyle does not change the buildings.
- A building with no height data gets a height for its kind from the style file.

## Problem

mapstyle draws buildings as flat areas. When you tilt the map, nothing rises, so the map does not
show the city in 3D. MapLibre can draw buildings as blocks with a `fill-extrusion` layer, from a
height on each building.

## The data

duckOSM's `features.buildings` keeps all the OSM tags of a building, so mapstyle can read the
height from the tags. duckOSM does not change.

| Area | Buildings | With `building:levels` | With `height` |
|---|---|---|---|
| Norrmalm | 782 | 724 | 5 |
| Tartu | 22 494 | 1 066 | 15 293 |
| Vancouver | 138 708 | 10 698 | 9 692 |

In Tartu, `height` is not a height in metres. It has only the values 0 to 9 (`height=1` on 3 585
buildings, which include apartment blocks with 5 levels). All of these buildings come from the
Estonian ETAK import. `min_height` and `building:part` are on fewer than 20 buildings in each area,
so mapstyle does not use them.

## The height rule

The height of a building, in this order:

1. `building:levels` × `m_per_level` (3 m).
2. `height`, in metres, when it is 2 m or more. A lower value is not a building height (Tartu).
3. The height for the building's `kind` in the style file.
4. The `default` height in the style file.

`building:levels` comes before `height` because the levels are correct in all three areas, and
`height` is not correct in Tartu. A `height` value with a unit (`12 m`) is read as a number.

## The style file

A new block in `styles/osm_carto.yaml`, under `features`:

```yaml
buildings_3d:
  m_per_level: 3             # metres for one level (building:levels)
  min_height: 2              # a `height` tag below this is not a height (Tartu's ETAK codes)
  opacity: 0.9
  heights:                   # metres, by building kind, when the building has no height data
    house: 6
    detached: 6
    semidetached_house: 6
    terrace: 7
    residential: 9
    apartments: 15
    garage: 3
    garages: 3
    shed: 3
    roof: 3
    greenhouse: 3
    retail: 6
    commercial: 12
    office: 15
    industrial: 8
    school: 9
    church: 15
    default: 9
```

The colour of the blocks is the building fill of the theme (`features.areas.buildings.fill`), so
every theme has 3D buildings in its own colour with no new key.

## On the page

- `load_layers` gives each building a `height` property, from the rule above, in SQL.
- `layers.js` adds one `fill-extrusion` layer on the source of the buildings overlay. It is above
  the roads and below the icons, so a building hides the roads behind it and the icons stay on top.
- A building button under roadstyle's 2D/3D button (added 2026-10-21: the row alone was hard to find), and a "Buildings 3D"
  row under "buildings" in the Layers box. Both start off and both call `rsSetBuildings3D`.
- The 3D layer shows only when the "buildings" layer is on and "Buildings 3D" is on. It follows
  `rs:overlaychange` for the buildings layer.
- JavaScript: `rsSetBuildings3D(on)` and `rsGetBuildings3D()`, made like mapstyle's other `rs*`
  functions, with an `ms:buildings3d` event.
- A click on a building still opens its popup through the flat building layer under the block.
  On a tilted map, a click on the wall of a block can hit the ground behind it.

## Not in this step

- `export.py` (style.json for another app, the GeoLibre plugin): the same layer can be added later.
- Roof shapes, `min_height`, `building:part`.
- A `render_map` keyword to open the page with 3D buildings on.

## Tests and docs

- `tests/test_map.py`: the height of a building from levels, from `height`, from a Tartu code, from
  its kind, and the default.
- README (the JavaScript table), `skills/mapstyle/SKILL.md` and the docs page on layers.
