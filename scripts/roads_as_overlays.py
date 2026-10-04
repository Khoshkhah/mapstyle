"""Experiment: draw ALL roads as edge-attached overlays instead of roadstyle's own road fill
(docs/design/roads_as_overlays.md). The page is the same map, with `road_fill=False` (roadstyle keeps
each road's casing, its fill is invisible) and the fill drawn by `rs.Overlay(edge_col=..., order_col=...)`.

    .venv/bin/python scripts/roads_as_overlays.py ../duckOSM/data/db/monaco.duckdb -o render/roads_as_overlays.html

mapstyle's `render_map` runs unchanged: `rs.render_edges` is wrapped here to add the road overlays.
Not a library feature (it costs more than it gains, see the design note); it is the recipe for a
library that draws the fill itself (lanestyle). It uses two private names of roadstyle:
`render_web._width_expr` (the per-class zoom width of a road's fill) and `render_web.ROAD_Z`.
"""
import argparse

import roadstyle as rs
from roadstyle import render_web as rw

import mapstyle.map as m


def _order(highway):
    """roadstyle's own class order (`ROAD_Z`, a link just under its parent), as a whole number."""
    h = highway or ""
    base = h.removesuffix("_link")
    return int(10 * rw.ROAD_Z.get(h, rw.ROAD_Z.get(base, 4) - (0.5 if h != base else 0)))


def _feature_collection(g):
    """One feature per edge: its own geometry and the `edge_id` roadstyle puts at the edge's fill number."""
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": geom.__geo_interface__,
         "properties": {"edge_id": str(e), "highway": h, "fill": c, "order": _order(h)}}   # edge_id as text: it can pass 2**53
        for e, h, c, geom in zip(g["edge_id"], g["highway"], g["_color"], g.geometry)]}


def road_overlays(roads, palette, canvas):
    """The roads' fill as overlays: roadstyle's own resolved colour and opacity per edge (the same `__rs_fill` / `__rs_op`
    its page bakes), grouped by opacity; the zoom width is roadstyle's expression for the class."""
    frame = rs.build_styler(palette=palette, highway_col="highway", tunnel_col="tunnel", bridge_col="bridge").resolve_frame(roads)
    roads = roads.copy()
    roads["_op"] = [float(x) for x in frame.opacity]
    normal = roads["_op"].max()                  # a faded fill (a tunnel) has less than a plain road's; roadstyle decides which
    def faded_onto_canvas(fill, op):             # a tunnel's opaque underlay in the canvas colour is part of its look
        return "#" + "".join(f"{round(int(fill[i:i + 2], 16) * op + int(canvas[i:i + 2], 16) * (1 - op)):02x}" for i in (1, 3, 5))
    roads["_faded"] = roads["_op"] < normal
    roads["_color"] = [faded_onto_canvas(f, o) if t else f for f, o, t in zip(frame.fill, roads["_op"], roads["_faded"], strict=True)]
    width = rw._width_expr("highway")
    return [rs.Overlay(_feature_collection(g), edge_col="edge_id", order_col="order", color_col="fill", kind="line", width=width,
                       opacity=1.0 if faded else op, label="roads" + (" (faded)" if faded else ""), popup=[])
            for (op, faded), g in roads.groupby(["_op", "_faded"])]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("db", help="a duckOSM db")
    ap.add_argument("-o", "--out", default="render/roads_as_overlays.html")
    args = ap.parse_args(argv)

    render_edges = rs.render_edges

    def wrapped(roads, *a, **kw):
        rs.use_settings(kw["settings"])           # the palette's colours and widths, as render_edges applies them
        kw["overlays"] = list(kw["overlays"]) + road_overlays(roads, kw["palette"], rs.get_basemap("blank").bg)
        kw["road_fill"] = False                   # the casing stays roadstyle's; the fill is the overlays
        return render_edges(roads, *a, **kw)

    rs.render_edges = wrapped
    page = m.render_map(args.db)
    page.save(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
