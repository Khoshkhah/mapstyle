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


def merge_modes(db, modes=("driving", "walking", "cycling")):
    """Return one Layer of distinct edges (by edge_id) with driving/walking/cycling flags."""
    import duckdb
    import geopandas as gpd
    import shapely.wkt as wkt

    con = duckdb.connect(db, read_only=True)
    con.execute("INSTALL spatial; LOAD spatial;")
    union = " UNION ALL ".join(
        f"SELECT edge_id, class, geom, name, length_m, layer, bridge, tunnel, service, oneway, '{m}' AS mode "
        f"FROM basemap.roads_{m}" for m in modes)
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
               bool_or(mode = 'driving')    AS d,
               bool_or(mode = 'walking')    AS w,
               bool_or(mode = 'cycling')    AS c
        FROM ({union})
        GROUP BY edge_id
    """).fetchall()
    con.close()

    rec = {"edge_id": [], "highway": [], "name": [], "length_m": [],
           "layer": [], "bridge": [], "tunnel": [], "service": [], "oneway": [],
           "driving": [], "walking": [], "cycling": [], "combo": []}
    geoms = []
    for eid, cls, geom_wkt, nm, length_m, lyr, brg, tun, svc, ow, is_d, is_w, is_c in rows:
        combo = "".join(k for k, v in (("d", is_d), ("w", is_w), ("c", is_c)) if v)
        rec["edge_id"].append(eid); rec["highway"].append(cls)
        rec["name"].append(nm); rec["length_m"].append(length_m)
        rec["layer"].append(lyr); rec["bridge"].append(brg); rec["tunnel"].append(tun)
        rec["service"].append(svc); rec["oneway"].append(bool(ow))
        rec["driving"].append(bool(is_d)); rec["walking"].append(bool(is_w)); rec["cycling"].append(bool(is_c))
        rec["combo"].append(combo)
        geoms.append(wkt.loads(geom_wkt))
    gdf = gpd.GeoDataFrame(rec, geometry=geoms, crs="EPSG:4326")
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


def render_merge(layer, out_dir, basemap="osm", title="mapstyle — merged modes", overlays=(),
                 boundary=None):
    """Write a viewer for the merged set: OSM/Modes coloring + per-mode filter + base selector.

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

    out = Path(out_dir); (out / "data").mkdir(parents=True, exist_ok=True)
    feats = []
    gdf = layer.gdf
    _SVC_MINOR = ("driveway", "parking_aisle", "drive-through", "drive_through")
    label_feats = []   # name-label candidates: one per named piece (the viewer fits + places them)
    arrow_feats = []   # oneway arrow markers, sampled along the lines (OSM-style)
    for geom, eid, hw, nm, length_m, lyr, brg, tun, svc, ow, combo, d, w, c in zip(
            gdf.geometry, gdf.edge_id, gdf.highway, gdf.name, gdf.length_m,
            gdf.layer, gdf.bridge, gdf.tunnel, gdf.service, gdf.oneway, gdf.combo,
            gdf.driving, gdf.walking, gdf.cycling):
        if geom is None or geom.is_empty:
            continue
        s = resolve_road(hw)
        layer = _layer_int(lyr)
        is_bridge = bool(brg) and str(brg).strip().lower() not in ("", "no")
        is_tunnel = bool(tun) and str(tun).strip().lower() not in ("", "no")
        casing = "#34343a" if is_bridge else s.casing   # bridges get a dark casing (OSM)
        g = road_group(hw)
        if g == "service" and str(svc).strip().lower() in _SVC_MINOR:
            g = "service_minor"                          # driveways/parking aisles -> narrower
        if nm and g in NAME_GROUPS:                       # name-label candidates ALONG the piece
            pr = road_z(hw)
            for pos, na, fit_m in _label_candidates(geom, n_sample):
                if fit_m >= 20:                           # skip points without room for any name
                    label_feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": pos},
                        "properties": {"nm": nm, "na": na, "len": round(fit_m), "pr": pr, "g": g}})
        if ow:                                            # oneway -> arrows along the line
            for pos, ang, seq in _arrow_points(geom, a_sample):
                arrow_feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": pos},
                                    "properties": {"ang": ang, "seq": seq, "g": g}})
        feats.append({"type": "Feature", "geometry": sg.mapping(geom), "properties": {
            "c": _rgb(s.fill),
            "cc": _rgb(casing) if casing else None,
            "dash": list(s.dash) if s.dash else None,
            "cb": _rgb(COMBO_COLOR.get(combo, "#999999")),
            "md": bool(d), "mw": bool(w), "mc": bool(c),
            "eid": str(eid), "hw": hw, "nm": nm,
            "len": round(length_m) if length_m else None,
            # draw order: class rank + 10*layer (bridges up, tunnels down) — osm2pgsql z_order
            "z": road_z(hw) + 10 * layer, "g": g,
            "lk": bool(hw) and str(hw).strip().lower().endswith("_link"),
            "br": is_bridge, "tn": is_tunnel, "lv": layer, "ow": bool(ow),
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
    center = [(minx + maxx) / 2, (miny + maxy) / 2]
    default_bm = _BM_ALIAS.get(basemap, basemap if basemap in BASEMAPS else "OSM Standard")
    legend = "".join(
        f'<span style="color:{COMBO_COLOR[k]}">&#9632;</span> {v}<br>' for k, v in
        [("dwc", "all 3"), ("dc", "drive+cycle"), ("dw", "drive+walk"),
         ("wc", "walk+cycle"), ("d", "drive only"), ("c", "cycle only"), ("w", "walk only")])
    rstyle = _style["roads"]
    html = (_TEMPLATE
            .replace("__WIDTH__", json.dumps(rstyle["width"]))
            .replace("__HIRATE__", json.dumps(rstyle["hi_rate"]))
            .replace("__CASING__", json.dumps(rstyle["casing_ratio"]))
            .replace("__ARROWMINZ__", str(astyle.get("min_zoom", 16)))
            .replace("__ARROWSPACING__", str(astyle.get("spacing_px", 150)))
            .replace("__ARROWSIZE__", str(astyle.get("size_px", 7)))
            .replace("__ARROWCOLOR__", str(astyle.get("color", "#8a8a8a")))
            .replace("__NAMEMIN__", str(nstyle.get("min_size", 10)))
            .replace("__NAMEMAX__", str(nstyle.get("max_size", 22)))
            .replace("__NAMEWK__", str(nstyle.get("width_ratio", 1.25)))
            .replace("__NAMEGLYPH__", str(nstyle.get("glyph", 0.64)))
            .replace("__NAMEREPEAT__", str(nstyle.get("repeat_px", 300)))
            .replace("__ARROWS__", "true" if "arrows" in overlays else "false")
            .replace("__NAMES__", "true" if "names" in overlays else "false")
            .replace("__ARROWSCHK__", "checked" if "arrows" in overlays else "")
            .replace("__NAMESCHK__", "checked" if "names" in overlays else "")
            .replace("__HASBOUND__", "true" if has_bound else "false")
            .replace("__BOUNDROW__", _BOUND_ROW if has_bound else "")
            .replace("__CENTER__", json.dumps(center))
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
  __BOUNDROW__
  <b>Legend (modes)</b><div id="legend">__LEGEND__</div>
</div>
<div id="info"></div>
<script>
const CENTER = __CENTER__, BASEMAPS = __BASEMAPS__, DEFAULT_BM = "__DEFAULT_BM__";
const S = {md:true, mw:true, mc:true, cmode:"osm", arrows:__ARROWS__, names:__NAMES__, boundary:__HASBOUND__};
let FEATURES = [], KEEP = [], LABELS = [], ARROWS = [], BOUNDARY = [];

const map = new maplibregl.Map({container:"map", style:BASEMAPS[DEFAULT_BM], center:CENTER, zoom:13});
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

// openstreetmap-carto fill widths (px) by zoom, per class group; casing = fill + add.
// road widths/growth/casing come from styles/osm_carto.yaml (injected below)
const FILL = __WIDTH__;
const HI_RATE = __HIRATE__;
const CASING_RATIO = __CASING__;
// Smooth openstreetmap-carto VECTOR widths: linear interpolation between the per-zoom anchors,
// so roads only ever widen as you zoom in (no raster "sawtooth"). This is how a vector OSM
// style renders. It won't pixel-match the RASTER basemap between integer zooms (the raster
// scales pre-rendered tiles), so evaluate on the "None" base (or a vector base like Positron).
function interp(t, z, hiRate){
  const k = Object.keys(t).map(Number).sort((a,b)=>a-b);
  if(z<=k[0]) return t[k[0]];
  const last=k[k.length-1];
  if(z>=last) return t[last]*Math.pow(hiRate, z-last);   // keep widening past the table top
  for(let i=0;i<k.length-1;i++) if(z<=k[i+1]){ const f=(z-k[i])/(k[i+1]-k[i]); return t[k[i]]+(t[k[i+1]]-t[k[i]])*f; }
  return t[last];
}
const LINK_W = 0.6;   // ramps (*_link) drawn narrower than the through road, like OSM
function fillW(f){
  const g = f.properties.g;
  const w = interp(FILL[g]||FILL.residential, map.getZoom(), HI_RATE[g]||1.55);
  return f.properties.lk ? w*LINK_W : w;
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
  for(const b of [-1, 0, 1]){
    const fc = {type:"FeatureCollection", features:KEEP.filter(f=>band(f)===b)};
    if(!fc.features.length) continue;
    layers.push(
      new deck.GeoJsonLayer({id:"cas"+b, data:fc, stroked:true, filled:false, lineWidthUnits:"pixels",
        lineWidthMinPixels:0.5, visible:S.cmode==="osm",
        getLineColor:f=>f.properties.cc||[0,0,0,0], getLineWidth:casW,
        updateTriggers:{getLineWidth:[zt]}}),
      new deck.GeoJsonLayer({id:"fill"+b, data:fc, stroked:true, filled:false, pickable:true,
        autoHighlight:true, highlightColor:[255,238,0,210], lineWidthUnits:"pixels", lineWidthMinPixels:0.6,
        getLineColor:col, getLineWidth:fillW,
        extensions:DASH, dashJustified:true, getDashArray:f=>(S.cmode==="osm"&&f.properties.dash)||[0,0],
        onClick:info=>showInfo(info.object),
        updateTriggers:{getLineColor:[S.cmode], getLineWidth:[zt], getDashArray:[S.cmode]}}),
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
    const wpx = interp(FILL[f.properties.g]||FILL.residential, z, HI_RATE[f.properties.g]||1.55);
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
    const awid = f => interp(FILL[f.properties.g]||FILL.service, z, HI_RATE[f.properties.g]||1.55);
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
      sizeUnits:"pixels", getSize: f => f.__fs, getColor:[30,30,30], billboard:true,
      fontSettings:{sdf:true}, outlineWidth: 3, outlineColor:[255,255,255],
      getTextAnchor:"middle", getAlignmentBaseline:"center",
      updateTriggers:{getSize:[zt]}}));
  }
  if(S.boundary && BOUNDARY.length){   // clip/area boundary, purple dashed outline, on top (duckOSM look)
    layers.push(new deck.GeoJsonLayer({id:"boundary", data:{type:"FeatureCollection", features:BOUNDARY},
      stroked:true, filled:false, lineWidthUnits:"pixels", getLineWidth:2.5, lineWidthMinPixels:2.5,
      getLineColor:[106,13,173,235], extensions:DASH, dashJustified:true, getDashArray:[6,4]}));
  }
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
const zoomBox = document.getElementById("zoom");
function showZoom(){ zoomBox.textContent = "zoom " + map.getZoom().toFixed(2); }
map.on("move", showZoom); map.on("load", showZoom);
let raf=null; map.on("zoom", ()=>{ if(raf) return; raf=requestAnimationFrame(()=>{raf=null; draw();}); });

Promise.all([
  fetch("data/roads_merged.geojson").then(r=>r.json()),
  fetch("data/labels.geojson").then(r=>r.json()),
  fetch("data/arrows.geojson").then(r=>r.json()),
  fetch("data/boundary.geojson").then(r=>r.ok?r.json():{features:[]}).catch(()=>({features:[]}))
]).then(([roads, labels, arrows, boundary]) => {
  FEATURES = roads.features; LABELS = labels.features; ARROWS = arrows.features; BOUNDARY = boundary.features||[];
  const go=()=>refilter(); if(map.loaded()) go(); else map.on("load", go);
});
</script></body></html>"""
