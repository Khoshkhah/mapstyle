# Design: the roadstyle look as a theme

**Status:** proposal, 2026-10-22. Waits for sign-off. Nothing is coded.

## Problem

The level editor of duckOSM draws roads with roadstyle's own defaults: the profile `default` and the palette `amber`. The mapstyle page and the
GeoLibre plugin draw roads with the OSM-Carto look (theme `osm`, path style `google`). Kaveh wants the editor look as a choice, and OSM-Carto stays the default.

## Change

1. **A theme `roadstyle`** (`styles/themes/roadstyle.yaml`). Its `roads.colors` are the colours of roadstyle's palette `amber` (fill, casing, dash) for
   the classes that `amber` has: motorway, trunk, primary, secondary, tertiary, residential, service, footway, path, cycleway. The file is made from
   `rs.palette_to_dict("amber")` by a script, so the two cannot differ (a test compares them).
2. A class that `amber` lacks (steps, pedestrian, platform, raceway, …) keeps its OSM-Carto colour from `osm_carto.yaml`. This is the rule of `mode_settings`
   today for a class that a palette does not have.
3. The feature layers (water, land, buildings, …) keep their OSM-Carto colours. Only the roads change.
4. **The widths** are the profile `default` of roadstyle. `mode_settings` already starts from it, so no change.
5. **Where it is chosen:** `mapstyle --theme roadstyle`, `render_map(theme="roadstyle")`, and a fourth item in the plugin's dialog "Colours". The default stays `osm`.

Not changed: roadstyle, `edge_id`, the data, the drawing order.

## Tests

`themes()` lists `roadstyle`; the theme's road colours equal the palette `amber`; a page renders with it; the plugin dialog has four colour choices.

## Decision for Kaveh

Is a theme the right place? The other way is a path style (the colours of footways and cycleways only), which is not enough: the editor also changes the colours of the main roads.
