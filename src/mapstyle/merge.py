"""Merge the three mode networks into ONE multi-modal edge set.

Key insight (validated on Tartu): `edge_id` is stable across modes, so the same physical
segment has the same id in driving/walking/cycling. Merging by `edge_id` gives one edge per
segment with three mode flags (driving/walking/cycling) instead of 106k overlapping rows ->
68k distinct edges. This is the model to implement in duckOSM (a single edges table with
per-mode access flags, not three schemas).

`merge_modes()` does the merge; `render_merge()` writes a viewer that styles the merged set
by OSM class, filters it by mode (checkboxes), or colors it by mode-combination (to *see* the
merge).
"""

import json
import math
from collections import Counter
from pathlib import Path

from mapstyle.layers import Layer
from mapstyle.roads import resolve_road, road_z, road_group
from mapstyle.style import load_style

# mode-combination -> color (for the "color by: Modes" view)
COMBO_COLOR = {
    "dwc": "#555555",   # all three (shared by everyone)
    "dc": "#9b59b6",    # drive + cycle
    "dw": "#e67e22",    # drive + walk
    "wc": "#16a085",    # walk + cycle
    "d": "#e74c3c",     # drive only
    "c": "#2b6cb0",     # cycle only
    "w": "#27ae60",     # walk only
}


# service roads whose `service=*` subtag makes them the narrower `service_minor` width group
_SVC_MINOR = ("driveway", "parking_aisle", "drive-through", "drive_through")


def _group_of(hw, svc=None):
    """road_group(hw), but split driveways/parking-aisles off to the narrower `service_minor`."""
    g = road_group(hw)
    if g == "service" and str(svc).strip().lower() in _SVC_MINOR:
        g = "service_minor"
    return g


def _base_m(hw, svc, oneway, wm):
    """Physical base width (metres) of a road/direction = lanes x lane_m[class] — BOTH from config
    (``roads.width_model``), NOT from OSM lane tags (too noisy). A ONE-WAY road uses ``lanes_oneway``
    (total lanes of the carriageway); a TWO-WAY road uses ``lanes`` (lanes per direction; 0.5 =
    single-track). So a secondary renders wider one-way (dual carriageway) than one two-way direction.
    See docs/width-model.md."""
    g = _group_of(hw, svc)
    lane_m = wm.get("lane_m") or {}
    tbl = (wm.get("lanes_oneway") if oneway else wm.get("lanes")) or {}
    lm = lane_m.get(g, lane_m.get("default", 3.0))
    n = tbl.get(g, tbl.get("default", 1))
    return n * lm


def _offset_two_way(gdf):
    """Offset each two-way edge sideways by its OWN baked per-direction offset (``gdf['off']`` metres,
    = base_width/2) so the two directions sit edge-to-edge beside the centreline; one-way edges
    (``off``=0) stay centred. Purely GLOBAL / per-class (physical width model) — no junction
    awareness. Done in a local UTM CRS; a degenerate offset falls back to the centreline."""
    import geopandas as gpd

    if "off" not in gdf:
        return gdf
    m_crs = gdf.estimate_utm_crs()
    m = gdf.to_crs(m_crs)
    out = []
    for geom, d in zip(m.geometry, m["off"]):
        d = float(d) if d == d else 0.0                        # NaN-safe
        if not d or geom is None or geom.is_empty:
            out.append(geom)
            continue
        try:
            o = geom.offset_curve(d)
            if o is not None and not o.is_empty:
                if o.geom_type == "MultiLineString":
                    o = max(o.geoms, key=lambda g: g.length)   # keep the longest part -> stay a LineString
                out.append(o if o.geom_type == "LineString" else geom)
            else:
                out.append(geom)
        except Exception:
            out.append(geom)
    m["geometry"] = gpd.GeoSeries(out, index=m.index, crs=m_crs)
    return m.to_crs("EPSG:4326")


def merge_modes(db, modes=("driving", "walking", "cycling")):
    """Return one Layer of distinct edges (by edge_id) with driving/walking/cycling flags.

    Reads the per-mode routing graphs straight from a duckOSM db (``<mode>.edges``) — the single
    source of truth. duckOSM edges are DIRECTED: a two-way segment keeps BOTH its forward and
    reverse rows (different edge_ids on purpose), and ``_offset_two_way`` fans that pair into two
    parallel lanes — the both-directions look. A one-way street has only its single directed edge
    (stays centred). ``highway``/``geometry`` are aliased to the ``class``/``geom`` the styling
    code expects.
    """
    import duckdb
    import geopandas as gpd
    import shapely.wkt as wkt

    con = duckdb.connect(db, read_only=True)
    con.execute("INSTALL spatial; LOAD spatial;")
    union = " UNION ALL ".join(
        f"SELECT e.edge_id, e.highway AS class, e.geometry AS geom, e.name, e.length_m, "
        f"e.layer, e.bridge, e.tunnel, e.service, e.oneway, "
        f"TRY_CAST(w.tags['lanes'] AS INTEGER) AS lanes, "   # raw OSM TOTAL lanes tag (info only; width is class-fixed)
        f"'{m}' AS mode FROM {m}.edges e LEFT JOIN {m}.ways w ON e.osm_id = w.osm_id" for m in modes)
    rows = con.execute(f"""
        SELECT edge_id,
               any_value(class)             AS class,
               ST_AsText(any_value(geom))   AS wkt,
               any_value(name)              AS name,
               max(length_m)                AS length_m,
               any_value(layer)             AS layer,
               any_value(bridge)            AS bridge,
               any_value(tunnel)            AS tunnel,
               any_value(service)           AS service,
               bool_or(oneway)              AS oneway,
               any_value(lanes)             AS lanes,
               bool_or(mode = 'driving')    AS d,
               bool_or(mode = 'walking')    AS w,
               bool_or(mode = 'cycling')    AS c
        FROM ({union})
        GROUP BY edge_id
    """).fetchall()
    con.close()

    rec = {"edge_id": [], "highway": [], "name": [], "length_m": [],
           "layer": [], "bridge": [], "tunnel": [], "service": [], "oneway": [], "lanes": [],
           "driving": [], "walking": [], "cycling": [], "combo": []}
    geoms = []
    for eid, cls, geom_wkt, nm, length_m, lyr, brg, tun, svc, ow, lns, is_d, is_w, is_c in rows:
        combo = "".join(k for k, v in (("d", is_d), ("w", is_w), ("c", is_c)) if v)
        rec["edge_id"].append(eid); rec["highway"].append(cls)
        rec["name"].append(nm); rec["length_m"].append(length_m)
        rec["layer"].append(lyr); rec["bridge"].append(brg); rec["tunnel"].append(tun)
        rec["service"].append(svc); rec["oneway"].append(bool(ow)); rec["lanes"].append(lns)
        rec["driving"].append(bool(is_d)); rec["walking"].append(bool(is_w)); rec["cycling"].append(bool(is_c))
        rec["combo"].append(combo)
        geoms.append(wkt.loads(geom_wkt))
    gdf = gpd.GeoDataFrame(rec, geometry=geoms, crs="EPSG:4326")
    # PHYSICAL width model (see docs/width-model.md): each DIRECTED edge's base width (metres) =
    # its lane count x lane_m[class]. A two-way road = its two directed edges, each offset sideways
    # by base/2 (baked here, in metres) so they sit edge-to-edge; one-way roads stay centred. Paths /
    # footways (`path` group) are drawn as a single dashed line, never split. The render width is then
    # base_m x (1/mpp) x zoom_boost(zoom) — computed per-zoom in the viewer, sharing this base_m.
    wm = (load_style().get("roads") or {}).get("width_model") or {}
    gdf["bm"] = [_base_m(hw, svc, ow, wm)
                 for hw, svc, ow in zip(gdf["highway"], gdf["service"], gdf["oneway"])]
    gdf["lane"] = [(not bool(ow)) and road_group(hw) != "path"
                   for hw, ow in zip(gdf["highway"], gdf["oneway"])]
    gdf["off"] = [bm / 2.0 if ln else 0.0 for bm, ln in zip(gdf["bm"], gdf["lane"])]
    gdf = _offset_two_way(gdf)             # offset each two-way direction by its own base/2 (metres)
    return Layer("roads_merged", gdf, "line")


def merge_stats(layer):
    """Print + return the merge breakdown by mode-combination."""
    c = Counter(layer.gdf["combo"])
    names = {"dwc": "all three", "dc": "drive+cycle", "dw": "drive+walk",
             "wc": "walk+cycle", "d": "drive only", "c": "cycle only", "w": "walk only"}
    total = len(layer.gdf)
    print(f"merged edges: {total:,}")
    for combo, n in sorted(c.items(), key=lambda kv: -kv[1]):
        print(f"  {combo:3s} {names.get(combo, combo):12s} {n:6,}  ({100*n/total:4.1f}%)")
    return dict(c)


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _darker(rgb, f=0.6):
    """A darker shade of an [r,g,b] colour — used for landcover pattern symbols over the fill."""
    return [int(c * f) for c in rgb]


def _layer_int(v):
    """OSM `layer` tag (string, e.g. '1', '-1') -> int; default 0."""
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _straight_run(geom, fc, steps=40, perp_frac=0.10, perp_floor=3.0):
    """At fraction `fc` along `geom`: the point [lon,lat], the screen-space angle there (deck CCW
    from east, Web-Mercator latitude-corrected like the arrows), and `fit_m` — the CONTIGUOUS
    straight run of road CENTRED on that point. Walking out each way stops where the road leaves a
    narrow cone around the local tangent (perp > perp_frac*along + perp_floor m), so a straight,
    centred label of <= fit_m metres lies FULLY on the road (not merely within its extent)."""
    d = 0.01
    m = geom.interpolate(fc, normalized=True)
    a = geom.interpolate(max(fc - d, 0.0), normalized=True)
    b = geom.interpolate(min(fc + d, 1.0), normalized=True)
    cl = math.cos(math.radians(m.y)) or 1e-6
    tx, ty = (b.x - a.x) * cl, (b.y - a.y)                  # tangent (lon scaled to lat metres)
    tn = math.hypot(tx, ty) or 1e-9
    tx, ty = tx / tn, ty / tn
    ang = math.degrees(math.atan2((b.y - a.y) / cl, b.x - a.x))

    def run(sign):
        last = 0.0
        for i in range(1, steps + 1):
            fr = fc + sign * (i / steps) * 0.5
            if fr < 0.0 or fr > 1.0:
                break
            q = geom.interpolate(fr, normalized=True)
            ax = (q.x - m.x) * cl * 111320
            ay = (q.y - m.y) * 111320
            along = ax * tx + ay * ty
            if abs(-ax * ty + ay * tx) > perp_frac * abs(along) + perp_floor:
                break                                       # road left the tangent cone -> stop
            last = abs(along)
        return last

    fit_m = 2 * min(run(1), run(-1))
    na = ang
    while na > 90:
        na -= 180
    while na <= -90:
        na += 180
    return [round(m.x, 6), round(m.y, 6)], round(na, 1), fit_m


def _label_candidates(geom, stride_m=80):
    """Name-label candidates along `geom`: one every ~stride_m, each a (pos, na, fit_m) from
    `_straight_run`. Long roads thus get several candidates (more places to show the name); the
    viewer keeps those that fit at the current zoom and collision-places them."""
    out = []
    try:
        n = max(1, round(geom.length * 111320 / stride_m))
        for k in range(n):
            out.append(_straight_run(geom, (k + 0.5) / n))
    except Exception:
        pass
    return out


_ARROW_STEP_M = 18   # base sample spacing; the viewer subsamples by zoom for ~constant px spacing


def _arrow_points(geom, spacing_m=_ARROW_STEP_M):
    """Sample points along a oneway line every ~spacing_m. Returns (pos, angle, seq) where the
    angle is the screen-space direction in Web Mercator (latitude-corrected: north-south is
    stretched by 1/cos(lat)), in deck CCW degrees so a right-pointing icon follows travel."""
    try:
        n = max(1, int(geom.length * 111320 / spacing_m))
        out = []
        for i in range(n):
            frac = (i + 0.5) / n
            p = geom.interpolate(frac, normalized=True)
            a = geom.interpolate(max(frac - 0.5 / n, 0.0), normalized=True)
            b = geom.interpolate(min(frac + 0.5 / n, 1.0), normalized=True)
            coslat = math.cos(math.radians(p.y)) or 1e-6
            ang = math.degrees(math.atan2((b.y - a.y) / coslat, b.x - a.x))
            out.append(([round(p.x, 6), round(p.y, 6)], round(ang, 1), i))
        return out
    except Exception:
        return []


# road groups that get name labels (skip service/driveways/paths)
NAME_GROUPS = {"major", "primary", "secondary", "tertiary", "residential", "living_street", "pedestrian"}

# boundary toggle row, injected into the panel only when a boundary overlay is present
_BOUND_ROW = '<label><input type="checkbox" id="boundary" checked> city boundary</label>'


def _load_boundary(src):
    """Boundary-overlay source -> a GeoJSON FeatureCollection (geometry only), or None.
    `src` may be a path to a .geojson (FeatureCollection / Feature / bare geometry), a shapely
    geometry, or None (no overlay)."""
    if src is None:
        return None
    if isinstance(src, (str, Path)):
        p = Path(src)
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        if data.get("type") == "FeatureCollection":
            geoms = [f["geometry"] for f in data["features"] if f.get("geometry")]
        elif data.get("type") == "Feature":
            geoms = [data["geometry"]]
        else:
            geoms = [data]
    else:                                    # assume a shapely geometry
        import shapely.geometry as sg
        geoms = [sg.mapping(src)]
    feats = [{"type": "Feature", "properties": {}, "geometry": g} for g in geoms if g]
    return {"type": "FeatureCollection", "features": feats} if feats else None


def render_merge(layer, out_dir, basemap="osm", title="Debug Visualization", overlays=(),
                 boundary=None, feature_layers=None, zoom=13, center=None):
    """Write a viewer for the merged set: OSM/Modes coloring + per-mode filter + base selector.

    feature_layers: optional list of mapstyle ``Layer`` (water/land/buildings/…) drawn UNDER the
    roads as separate, toggleable base-map layers — so the same viewer keeps the per-zoom road
    widths + names + arrows AND shows the filterable feature layers.

    overlays: which label overlays start ON (also toggleable in the viewer). Any of
    ``"arrows"`` (oneway direction arrows, shown at zoom >=16) and ``"names"`` (street-name
    labels, zoom >=14). e.g. ``overlays=("names", "arrows")`` for both.
    boundary: optional clip/area boundary to overlay as a purple dashed outline — a path to a
    .geojson, a shapely geometry, or None. Shown on top, toggleable in the viewer.
    """
    import shapely.geometry as sg
    from mapstyle.render_web import BASEMAPS, _BM_ALIAS, write_serve

    _style = load_style()
    astyle = _style.get("arrows", {})
    a_sample = astyle.get("sample_m", _ARROW_STEP_M)   # along-road bake step (metres)
    nstyle = _style.get("names", {})
    n_sample = nstyle.get("sample_m", 80)              # label-candidate spacing along each road
    rmz = {str(k).strip().lower(): v for k, v in ((_style.get("roads") or {}).get("min_zoom") or {}).items()}

    wm = (_style.get("roads") or {}).get("width_model") or {}   # physical width model (lane_m / …)
    out = Path(out_dir); (out / "data").mkdir(parents=True, exist_ok=True)
    feats = []
    gdf = layer.gdf
    label_feats = []   # name-label candidates: one per named piece (the viewer fits + places them)
    arrow_feats = []   # oneway arrow markers, sampled along the lines (OSM-style)
    con_flags = gdf["is_construction"] if "is_construction" in gdf else [False] * len(gdf)
    lane_flags = gdf["lane"] if "lane" in gdf else [False] * len(gdf)
    bm_vals = gdf["bm"] if "bm" in gdf else [None] * len(gdf)
    for geom, eid, hw, nm, length_m, lyr, brg, tun, svc, ow, lns, combo, d, w, c, iscon, lane, bmv in zip(
            gdf.geometry, gdf.edge_id, gdf.highway, gdf.name, gdf.length_m,
            gdf.layer, gdf.bridge, gdf.tunnel, gdf.service, gdf.oneway, gdf.get("lanes", [None] * len(gdf)),
            gdf.combo, gdf.driving, gdf.walking, gdf.cycling, con_flags, lane_flags, bm_vals):
        if geom is None or geom.is_empty:
            continue
        lane = bool(lane) if lane == lane else False   # NaN-safe: rows added later (construction) lack it
        bm = float(bmv) if bmv == bmv and bmv is not None else _base_m(hw, svc, ow, wm)   # construction: derive
        s = resolve_road(hw)
        layer = _layer_int(lyr)
        is_bridge = bool(brg) and str(brg).strip().lower() not in ("", "no")
        is_tunnel = bool(tun) and str(tun).strip().lower() not in ("", "no")
        casing = "#34343a" if is_bridge else s.casing   # bridges get a dark casing (OSM)
        fill, dash = s.fill, s.dash
        if iscon:                                        # highway=construction: grey road, but keep
            fill, casing, dash = "#bdbdbd", "#8f8f8f", None   # its FUTURE class's width/shape (hw)
        g = _group_of(hw, svc)                            # width group (+ driveway/aisle -> service_minor)
        if nm and g in NAME_GROUPS:                       # name-label candidates ALONG the piece
            pr = road_z(hw)
            full_bm = round(bm * (2 if lane else 1), 2)   # painted road width (both directions if two-way)
            for pos, na, fit_m in _label_candidates(geom, n_sample):
                if fit_m >= 20:                           # skip points without room for any name
                    label_feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": pos},
                        "properties": {"nm": nm, "na": na, "len": round(fit_m), "pr": pr, "g": g, "bm": full_bm}})
        if ow:                                            # oneway -> arrows along the line
            for pos, ang, seq in _arrow_points(geom, a_sample):
                arrow_feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": pos},
                                    "properties": {"ang": ang, "seq": seq, "g": g, "bm": round(bm, 2)}})
        feats.append({"type": "Feature", "geometry": sg.mapping(geom), "properties": {
            "c": _rgb(fill),
            "cc": _rgb(casing) if casing else None,
            "dash": list(dash) if dash else None,
            "cb": _rgb("#bdbdbd") if iscon else _rgb(COMBO_COLOR.get(combo, "#999999")),
            "md": bool(d), "mw": bool(w), "mc": bool(c),
            "eid": str(eid), "hw": hw, "nm": nm,
            "len": round(length_m) if length_m else None,
            # draw order: class rank + 10*layer (bridges up, tunnels down) — osm2pgsql z_order
            "z": road_z(hw) + 10 * layer, "g": g,
            "lk": bool(hw) and str(hw).strip().lower().endswith("_link"),
            "ln": bool(lane),   # two-way direction -> width x lane_overlap so the pair overlaps (no seam)
            "lanes": int(lns) if lns == lns and lns is not None else None,   # OSM lane tag (info only; width is class-fixed)
            "bm": round(bm, 2),   # physical base width of THIS direction (metres); width_px = bm/mpp*zoom_boost
            "br": is_bridge, "tn": is_tunnel, "lv": layer, "ow": bool(ow),
            "mz": rmz.get(str(hw).strip().lower(), 0),   # class hidden below this zoom (roads.min_zoom)
        }})
    # OSM draw order: low rank first (back) -> major roads last (front)
    feats.sort(key=lambda f: f["properties"]["z"])
    (out / "data" / "roads_merged.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}))

    # name-label candidates (one per named piece): each carries `na` (Mercator-correct, upright),
    # `len` = fit_m (straight centred span, m) and `pr` (road rank). The viewer keeps the ones that
    # fit at the current zoom, then collision-places them — repeating a name along long roads but
    # never overlapping another label.
    (out / "data" / "labels.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": label_feats}))
    (out / "data" / "arrows.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": arrow_feats}))

    bnd = _load_boundary(boundary)            # optional clip/area boundary outline
    if bnd is not None:
        (out / "data" / "boundary.geojson").write_text(json.dumps(bnd))
    has_bound = bnd is not None

    minx, miny, maxx, maxy = gdf.total_bounds
    center = center or [(minx + maxx) / 2, (miny + maxy) / 2]
    default_bm = _BM_ALIAS.get(basemap, basemap if basemap in BASEMAPS else "OSM Standard")
    legend = "".join(
        f'<span style="color:{COMBO_COLOR[k]}">&#9632;</span> {v}<br>' for k, v in
        [("dwc", "all 3"), ("dc", "drive+cycle"), ("dw", "drive+walk"),
         ("wc", "walk+cycle"), ("d", "drive only"), ("c", "cycle only"), ("w", "walk only")])
    # feature base layers (water/land/buildings/POIs/…) — drawn UNDER the roads, each toggleable.
    # ALL styling (fills, line colour/width/dash, point colour/size/icon) comes from the stylesheet's
    # `features:` block — nothing is hard-coded here. Style a layer by naming it in feature_layers
    # and adding an entry under features.areas / features.lines / features.points in the YAML.
    import shapely.geometry as _sg
    fcfg = _style.get("features", {})
    areas_cfg, lines_cfg, points_cfg = fcfg.get("areas", {}), fcfg.get("lines", {}), fcfg.get("points", {})
    feature_defs = []
    for fl in (feature_layers or []):
        fk = "polygon" if fl.kind in ("polygon", "area") else ("point" if fl.kind == "point" else "line")
        classes = fl.gdf["class"] if "class" in fl.gdf else fl.gdf.get("highway", [None] * len(fl.gdf))
        ff = []
        fdef = {"id": fl.name, "kind": fk}
        if fk == "polygon":
            spec = areas_cfg.get(fl.name, {})
            by_class = "fill" not in spec                       # e.g. landcover: {class: colour, default: …}
            outline = None if by_class else spec.get("outline")
            opacity = 0.85 if by_class else spec.get("opacity", 0.85)
            fdef["mz"] = spec.get("min_zoom", 0)                 # hide this area layer below this zoom
            pat_map = fcfg.get(f"{fl.name}_pattern") or {}       # per-class OSM texture (patterns.py tile)
            out_map = fcfg.get(f"{fl.name}_outline") or {}       # per-class OSM border colour
            for gm, cls in zip(fl.gdf.geometry, classes):
                if gm is None or gm.is_empty:
                    continue
                fill = spec.get(cls, spec.get("default", "#e8e6df")) if by_class else spec.get("fill", "#e8e6df")
                props = {"fc": _rgb(fill) + [int(opacity * 255)]}
                if cls in out_map:                               # OSM border on this class
                    props["oc"] = _rgb(out_map[cls]) + [235]
                if cls in pat_map:                               # OSM texture: darker symbols over the fill
                    props["pat"] = pat_map[cls]
                    props["pc"] = _darker(_rgb(fill), 0.5) + [160]   # semi-transparent: base fill stays visible
                ff.append({"type": "Feature", "geometry": _sg.mapping(gm), "properties": props})
            if outline:
                fdef["oc"] = _rgb(outline)                       # layer-wide outline (non-by_class layers)
            if pat_map:
                fdef["pat"] = True                               # has textures -> viewer adds a pattern overlay
        elif fk == "point":
            spec = points_cfg.get(fl.name, points_cfg.get("default", {"color": "#808080", "size": 3}))
            pc = _rgb(spec.get("color", "#808080")) + [225]
            fdef["sz"] = spec.get("size", 1)
            fdef["ic"] = spec.get("icon")
            fdef["mz"] = spec.get("min_zoom", 14)
            fdef["col"] = _rgb(spec.get("color", "#808080"))   # tints the SVG (mask)
            bearings = fl.gdf["bearing"] if "bearing" in fl.gdf else [None] * len(fl.gdf)
            for gm, br in zip(fl.gdf.geometry, bearings):
                if gm is None or gm.is_empty:
                    continue
                props = {"pc": pc}
                if br is not None and br == br:      # bearing present (not None/NaN) -> orient the icon
                    props["ang"] = round(float(br), 1)
                ff.append({"type": "Feature", "geometry": _sg.mapping(gm), "properties": props})
        else:
            spec = lines_cfg.get(fl.name, {})
            col, w, dash = _rgb(spec.get("color", "#888888")), spec.get("width", 1.4), spec.get("dash")
            for gm in fl.gdf.geometry:
                if gm is None or gm.is_empty:
                    continue
                ff.append({"type": "Feature", "geometry": _sg.mapping(gm),
                           "properties": {"c": col, "w": w, "dash": dash}})
        (out / "data" / f"feat_{fl.name}.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": ff}))
        feature_defs.append(fdef)
    feature_rows = "".join(
        f'<label><input type="checkbox" class="featchk" data-id="{d["id"]}" checked> {d["id"]}</label>'
        for d in feature_defs)

    # copy the SVG icon files referenced by any point layer into the render dir (served as data/icons/)
    icons_src = Path(__file__).parent / "icons"
    if any(d.get("ic") for d in feature_defs):
        import shutil
        (out / "data" / "icons").mkdir(parents=True, exist_ok=True)
        for d in feature_defs:
            svg = icons_src / (d.get("ic") or "")
            if d.get("ic") and svg.exists():
                shutil.copy(svg, out / "data" / "icons" / d["ic"])
    icfg = fcfg.get("icon", {})            # icon size-by-zoom curve (interpolated like roads.width)

    # landcover TEXTURE atlas (only if some polygon layer configured patterns) — served as data/pattern_atlas.png
    pat_atlas_url, pat_map_json = "", "{}"
    if any(d.get("pat") for d in feature_defs):
        from mapstyle.patterns import build_pattern_atlas
        png, pmap = build_pattern_atlas()
        (out / "data" / "pattern_atlas.png").write_bytes(png)
        pat_atlas_url, pat_map_json = "data/pattern_atlas.png", json.dumps(pmap)

    rstyle = _style["roads"]
    html = (_TEMPLATE
            .replace("__PATTERNATLAS__", pat_atlas_url)
            .replace("__PATTERNMAP__", pat_map_json)
            .replace("__FEATUREDEFS__", json.dumps(feature_defs))
            .replace("__FEATUREROWS__", feature_rows)
            .replace("__CASING__", json.dumps(rstyle["casing_ratio"]))
            .replace("__ZOOMBOOST__", json.dumps(wm.get("zoom_boost") or {"18": 1.0}))
            .replace("__LANEOVERLAP__", str(wm.get("lane_overlap", 1.15)))
            .replace("__ARROWMINZ__", str(astyle.get("min_zoom", 16)))
            .replace("__ARROWSPACING__", str(astyle.get("spacing_px", 150)))
            .replace("__ARROWSIZE__", str(astyle.get("size_px", 7)))
            .replace("__ARROWCOLOR__", str(astyle.get("color", "#8a8a8a")))
            .replace("__NAMEMIN__", str(nstyle.get("min_size", 10)))
            .replace("__NAMEMAX__", str(nstyle.get("max_size", 22)))
            .replace("__NAMEWK__", str(nstyle.get("width_ratio", 1.25)))
            .replace("__NAMEGLYPH__", str(nstyle.get("glyph", 0.64)))
            .replace("__NAMEREPEAT__", str(nstyle.get("repeat_px", 300)))
            # street-name label colour: default to the arrow colour (names read as the same subtle
            # grey as the oneway arrows), overridable via names.color.
            .replace("__NAMECOLOR__", str(_rgb(nstyle.get("color", astyle.get("color", "#8a8a8a")))))
            .replace("__NAMEHALO__", str(nstyle.get("halo", 0)))   # white text halo width (px); 0 = none
            .replace("__ARROWS__", "true" if "arrows" in overlays else "false")
            .replace("__NAMES__", "true" if "names" in overlays else "false")
            .replace("__ARROWSCHK__", "checked" if "arrows" in overlays else "")
            .replace("__NAMESCHK__", "checked" if "names" in overlays else "")
            .replace("__HASBOUND__", "true" if has_bound else "false")
            .replace("__BOUNDROW__", _BOUND_ROW if has_bound else "")
            .replace("__CENTER__", json.dumps(center))
            .replace("__ZOOM__", str(zoom))
            .replace("__ICONSIZE__", json.dumps(icfg.get("size", {14: 9, 16: 14})))
            .replace("__ICONHI__", str(icfg.get("hi_rate", 1.5)))
            .replace("__ICONOP__", str(icfg.get("opacity", 0.8)))
            .replace("__BASEMAPS__", json.dumps(BASEMAPS))
            .replace("__DEFAULT_BM__", default_bm)
            .replace("__LEGEND__", legend)
            .replace("__TITLE__", title))
    index = out / "index.html"
    index.write_text(html)
    write_serve(out_dir)          # python serve.py -> http://localhost:8080/index.html
    return str(index)


_TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8"/><title>__TITLE__</title>
<meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no"/>
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
<link href="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css" rel="stylesheet"/>
<script src="https://unpkg.com/deck.gl@9/dist.min.js"></script>
<style>
  body{margin:0} #map{position:absolute;inset:0}
  #panel{position:absolute;top:10px;left:10px;z-index:2;background:#fff;padding:10px 12px;
    border-radius:6px;font:13px/1.5 system-ui,sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.3);max-width:200px}
  #panel b{display:block;margin:6px 0 3px} #panel select{width:100%}
  #panel label{display:block;cursor:pointer;white-space:nowrap}
  #legend{font-size:12px;color:#444}
  #info{position:absolute;bottom:14px;left:10px;z-index:2;background:#fff;padding:8px 12px;
    border-radius:6px;font:13px/1.5 system-ui,sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.3);
    max-width:260px;display:none}
  #zoom{position:absolute;bottom:14px;right:10px;z-index:2;background:#fff;padding:5px 10px;
    border-radius:6px;font:13px/1.4 system-ui,sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.3)}
</style></head><body>
<div id="map"></div>
<div id="zoom">zoom —</div>
<div id="panel">
  <b style="font-size:15px;border-bottom:1px solid #ddd;padding-bottom:5px;margin:0 0 8px">Debug Visualization</b>
  <b>Base layer</b><select id="basemap"></select>
  <b>Color by</b>
  <label><input type="radio" name="cmode" value="osm" checked> OSM class</label>
  <label><input type="radio" name="cmode" value="modes"> mode combination</label>
  <b>Show modes</b>
  <label><input type="checkbox" id="md" checked> driving</label>
  <label><input type="checkbox" id="mw" checked> walking</label>
  <label><input type="checkbox" id="mc" checked> cycling</label>
  <b>Overlays</b>
  <label><input type="checkbox" id="arrows" __ARROWSCHK__> oneway arrows (z≥__ARROWMINZ__)</label>
  <label><input type="checkbox" id="names" __NAMESCHK__> street names (by class)</label>
  <b>Features</b>__FEATUREROWS__
  __BOUNDROW__
  <b>Legend (modes)</b><div id="legend">__LEGEND__</div>
</div>
<div id="info"></div>
<script>
const CENTER = __CENTER__, BASEMAPS = __BASEMAPS__, DEFAULT_BM = "__DEFAULT_BM__";
const S = {md:true, mw:true, mc:true, cmode:"osm", arrows:__ARROWS__, names:__NAMES__, boundary:__HASBOUND__};
let FEATURES = [], KEEP = [], LABELS = [], ARROWS = [], BOUNDARY = [];
const FEATUREDEFS = __FEATUREDEFS__, FEATDATA = {}, fstate = {}; FEATUREDEFS.forEach(d=>fstate[d.id]=true);
const ICONSIZE = __ICONSIZE__, ICONHI = __ICONHI__, ICONOP = __ICONOP__;   // icon px-size by zoom (interp like roads.width)
const PATTERN_ATLAS = "__PATTERNATLAS__", PATTERN_MAP = __PATTERNMAP__;    // landcover texture atlas (patterns.py) + name->box
function featureLayers(which){                             // "bg"=polygons/lines (under roads), "fg"=points/icons (on top)
  const out=[];
  for(const d of FEATUREDEFS){
    if(!fstate[d.id] || !FEATDATA[d.id]) continue;
    const isPt = d.kind==="point";
    if((which==="bg") === isPt) continue;                 // bg skips points; fg keeps only points
    if(d.kind==="polygon"){
      const vis = map.getZoom() >= (d.mz||0);
      // solid fill + per-feature OSM border (f.properties.oc); layer-wide d.oc for non-by-class layers
      out.push(new deck.GeoJsonLayer({id:"f_"+d.id, data:FEATDATA[d.id], visible:vis, stroked:true, filled:true,
        getFillColor:f=>f.properties.fc, getLineColor:f=>f.properties.oc || d.oc || [0,0,0,0],
        lineWidthUnits:"pixels", getLineWidth:0.8, lineWidthMinPixels:0.4}));
      // OSM texture overlay: darker symbols (f.properties.pc) masked by the atlas pattern, over the fill
      if(d.pat && deck.FillStyleExtension)
        out.push(new deck.GeoJsonLayer({id:"fp_"+d.id, data:FEATDATA[d.id], visible:vis, stroked:false, filled:true,
          getFillColor:f=>f.properties.pc || [0,0,0,0],
          extensions:[new deck.FillStyleExtension({pattern:true})],
          fillPatternAtlas:PATTERN_ATLAS, fillPatternMapping:PATTERN_MAP, fillPatternEnabled:true,
          getFillPattern:f=>f.properties.pat || "trees", getFillPatternScale:0.5, getFillPatternOffset:[0,0]}));
    }
    else if(d.kind==="point"){
      const vis = map.getZoom() >= (d.mz||14);    // categories appear only when zoomed in (declutter)
      if(d.ic)                                     // SVG icon (mask -> tinted by the config colour); px-size by zoom
        out.push(new deck.IconLayer({id:"f_"+d.id, data:FEATDATA[d.id], dataTransform:x=>x.features||[],
          visible:vis, opacity:ICONOP,
          getIcon:()=>({url:"data/icons/"+d.ic, width:48, height:48, mask:true}),
          getPosition:f=>f.geometry.coordinates, getColor:d.col,
          getAngle:f=>-(f.properties.ang||0),         // orient to the road (bearing); 0 for icons without one
          getSize:interp(ICONSIZE, map.getZoom(), ICONHI)*(d.sz||1), sizeUnits:"pixels"}));
      else                                         // plain coloured dot (also zoom-scaled)
        out.push(new deck.GeoJsonLayer({id:"f_"+d.id, data:FEATDATA[d.id], visible:vis, pointType:"circle",
          getFillColor:f=>f.properties.pc, pointRadiusUnits:"meters", getPointRadius:(d.sz||3)*4,
          pointRadiusMinPixels:2, pointRadiusMaxPixels:14, stroked:true, getLineColor:[255,255,255,180],
          lineWidthMinPixels:0.4}));
    } else
      out.push(new deck.GeoJsonLayer({id:"f_"+d.id, data:FEATDATA[d.id], stroked:true, filled:false,
        lineWidthUnits:"pixels", lineWidthMinPixels:0.5, getLineColor:f=>f.properties.c, getLineWidth:f=>f.properties.w||1.4,
        extensions:DASH, dashJustified:true, getDashArray:f=>f.properties.dash||[0,0]}));
  }
  return out;
}

const map = new maplibregl.Map({container:"map", style:BASEMAPS[DEFAULT_BM], center:CENTER, zoom:__ZOOM__, hash:true});
const overlay = new deck.MapboxOverlay({interleaved:false, layers:[]});
map.addControl(overlay); map.addControl(new maplibregl.NavigationControl());
const DASH = deck.PathStyleExtension ? [new deck.PathStyleExtension({dash:true})] : [];

// the exact openstreetmap-carto oneway.svg arrow (12x5, thin shaft + head), filled dark.
function makeArrow(){
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="20" viewBox="0 0 12 5">'
    + '<path d="M 0,2 7,2 7,0 12,2.5 7,5 7,3 0,3 z" fill="__ARROWCOLOR__"/></svg>';
  return "data:image/svg+xml;base64," + btoa(svg);
}
const ARROW_ICON = makeArrow();

// PHYSICAL width model (see docs/width-model.md): width_px = base_metres x (1/mpp) x zoom_boost(zoom).
// `bm` (base metres of a road/direction) is baked per feature = lanes x lane_m[class]; ONE global
// zoom_boost curve (legibility multiplier over true physical size, ->1 at high zoom) scales all
// classes together, so class widths stay in fixed ratio at every zoom. All numbers -> osm_carto.yaml.
const CASING_RATIO = __CASING__;
const ZOOM_BOOST = __ZOOMBOOST__;       // zoom -> legibility multiplier over physical (interp; ->1.0 high z)
const LANE_OVERLAP = __LANEOVERLAP__;   // two directions overlap this much at the centre (no seam, no gap)
function interp(t, z, hiRate){          // linear interp between zoom anchors; past the top grows by hiRate
  const k = Object.keys(t).map(Number).sort((a,b)=>a-b);
  if(z<=k[0]) return t[k[0]];
  const last=k[k.length-1];
  if(z>=last) return t[last]*Math.pow(hiRate, z-last);
  for(let i=0;i<k.length-1;i++) if(z<=k[i+1]){ const f=(z-k[i])/(k[i+1]-k[i]); return t[k[i]]+(t[k[i+1]]-t[k[i]])*f; }
  return t[last];
}
// metres-per-pixel at zoom z. MapLibre GL renders with 512px tiles, so its true scale is ONE zoom
// finer than the classic 256-tile Web-Mercator formula -> divide by 2^(z+1), not 2^z. Getting this
// wrong draws physical widths at HALF scale while the baked metre-offsets project at TRUE scale, so a
// gap opens between the two directions of every two-way road. See docs/width-model.md (offset calc).
function mppAt(z){ return 156543.03 * Math.cos(map.getCenter().lat*Math.PI/180) / Math.pow(2, z + 1); }
// physical width of a road (metres `bm`) in pixels at zoom z; `isLane` (a two-way direction) adds the
// slight centre overlap. zoom_boost stays flat (hiRate 1) above its top anchor = true physical scale.
function widthPx(bm, z, isLane){ return (bm||0) / mppAt(z) * interp(ZOOM_BOOST, z, 1.0) * (isLane ? LANE_OVERLAP : 1); }
const LINK_W = 0.6;   // ramps (*_link) drawn narrower than the through road, like OSM
function fillW(f){
  let w = widthPx(f.properties.bm, map.getZoom(), f.properties.ln);
  if(f.properties.lk) w *= LINK_W;   // ramps narrower
  return w;
}
// casing as a ratio of fill (so the outline scales with the road, incl. overzoom)
function casW(f){ return f.properties.cc ? fillW(f) * (CASING_RATIO[f.properties.g]||1.3) : 0; }

function modesStr(p){ return [p.md&&"driving",p.mw&&"walking",p.mc&&"cycling"].filter(Boolean).join(", "); }
function showInfo(o){
  const i = document.getElementById("info");
  if(!o){ i.style.display="none"; return; }
  const p = o.properties;
  i.style.display = "block";
  i.innerHTML = `<b>${p.nm||"(unnamed)"}</b><br>class: ${p.hw}<br>length: ${p.len==null?"?":p.len+" m"}`
    + `<br>width: ${p.bm==null?"?":p.bm+" m/dir"} (class-fixed)${p.ow?" · one-way":""}`
    + `<br><span style="color:#888;font-size:11px">OSM lanes: ${p.lanes==null?"untagged":p.lanes+" total"} (not used)</span>`
    + `<br>modes: ${modesStr(p)||"—"}<br><span style="color:#888;font-size:11px">edge_id ${p.eid}</span>`;
}

// elevation band: tunnels/below = -1, ground = 0, bridges/above = +1. deck draws LAYERS in
// array order, so each band is its own casing+fill pair and bridges stack as a unit on top.
function band(f){
  const p = f.properties;
  if(p.br || p.lv > 0) return 1;
  if(p.tn || p.lv < 0) return -1;
  return 0;
}
function draw(){
  const col = S.cmode==="modes" ? (f=>f.properties.cb) : (f=>f.properties.c);
  const zt = Math.round(map.getZoom()*5)/5;     // re-evaluate widths per 0.2 zoom step
  const layers = [];
  layers.push(...featureLayers("bg"));          // area/line feature layers first (drawn underneath the roads)
  for(const b of [-1, 0, 1]){
    const fc = {type:"FeatureCollection", features:KEEP.filter(f=>band(f)===b && map.getZoom() >= (f.properties.mz||0))};
    if(!fc.features.length) continue;
    // grade-specific styling (deck has no line-offset/sort-key; we vary the accessors per band):
    //  tunnels (b<0): dashed casing + faded fill -> reads as "underground"; bridges (b>0): heavier deck casing.
    const isTun = b === -1, isBr = b === 1;
    const casWidth = isBr ? (f=>casW(f)*1.25) : casW;
    const casDash  = isTun ? (f=>[5,4]) : (f=>[0,0]);
    const fillColor = isTun ? (f=>{const c=col(f); return [c[0],c[1],c[2],145];}) : col;
    layers.push(
      new deck.GeoJsonLayer({id:"cas"+b, data:fc, stroked:true, filled:false, lineWidthUnits:"pixels",
        lineWidthMinPixels:0.5, visible:S.cmode==="osm",
        getLineColor:f=>f.properties.cc||[0,0,0,0], getLineWidth:casWidth,
        extensions:DASH, dashJustified:true, getDashArray:casDash,
        updateTriggers:{getLineWidth:[zt,b], getDashArray:[b]}}),
      new deck.GeoJsonLayer({id:"fill"+b, data:fc, stroked:true, filled:false, pickable:true,
        autoHighlight:true, highlightColor:[255,238,0,210], lineWidthUnits:"pixels", lineWidthMinPixels:0.6,
        getLineColor:fillColor, getLineWidth:fillW,
        extensions:DASH, dashJustified:true, getDashArray:f=>(S.cmode==="osm"&&f.properties.dash)||[0,0],
        onClick:info=>showInfo(info.object),
        updateTriggers:{getLineColor:[S.cmode,b], getLineWidth:[zt], getDashArray:[S.cmode]}}),
    );
  }
  const z = map.getZoom();
  const cosC = Math.cos(map.getCenter().lat*Math.PI/180);
  const mpp = 156543.03 * cosC / Math.pow(2, z);        // metres per pixel — shared by arrows + names
  const MINF = __NAMEMIN__, MAXF = __NAMEMAX__, GLYPH = __NAMEGLYPH__, WK = __NAMEWK__;  // from names.* (YAML)
  // a name must fit the road in BOTH directions: along its straight run (length) AND across its
  // painted width (so the text sits INSIDE the road, not towering over a hairline). The font is the
  // smaller of the two fits; 0 => doesn't fit yet at this zoom -> hidden.
  const fontFor = f => {
    const lenFont = 0.9 * (f.properties.len / mpp) / (f.properties.nm.length * GLYPH);   // along length
    const wpx = widthPx(f.properties.bm, z, false);   // painted road width (bm = both directions if two-way)
    const fs = Math.min(lenFont, wpx * WK);                                               // across width
    return fs >= MINF ? Math.min(fs, MAXF) : 0;
  };
  const boxOf = (f, fs) => {                            // a label's oriented box (its own font size)
    const c = f.geometry.coordinates, a = f.properties.na * Math.PI/180;
    return {x: c[0]*111320*cosC, y: c[1]*111320, ax: Math.cos(a), ay: Math.sin(a),
            hl: (f.properties.nm.length*fs*GLYPH/2 + fs*0.5)*mpp, hw: fs*0.8*mpp, nm: f.properties.nm};
  };

  // names: size each candidate to fill its road, keep those that reach MINF, then greedily place —
  // important roads first, repeating a name along long roads (>= CELL apart), never overlapping a
  // label. Computed FIRST so arrows can avoid the placed ones.
  let nameFit = [], nameZones = [];
  if(S.names){
    const cand = [];
    for(const f of LABELS){ const fs = fontFor(f); if(fs){ f.__fs = fs; cand.push(f); } }
    cand.sort((a,b) => (b.properties.pr - a.properties.pr) || (b.properties.len - a.properties.len));
    const CELL = __NAMEREPEAT__*mpp, REP2 = CELL*CELL; // grid cell == same-name repeat distance (px)
    const grid = new Map();
    for(const f of cand){
      const b = boxOf(f, f.__fs), gx = Math.round(b.x/CELL), gy = Math.round(b.y/CELL);
      let ok = true;
      for(let ix=gx-1; ix<=gx+1 && ok; ix++) for(let iy=gy-1; iy<=gy+1 && ok; iy++){
        const bucket = grid.get(ix+","+iy); if(!bucket) continue;
        for(const p of bucket){
          const dx = b.x-p.x, dy = b.y-p.y;
          if(p.nm===b.nm && dx*dx+dy*dy < REP2){ ok=false; break; }                         // repeat gap
          if(Math.abs(dx*b.ax+dy*b.ay) < b.hl+p.hl && Math.abs(-dx*b.ay+dy*b.ax) < b.hw+p.hw){ ok=false; break; } // overlap
        }
      }
      if(ok){ nameFit.push(f); nameZones.push(b);
        const kk = gx+","+gy; let bk = grid.get(kk); if(!bk){ bk=[]; grid.set(kk,bk); } bk.push(b); }
    }
  }

  if(S.arrows && z >= __ARROWMINZ__){   // oneway arrows: must fit the road WIDTH (hidden/scaled on thin
    const tM = __ARROWSPACING__ * mpp;                   // roads), grid-deduped to ~spacing_px, off names
    const AMIN = Math.min(3.5, __ARROWSIZE__);           // hide arrows where the road is thinner than this (px)
    const awid = f => widthPx(f.properties.bm, z, false);   // physical width of the (one-way) road
    const seen = new Set();                              // keep one arrow per tM grid cell (global)
    let data = ARROWS.filter(f => {
      if(awid(f) < AMIN) return false;                   // road too thin to carry an arrow at this zoom
      const c = f.geometry.coordinates;
      const k = Math.round(c[0]*111320*cosC/tM) + "," + Math.round(c[1]*111320/tM);
      if(seen.has(k)) return false; seen.add(k); return true;
    });
    if(nameZones.length){                                // drop arrows sitting inside a name box
      data = data.filter(f => {
        const c = f.geometry.coordinates, px = c[0]*111320*cosC, py = c[1]*111320;
        for(const n of nameZones){
          const dx = px - n.x, dy = py - n.y;
          if(Math.abs(dx*n.ax + dy*n.ay) < n.hl && Math.abs(-dx*n.ay + dy*n.ax) < n.hw) return false;
        }
        return true;
      });
    }
    layers.push(new deck.IconLayer({id:"arrows", data,
      getIcon: () => ({url: ARROW_ICON, width: 48, height: 20, anchorX: 24, anchorY: 10}),
      getPosition: f => f.geometry.coordinates, getAngle: f => f.properties.ang,
      sizeUnits:"pixels", getSize: f => Math.min(awid(f), __ARROWSIZE__), billboard:true,
      updateTriggers:{getSize:[zt]}}));
  }
  if(nameFit.length){           // road-name labels (white halo), each sized to fill its road
    layers.push(new deck.TextLayer({id:"names", data: nameFit, characterSet:"auto",
      getPosition: f => f.geometry.coordinates, getText: f => f.properties.nm, getAngle: f => f.properties.na,
      sizeUnits:"pixels", getSize: f => f.__fs, getColor:__NAMECOLOR__, billboard:true,
      fontSettings:{sdf:true}, outlineWidth: __NAMEHALO__, outlineColor:[255,255,255],
      getTextAnchor:"middle", getAlignmentBaseline:"center",
      updateTriggers:{getSize:[zt]}}));
  }
  if(S.boundary && BOUNDARY.length){   // clip/area boundary, purple dashed outline, on top (duckOSM look)
    layers.push(new deck.GeoJsonLayer({id:"boundary", data:{type:"FeatureCollection", features:BOUNDARY},
      stroked:true, filled:false, lineWidthUnits:"pixels", getLineWidth:2.5, lineWidthMinPixels:2.5,
      getLineColor:[106,13,173,235], extensions:DASH, dashJustified:true, getDashArray:[6,4]}));
  }
  layers.push(...featureLayers("fg"));          // point/icon feature layers LAST — always on top
  overlay.setProps({layers});
}
function refilter(){
  KEEP = FEATURES.filter(f => (f.properties.md&&S.md)||(f.properties.mw&&S.mw)||(f.properties.mc&&S.mc));
  draw();
}

const sel = document.getElementById("basemap");
Object.keys(BASEMAPS).forEach(k=>{const o=document.createElement("option");o.value=k;o.text=k;if(k===DEFAULT_BM)o.selected=true;sel.appendChild(o);});
sel.onchange = e => { map.setStyle(BASEMAPS[e.target.value]); map.once("idle", draw); };
["md","mw","mc"].forEach(id => document.getElementById(id).onchange = e => { S[id]=e.target.checked; refilter(); });
document.querySelectorAll('input[name=cmode]').forEach(r => r.onchange = e => { S.cmode=e.target.value; draw(); });
["arrows","names","boundary"].forEach(id => { const el=document.getElementById(id); if(el) el.onchange = e => { S[id]=e.target.checked; draw(); }; });
document.querySelectorAll('.featchk').forEach(cb => cb.onchange = e => { fstate[e.target.dataset.id]=e.target.checked; draw(); });
const zoomBox = document.getElementById("zoom");
function showZoom(){ zoomBox.textContent = "zoom " + map.getZoom().toFixed(2); }
map.on("move", showZoom); map.on("load", showZoom);
let raf=null; map.on("zoom", ()=>{ if(raf) return; raf=requestAnimationFrame(()=>{raf=null; draw();}); });

Promise.all([
  fetch("data/roads_merged.geojson").then(r=>r.json()),
  fetch("data/labels.geojson").then(r=>r.json()),
  fetch("data/arrows.geojson").then(r=>r.json()),
  fetch("data/boundary.geojson").then(r=>r.ok?r.json():{features:[]}).catch(()=>({features:[]})),
  ...FEATUREDEFS.map(d=>fetch("data/feat_"+d.id+".geojson").then(r=>r.json()).then(j=>{FEATDATA[d.id]=j; return 0;}))
]).then((res) => {
  const [roads, labels, arrows, boundary] = res;
  FEATURES = roads.features; LABELS = labels.features; ARROWS = arrows.features; BOUNDARY = boundary.features||[];
  const go=()=>refilter(); if(map.loaded()) go(); else map.on("load", go);
});
</script></body></html>"""
