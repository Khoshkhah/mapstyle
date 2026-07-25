"""Folium backend: compose line/polygon/point layers onto one shared map.

Line layers reuse roadstyle's `resolve()` (the casing+fill styling brain); polygon/point
layers use mapstyle's own palettes. Each layer is added in z-order so they stack like an
OSM base map.
"""

import folium
from roadstyle.fastjson import fc_dict

from mapstyle.palettes import polygon_style

_BASEMAP = {"light": "cartodbpositron", "dark": "cartodbdark_matter", "satellite": None}


def _bounds(layers):
    b = None
    for L in layers:
        if L.gdf.empty:
            continue
        minx, miny, maxx, maxy = L.gdf.total_bounds
        if b is None:
            b = [minx, miny, maxx, maxy]
        else:
            b = [min(b[0], minx), min(b[1], miny), max(b[2], maxx), max(b[3], maxy)]
    return b


def _add_line(m, layer, theme):
    """Style each edge via roadstyle.resolve, then draw casing under fill (the sandwich)."""
    from mapstyle.roads import resolve_road

    gj = fc_dict(layer.gdf)
    for ft in gj["features"]:
        hw = ft["properties"].get("highway") or "unclassified"
        s = resolve_road(hw)
        p = ft["properties"]
        p["_f"], p["_w"], p["_o"] = s.fill, s.width, s.opacity
        p["_c"], p["_cw"], p["_co"] = (s.casing or "#000000"), (s.casing_width or 0), s.casing_opacity
        p["_d"] = ",".join(map(str, s.dash)) if s.dash else None

    folium.GeoJson(
        gj, name=f"{layer.name} · casing",
        style_function=lambda f: {
            "color": f["properties"]["_c"],
            "weight": f["properties"]["_cw"],
            "opacity": f["properties"]["_co"] if f["properties"]["_cw"] else 0,
            "lineCap": "round", "lineJoin": "round",
        },
    ).add_to(m)
    folium.GeoJson(
        gj, name=layer.name,
        style_function=lambda f: {
            "color": f["properties"]["_f"],
            "weight": f["properties"]["_w"],
            "opacity": f["properties"]["_o"],
            "dashArray": f["properties"]["_d"],
            "lineCap": "round", "lineJoin": "round",
        },
    ).add_to(m)


def _add_polygon(m, layer, theme):
    gj = fc_dict(layer.gdf)
    name = layer.name
    folium.GeoJson(
        gj, name=name,
        style_function=lambda f: polygon_style(name, f["properties"].get("class")),
    ).add_to(m)


def _add_point(m, layer, theme):
    fg = folium.FeatureGroup(name=layer.name)
    for _, row in layer.gdf.iterrows():
        g = row.geometry
        if g is None or g.geom_type != "Point":
            continue
        folium.CircleMarker([g.y, g.x], radius=2.5, color="#666666", weight=0.5,
                            fill=True, fill_color="#ee9999", fill_opacity=0.85,
                            popup=row.get("name")).add_to(fg)
    fg.add_to(m)


def render(layers, theme="light", zoom_start=13):
    b = _bounds(layers)
    center = [(b[1] + b[3]) / 2, (b[0] + b[2]) / 2] if b else [0, 0]
    m = folium.Map(location=center, zoom_start=zoom_start, tiles=_BASEMAP.get(theme, "cartodbpositron"))

    for layer in sorted(layers, key=lambda x: x.z):
        if layer.kind == "line":
            _add_line(m, layer, theme)
        elif layer.kind == "polygon":
            _add_polygon(m, layer, theme)
        elif layer.kind == "point":
            _add_point(m, layer, theme)
        else:
            raise ValueError(f"unknown layer kind: {layer.kind!r}")

    if b:
        m.fit_bounds([[b[1], b[0]], [b[3], b[2]]])
    folium.LayerControl(collapsed=False).add_to(m)
    return m


def save(m, out):
    m.save(out)
