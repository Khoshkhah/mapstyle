"""The base-map look for data layers in another app (the roadstyle GeoLibre plugin): MapLibre layers with no source, one
set per duckOSM ``features.*`` table, made from ``styles/layers.yaml`` (which layers, their ``kind`` filter, the draw order)
and the theme's ``features`` values (``styles/osm_carto.yaml``). duckOSM's GeoParquet export writes one file per table,
``features_<table>.parquet``; the plugin puts each look on the layer of that name.

Not in the look (the page has them): textures, icons (points are dots in the icon's colour), centroid points."""
import json
import re
from pathlib import Path

from mapstyle.style import load_style, load_theme

OUTLINE_W = 0.5      # the same as map.feature_overlays; it moves into the config with step 3 of roadstyle's style_config.md
POINT_R = 4
_GEOM = {"polygon": ["Polygon", "MultiPolygon"], "line": ["LineString", "MultiLineString"], "point": ["Point", "MultiPoint"]}


def _where(where):
    """The MapLibre filter for a ``layers.yaml`` ``where``. Only ``kind = '…'`` and ``kind IN (…)`` are known."""
    if not where:
        return None
    m = re.fullmatch(r"\s*kind\s+IN\s*\((.*)\)\s*", where, re.I)
    if m:
        return ["in", ["get", "kind"], ["literal", re.findall(r"'([^']*)'", m.group(1))]]
    m = re.fullmatch(r"\s*kind\s*=\s*'([^']*)'\s*", where)
    if m:
        return ["==", ["get", "kind"], m.group(1)]
    raise ValueError(f"export_look reads only kind = '…' and kind IN (…) in layers.yaml, not: {where}")


def _by_kind(colors, default):
    vals = [x for k, c in colors.items() if k != "default" for x in (k, c)]
    return ["match", ["get", "kind"], *vals, default] if vals else default


def export_look(path=None, *, theme: str = "osm") -> dict:
    """``{"name", "order", "files": {"features_<table>": {"layers", "hover", "popup", "columns"}}, "not_drawn"}``, written to ``path``
    if given. ``order`` is the tables in the draw order of their first layer. ``hover``: the feature under the cursor (the plugin sets
    which ``osm_id`` the filter keeps), in roadstyle's selection colour; ``popup``: the columns of ``layers.yaml``'s ``popup``."""
    from roadstyle import _settings
    st = load_theme(theme)[0]["features"]
    rt = _settings.theme()                    # the hover as on the page: roadstyle's selection colour and its overlay sizes
    sel, ov = rt["selection"], rt["overlays"]
    hover = {"polygon": {"type": "line", "paint": {"line-color": sel["hover"], "line-opacity": sel["opacity"], "line-width": ov["width"]}},
             "line": {"type": "line", "paint": {"line-color": sel["hover"], "line-opacity": sel["opacity"], "line-width": ov["width"]}},
             "point": {"type": "circle", "paint": {"circle-color": sel["hover"], "circle-opacity": sel["opacity"], "circle-radius": ov["radius"]}}}
    popup = load_style("layers")["popup"]
    areas, lines, points = st["areas"], st["lines"], st["points"]
    files, order, not_drawn = {}, [], []
    for s in load_style("layers")["layers"]:
        if not s.get("show", True):
            continue
        name, kind, table = s.get("merge_into") or s["name"], s["kind"], s["table"]
        if s.get("centroid"):
            not_drawn.append({"layer": s["name"], "why": "a point at the centre of an area: the look draws no centroids"})
            continue
        if table not in order:
            order.append(table)
        flt = ["all", ["in", ["geometry-type"], ["literal", _GEOM[kind]]], *[f for f in [_where(s.get("where"))] if f]]
        fl = files.setdefault(f"features_{table}", {"layers": [], "hover": {"id": "osm_id", "layers": []},
                                                    "popup": {"title": "name", "columns": [c for c in popup if c != "name"]}})
        out = fl["layers"]
        if kind not in {h.get("kind") for h in fl["hover"]["layers"]}:
            fl["hover"]["layers"].append({"id": "hover-" + kind, "kind": kind, "filter": ["in", ["geometry-type"], ["literal", _GEOM[kind]]], **hover[kind]})
        lid = s["name"]
        if name == "landcover":
            fills = dict(areas["landcover"])
            out.append({"id": lid, "type": "fill", "filter": flt,
                        "paint": {"fill-color": _by_kind(fills, fills["default"]), "fill-opacity": 1.0}})
            ol = st.get("landcover_outline") or {}
            if ol:
                out.append({"id": lid + "-outline", "type": "line", "filter": ["all", flt, ["in", ["get", "kind"], ["literal", list(ol)]]],
                            "paint": {"line-color": _by_kind(ol, next(iter(ol.values()))), "line-width": 1}})   # the filter keeps only listed kinds
        elif kind == "polygon":
            a = areas[name]
            out.append({"id": lid, "type": "fill", "filter": flt, "paint": {"fill-color": a["fill"], "fill-opacity": a.get("opacity", 1.0)}})
            if a.get("outline"):
                out.append({"id": lid + "-outline", "type": "line", "filter": flt,
                            "paint": {"line-color": a["outline"], "line-width": OUTLINE_W, "line-opacity": a.get("opacity", 1.0)}})
            if a.get("min_zoom"):
                for la in out[-2 if a.get("outline") else -1:]:
                    la["minzoom"] = a["min_zoom"]
        elif kind == "line":
            ln = lines[name]
            paint = {"line-color": ln["color"], "line-width": ln["width"]}
            if ln.get("dash"):
                paint["line-dasharray"] = ln["dash"]
            out.append({"id": lid, "type": "line", "filter": flt, "paint": paint})
        else:
            p = {**points["default"], **points.get(name, {})}
            out.append({"id": lid, "type": "circle", "filter": flt, "minzoom": p["min_zoom"],
                        "paint": {"circle-color": p["color"], "circle-radius": POINT_R}})
    for f in files.values():
        f["columns"] = ["kind"]
        for h in f["hover"]["layers"]:
            h.pop("kind")
    look = {"name": f"mapstyle {theme}", "order": order, "files": files, "not_drawn": not_drawn}
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(look, separators=(",", ":")))
    return look
