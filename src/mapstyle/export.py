"""A duckOSM db as style.json + vector tiles for another map app (GeoLibre with the roadstyle plugin, RustGIS, QGIS):
the map of ``render_map`` (all modes' roads in the mode's style, the ``features.*`` base map), written by roadstyle's
``export_style``. The one input is the db.

    mapstyle monaco.duckdb --export out/monaco --base-url http://localhost:8795/monaco/

The page's layers.js colours the base map when the page opens (colour by kind, outlines, zoom ranges, dashes); here the
same values from the config (``feature_overlays``) go into the style. Not in it yet: textures and icons (points are dots in
the icon's colour)."""
import json
import re

from mapstyle.map import PATHS, render_map


def _match(colors, default):
    vals = [x for k, c in colors.items() for x in (k, c)]
    return ["match", ["get", "kind"], *vals, default] if vals else default


def _restyle(style, config):
    """The base-map layers of an exported style (source layer ``ov<i>``: feature_overlays' i-th layer) with layers.js's
    colours, outlines, zoom ranges and dashes."""
    for lyr in style["layers"]:
        m = re.fullmatch(r"ov(\d+)", lyr.get("source-layer") or "")
        if not m:
            continue
        L = config["layers"][int(m.group(1))]
        paint = lyr.setdefault("paint", {})
        if lyr["type"] == "fill" and L.get("color_by"):
            paint["fill-color"] = _match(L["color_by"]["map"], L["color_by"]["default"])
        if lyr["id"].endswith("-outline") and L.get("outline_by"):
            paint["line-color"] = _match(L["outline_by"]["map"], L["outline_by"]["default"])
        if lyr["type"] == "line" and L.get("dash"):
            paint["line-dasharray"] = L["dash"]
        if L.get("min_zoom"):
            lyr["minzoom"] = L["min_zoom"]


def export_style(db, out_dir, *, base_url, mode=None, paths=PATHS, theme="osm", **kwargs):
    """Write the map of ``db`` (``render_map(db, mode, paths=..., theme=...)``) as ``style.json`` + tiles + sprite into
    ``out_dir``, served at ``base_url``; return the path of ``style.json``. ``kwargs`` go to ``render_map``."""
    import roadstyle as rs

    def write(roads, palette, settings, kw, config):
        kw = {k: v for k, v in kw.items() if k not in ("basemap", "basemaps")}   # the app has its own base map
        for ov in kw.get("overlays", []):
            ov.visible = True                  # the page shows them once layers.js has styled them; here they are styled already
        path = rs.export_style(roads, out_dir, base_url=base_url, palette=palette, settings=settings, **kw)
        style = json.loads(path.read_text())
        _restyle(style, config)
        path.write_text(json.dumps(style, separators=(",", ":")))
        return path

    return render_map(db, mode, paths=paths, theme=theme, _export=write, **kwargs)
