#!/usr/bin/env python3
"""Compute a MULTIMODAL shortest path (duckOSM) and write it as `data/route.geojson` for the viewer.

Phase A of routing-on-the-base-map: no live backend — precompute a door-to-door trip and drop it next
to the baked base map; the viewer picks it up as an overlay (see render_merge's route layer). The trip is
a sequence of LEGS, each tagged with a `mode`:

    access (walk off-network)  ->  walking / cycling / driving legs  ->  access (walk off-network)

Each network edge carries its `edge_id`, `osm_id`, `mode`, per-edge length + speed; the file's `summary`
has door-to-door length / time / avg speed + a per-mode breakdown. Needs the `mm` schema
(`duckosm multimodal <db>`).

Usage:
    python render_route.py "26.6980,58.3560" "26.7480,58.3830" [render_dir] [start_mode] [end_mode]
      points are lng,lat ; render_dir defaults to render/basemap ; modes default to walking.
"""
import json
import sys
from pathlib import Path

import duckdb

from duckosm.routing import route_multimodal   # duckOSM importable (pip install -e ../duckOSM)

DB = "../duckOSM/data/db/tartu.duckdb"
WALK_MS = 1.4   # walking speed for the off-network access legs (m/s ~ 5 km/h)


def _pt(s):
    lng, lat = (float(x) for x in s.split(","))
    return lng, lat


def nearest_node(con, lng, lat, mode="walking"):
    """(node_id, lng, lat) of the mode's junction node closest to (lng, lat)."""
    return con.execute(
        f"SELECT node_id, ST_X(geom), ST_Y(geom) FROM {mode}.nodes "
        f"ORDER BY ST_Distance(geom, ST_Point(?, ?)) LIMIT 1", [lng, lat]).fetchone()


def sphere_m(con, a, b):
    return con.execute("SELECT ST_Distance_Sphere(ST_Point(?,?), ST_Point(?,?))",
                       [a[0], a[1], b[0], b[1]]).fetchone()[0]


def main():
    start = _pt(sys.argv[1]) if len(sys.argv) > 1 else (26.6980, 58.3560)
    end = _pt(sys.argv[2]) if len(sys.argv) > 2 else (26.7480, 58.3830)
    out = Path(sys.argv[3] if len(sys.argv) > 3 else "render/basemap")
    start_mode = sys.argv[4] if len(sys.argv) > 4 else "walking"
    end_mode = sys.argv[5] if len(sys.argv) > 5 else "walking"

    con = duckdb.connect(DB, read_only=True)
    con.execute("INSTALL spatial; LOAD spatial;")
    s_node, sx, sy = nearest_node(con, *start, start_mode)
    d_node, dx, dy = nearest_node(con, *end, end_mode)
    res = route_multimodal(con, s_node, d_node, start_mode=start_mode, end_mode=end_mode)
    if not res:
        print(f"no multimodal route between {s_node} and {d_node}")
        return

    pairs = res["edges"]        # [(mode, edge_id), …] in path order
    # hydrate each mode's edges once -> geometry + osm attrs + per-edge cost, keyed by (mode, edge_id)
    by_key = {}
    for mode in set(m for m, _ in pairs):
        eids = [e for m, e in pairs if m == mode]
        rows = con.execute(f"""
            SELECT e.edge_id, e.osm_id, e.highway, e.name, ROUND(e.length_m, 1), e.cost_s,
                   to_json(w.tags), ST_AsGeoJSON(e.geometry)
            FROM {mode}.edges e LEFT JOIN {mode}.ways w ON e.osm_id = w.osm_id
            WHERE e.edge_id IN ({','.join(map(str, eids))})
        """).fetchall()
        for r in rows:
            by_key[(mode, r[0])] = r

    feats, cum = [], 0.0
    by_mode = {}   # mode -> [length_m, time_s]

    def add_access(p0, p1):
        """A straight-line off-network WALK leg from p0 to p1 (point <-> nearest junction)."""
        nonlocal cum
        length = round(sphere_m(con, p0, p1), 1)
        t = length / WALK_MS
        cum += length
        by_mode.setdefault("access", [0.0, 0.0])
        by_mode["access"][0] += length; by_mode["access"][1] += t
        feats.append({"type": "Feature",
                      "geometry": {"type": "LineString", "coordinates": [list(p0), list(p1)]},
                      "properties": {"mode": "access", "len_m": length, "cum_m": round(cum, 1),
                                     "_i": {"layer": "route", "mode": "access", "class": "walk (off-network)",
                                            "name": "", "len_m": length, "speed_kmh": round(WALK_MS * 3.6, 1)}}})

    add_access(start, (sx, sy))                 # from the clicked start to the network
    for seq, (mode, eid) in enumerate(pairs):
        r = by_key.get((mode, eid))
        if not r:
            continue
        _, osm_id, hw, name, length_m, cost_s, tags, geo = r
        length_m = length_m or 0.0
        cost_s = float(cost_s) if cost_s else 0.0
        speed = round(length_m / cost_s * 3.6, 1) if cost_s else None   # km/h
        cum += length_m
        by_mode.setdefault(mode, [0.0, 0.0]); by_mode[mode][0] += length_m; by_mode[mode][1] += cost_s
        info = {"layer": "route", "edge_id": eid, "osm_id": osm_id, "mode": mode, "class": hw,
                "name": name or "", "len_m": length_m, "speed_kmh": speed,
                "tags": json.loads(tags) if tags else {}}
        feats.append({"type": "Feature", "geometry": json.loads(geo),
                      "properties": {"eid": eid, "mode": mode, "seq": seq, "len_m": length_m,
                                     "cum_m": round(cum, 1), "speed_kmh": speed, "_i": info}})
    add_access((dx, dy), end)                   # from the network to the clicked end

    total_len = round(sum(v[0] for v in by_mode.values()), 1)
    total_t = round(sum(v[1] for v in by_mode.values()), 1)
    fc = {"type": "FeatureCollection",
          "summary": {"length_m": total_len, "time_s": total_t,
                      "speed_kmh": round(total_len / total_t * 3.6, 1) if total_t else 0,
                      "by_mode": {m: {"length_m": round(v[0], 1), "time_s": round(v[1])}
                                  for m, v in by_mode.items()},
                      "transfers": len(res.get("transfers", []))},
          "start": list(start), "end": list(end), "features": feats}
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "data" / "route.geojson").write_text(json.dumps(fc))
    con.close()
    s = fc["summary"]
    legs = " + ".join(f"{m} {v['length_m']:.0f}m" for m, v in s["by_mode"].items())
    print(f"wrote {out}/data/route.geojson — {s['length_m']:.0f} m, {s['time_s']:.0f} s, "
          f"{s['speed_kmh']:.0f} km/h  [{legs}]")


if __name__ == "__main__":
    main()
