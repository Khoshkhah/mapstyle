# Themes: the whole map's colours

**Status:** approved and implemented 2026-10-01 (Kaveh: "commit and push"). Themes: `grey`
(Kaveh chose "light grey (data)" among dark, light grey, satellite hybrid, high contrast) and
`google` (Kaveh: "should I create a google version too?", yes).
The previews (`render/themes/index.html`) come from a prototype of this design.

## Problem

mapstyle has one look, openstreetmap.org's (`styles/osm_carto.yaml`). Modes say which network
stands out and path styles how paths look, but the colours of everything else (roads, land use,
water, buildings, icons, the background) are fixed. On top of that look, your own colours
(SonoFlow's flows, a route, sensor readings) compete with greens, oranges and pinks.

## Design

- **`theme=`** on `render_map` and `--theme` on the command line: `osm` (today's look, the
  default) or a file in `styles/themes/<name>.yaml`. It combines with any mode and path style.
- **A theme file is short:**

  ```yaml
  # styles/themes/grey.yaml
  background: "#f5f5f3"            # the land colour (a plain base map, registered with roadstyle)
  transform:                        # applied to EVERY colour of the osm look not set below:
    saturation: 0.12                #   keep 12 % of the colour
    lighten: 0.35                   #   then 35 % of the way to white
  roads: {colors: {...}}            # explicit colours, same keys as osm_carto.yaml
  features: {areas: {...}, landcover_pattern: {}, ...}   # e.g. no textures
  paths: {footway: {fill: ...}}     # path colours over any path style (dash and width kept)
  roadstyle: {bridge_casing_color: "#a3a3a3"}   # roadstyle settings (its `config`)
  ```

  Order: osm_carto.yaml → the transform on every colour → the explicit colours. So a theme never
  has to list all 50 landcover kinds or 20 road classes, and a class added later gets a fitting
  colour on its own.
- **The background** becomes a plain roadstyle base map, `blank_<theme>`, registered with
  roadstyle's public `register_basemap` (roadstyle unchanged); the raster maps stay in the switcher.
- **Not themed:** your data colours (`rsColor`, colour options, the dashboard's colour by mode) and
  the route planner's legs: they are what the theme makes room for.

## `grey`

A quiet, light map for data, in the manner of CARTO Positron:

| Part | Colour |
|---|---|
| background (land) | `#f5f5f3` |
| sea, water | `#d5dde0` (a hint of blue), rivers `#c3cfd4` |
| parks, grass, forest | `#e7ece5` (a hint of green); every other land use from the transform |
| buildings | `#e6e5e2`, outline `#d9d8d4` |
| roads | white, grey outlines darker for bigger roads (`#a9a9a9` motorway … `#d4d4d4` residential); motorway / trunk fill `#ececec` |
| paths | light grey `#c9c9c9`, cycleways `#bcc3cc` |
| railways, platforms | greys |
| icons | from the transform: grey, lighter |
| textures | off |

## `google`

Clean and friendly, in the manner of Google Maps (colours only; nothing of theirs is copied), and
the match of the `google` path style (the default):

| Part | Colour |
|---|---|
| background (land) | `#f5f4f1` |
| sea, water, port basins | `#aadaff`, rivers `#8fc8f5` |
| parks, grass, forest | soft greens `#c3e4c6` … `#d4edd5`; hospitals pale pink, schools pale beige, beaches pale sand |
| other land use | near the land colour (`#f1f0ec`) |
| buildings | `#e9e8e5`, outline `#dcdbd7` |
| roads | motorway / trunk / primary yellow (`#f8d16c` / `#fbdd8a` / `#fde9a6`), the rest white with soft grey edges |
| icons | from the transform: their colour, softened |
| textures | off |

Both themes colour a port basin (`marina`) as water: OSM tags Port Hercule as a marina, and a
darker basin inside a light sea looked like a different thing.

## Checks

- Tests: every colour of `grey` is a hex colour with low saturation (≤ 15 %), except the explicit
  water and park hints; `theme="osm"` gives today's page exactly; an unknown theme is an error
  naming the choices; the CLI's `--theme`.
- Previews (whole Monaco map, every mode, with and without a data overlay): `osm` vs `grey`.
