"""A duckOSM db as style.json + vector tiles for another map app (GeoLibre with the roadstyle plugin, RustGIS, QGIS):
the map of ``render_map`` (all modes' roads in the mode's style, the ``features.*`` base map), written by roadstyle's
``export_style``. The one input is the db.

    mapstyle monaco.duckdb --export out/monaco --base-url http://localhost:8795/monaco/

The page's layers.js styles the base map when the page opens (colour by kind, outlines, dashes, textures, icons, zoom
ranges); here the same values from the config (``feature_overlays``) go into the style, the images into its metadata."""
import json
import re

from mapstyle.map import PATHS, render_map


def _match(colors, default):
    vals = [x for k, c in colors.items() for x in (k, c)]
    return ["match", ["get", "kind"], *vals, default] if vals else default


def _swap(expr, value):
    """roadstyle's hover / select ``case`` kept around a new base colour (as layers.js's swap)."""
    return expr[:-1] + [value] if isinstance(expr, list) and expr and expr[0] == "case" else value


def _restyle(style, config):
    """The base-map layers of an exported style (source layer ``ov<i>``: feature_overlays' i-th layer) styled as layers.js
    styles them on the page: colour and outline by kind, dashes, textures, icons, zoom ranges. The images (icons, textures)
    go into the style's metadata (``roadstyle:images``); the roadstyle GeoLibre plugin adds them to the map."""
    layers, out = style["layers"], []
    paint = {"fill": "fill-color", "line": "line-color", "circle": "circle-color"}
    by_ov = {}
    for lyr in layers:
        m = re.fullmatch(r"ov(\d+)", lyr.get("source-layer") or "")
        if m:
            by_ov.setdefault(int(m.group(1)), []).append(lyr)
    extra = {}                                            # layer id -> layers to put right after it
    for i, lys in by_ov.items():
        L = config["layers"][i]
        body_type = lys[0]["type"]
        bodies = [x for x in lys if x["type"] == body_type]
        meta, vis = lys[0].get("metadata", {}), lys[0].get("layout", {}).get("visibility", "visible")
        p = paint.get(body_type)
        for b in bodies:
            if L.get("color_by") and p:
                b.setdefault("paint", {})[p] = _swap(b["paint"].get(p), _match(L["color_by"]["map"], L["color_by"]["default"]))
            if L.get("dash") and body_type == "line":
                b.setdefault("paint", {})["line-dasharray"] = L["dash"]
        for x in lys:
            if x["id"].endswith("-outline") and L.get("outline_by"):
                x["paint"]["line-color"] = _match(L["outline_by"]["map"], L["outline_by"]["default"])
        def new(spec, after):
            spec = {**spec, "source": lys[0]["source"], "source-layer": f"ov{i}", "metadata": meta,
                    "layout": {**spec.get("layout", {}), "visibility": vis}}
            extra.setdefault(after, []).append(spec)
            lys.append(spec)
        if L.get("patterns"):
            pats = L["patterns"]
            new({"id": f"ov{i}-pattern", "type": "fill", "filter": ["match", ["get", "kind"], list(pats), True, False],
                 "paint": {"fill-pattern": ["match", ["get", "kind"], *[x for kv in pats.items() for x in kv], next(iter(pats.values()))]}},
                bodies[0]["id"])
        if L.get("icon"):
            ic = L["icon"]
            size = ["interpolate", ["linear"], ["zoom"], *[x for z, sz in ic["size"] for x in (z, sz)]]
            on_edge = any("__rs_fl" in json.dumps(b.get("filter")) for b in bodies)
            for k, b in enumerate(bodies):
                new({"id": f"ov{i}-icon{k or ''}", "type": "symbol", **({"filter": b["filter"]} if on_edge and b.get("filter") else {}),
                     "layout": {"icon-image": ic["image"], "icon-allow-overlap": True, "icon-size": size,
                                "icon-rotate": ["coalesce", ["get", "bearing"], 0], "icon-rotation-alignment": "map"},
                     "paint": {"icon-opacity": ic["opacity"]}}, b["id"])
                # the circle stays as the click / hover target, unseen and as big as the icon (an icon is 48 px x icon-size)
                b["paint"].update({"circle-opacity": 0, "circle-stroke-width": 0,
                                   "circle-radius": ["interpolate", ["linear"], ["zoom"], *[x for z, sz in ic["size"] for x in (z, sz * 24)]]})
        if L.get("min_zoom"):
            for x in lys:
                x["minzoom"] = L["min_zoom"]
    for lyr in layers:
        out.append(lyr)
        out.extend(extra.get(lyr["id"], []))
    style["layers"] = out
    style.setdefault("metadata", {})["roadstyle:images"] = config["images"]


def export_style(db, out_dir, *, base_url, mode=None, paths=PATHS, theme="osm", **kwargs):
    """Write the map of ``db`` (``render_map(db, mode, paths=..., theme=...)``) as ``style.json`` + tiles + sprite into
    ``out_dir``, served at ``base_url``; return the path of ``style.json``. ``kwargs`` go to ``render_map``."""
    import roadstyle as rs

    def write(roads, palette, settings, kw, config):
        kw = {k: v for k, v in kw.items() if k not in ("basemap", "basemaps")}   # the app has its own base map
        for ov, L in zip(kw.get("overlays", []), config["layers"], strict=True):
            ov.visible = L["ticked"]           # as the page opens: a layer unticked in layers.yaml starts hidden (its own row in the app)
        path = rs.export_style(roads, out_dir, base_url=base_url, palette=palette, settings=settings, **kw)
        style = json.loads(path.read_text())
        _restyle(style, config)
        path.write_text(json.dumps(style, separators=(",", ":")))
        return path

    return render_map(db, mode, paths=paths, theme=theme, _export=write, **kwargs)
