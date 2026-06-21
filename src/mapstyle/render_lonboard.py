"""lonboard (deck.gl / WebGL) backend — scales to 100k+ features.

Road layers reuse roadstyle's `resolve()` for per-edge casing+fill; polygon/point layers use
mapstyle's palettes. Each layer becomes one or two deck.gl layers, composed into a single
`lonboard.Map`. Distinct per-mode `color` overrides keep driving/cycling/walking separable.
"""

import numpy as np
from lonboard import Map, PathLayer, PolygonLayer, ScatterplotLayer

from mapstyle.roads import resolve_road
from mapstyle.palettes import polygon_style

_BASEMAP = {
    "light": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    "dark": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
}


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _road_layers(layer, theme):
    gdf = layer.gdf
    override = _rgb(layer.color) if layer.color else None
    fills, widths, cas, cws = [], [], [], []
    for hw in gdf["highway"].fillna("unclassified").tolist():
        s = resolve_road(hw)
        fills.append(override or _rgb(s.fill))
        widths.append(s.width)
        cas.append(_rgb(s.casing) if s.casing else (override or _rgb(s.fill)))
        cws.append(max(s.casing_width, s.width + 0.6) if s.casing else s.width)
    fills = np.array(fills, dtype=np.uint8)
    cas = np.array(cas, dtype=np.uint8)
    widths = np.array(widths, dtype=np.float32)
    cws = np.array(cws, dtype=np.float32)

    casing = PathLayer.from_geopandas(gdf, auto_downcast=False, get_color=cas, get_width=cws, width_units="pixels",
        width_min_pixels=0.6, opacity=0.75, pickable=False)
    fill = PathLayer.from_geopandas(
        gdf, auto_downcast=False, get_color=fills, get_width=widths, width_units="pixels",
        width_min_pixels=0.5, opacity=0.95, pickable=True)
    return [casing, fill]               # casing under, fill over


def _polygon_layers(layer):
    gdf = layer.gdf
    name = layer.name
    fills = np.array([_rgb(polygon_style(name, c)["fillColor"])
                      for c in gdf["class"].tolist()], dtype=np.uint8)
    stroked = name == "buildings"
    pl = PolygonLayer.from_geopandas(
        gdf, auto_downcast=False, get_fill_color=fills, opacity=0.85,
        stroked=stroked, filled=True, get_line_color=[194, 184, 172],
        get_line_width=0.5, line_width_units="pixels", pickable=True)
    return [pl]


def _point_layers(layer):
    gdf = layer.gdf
    sp = ScatterplotLayer.from_geopandas(
        gdf, auto_downcast=False, get_fill_color=[238, 153, 153], get_line_color=[102, 102, 102],
        get_radius=3, radius_units="pixels", stroked=True, get_line_width=0.5,
        line_width_units="pixels", opacity=0.85, pickable=True)
    return [sp]


def render(layers, theme="light"):
    deck = []
    for layer in sorted(layers, key=lambda x: x.z):
        if layer.kind == "line":
            deck += _road_layers(layer, theme)
        elif layer.kind == "polygon":
            deck += _polygon_layers(layer)
        elif layer.kind == "point":
            deck += _point_layers(layer)
        else:
            raise ValueError(f"unknown layer kind: {layer.kind!r}")
    style = _BASEMAP.get(theme, _BASEMAP["light"])
    return Map(deck, basemap_style=style)


def save(m, out):
    m.to_html(out)
