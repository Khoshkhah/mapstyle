"""render_web_features — the full base map as toggleable layers, with per-zoom road widths,
street-name labels and oneway arrows.

Combines the mapstyle renderers' strengths in one viewer:
  * like ``render_web``  — every layer (polygons / lines / points) is a separate, toggleable layer,
  * like ``render_merge`` — roads take their **per-zoom widths + casing** from
    ``styles/osm_carto.yaml`` (``roads.width`` / ``hi_rate`` / ``casing_ratio``), plus optional
    **street-name labels** (zoom >= names_min) and **oneway arrows** (zoom >= arrows_min).

Leaves ``render_web`` / ``render_merge`` untouched. Road layers (``roads`` from duckmap, ``streets``
from duckOSM) get per-zoom widths; a named road also gets a midpoint label; a road whose gdf has a
truthy ``oneway`` column gets direction arrows sampled along it. Other lines (e.g. ``waterways``) get
a plain fixed width + colour; polygons/points as in ``render_web``.

    from mapstyle import load_layer
    from mapstyle.render_web_features import render_web_features, write_serve
    layers = [load_layer(DB, t, k) for t, k in
              [("landcover","polygon"),("water","polygon"),("buildings","polygon"),("roads","line")]]
    render_web_features(layers, "render/tartu", names=True, arrows=True)
"""

import json
import math
from pathlib import Path

from mapstyle.palettes import polygon_style
from mapstyle.roads import resolve_road, road_group
from mapstyle.render_web import BASEMAPS, _BM_ALIAS, _rgb, write_serve  # reuse stable helpers
from mapstyle.style import load_style

# Line layers that are roads (per-zoom width + names/arrows). duckmap: 'roads'; duckOSM: 'streets'.
ROAD_LAYERS = {"roads", "streets"}
# road groups that get name labels (skip service/driveways/paths)
NAME_GROUPS = {"major", "primary", "secondary", "tertiary", "residential", "living_street", "pedestrian"}
_POINT_COLOR = {"public_transport": [30, 110, 180, 230], "pois": [200, 120, 40, 220],
                "place_labels": [60, 60, 60, 235], "places": [60, 60, 60, 235]}


def _pt_angle(geom, frac):
    """Point at `frac` along `geom` + the local bearing in deck CCW degrees (Mercator-corrected)."""
    p = geom.interpolate(frac, normalized=True)
    a = geom.interpolate(max(frac - 0.03, 0.0), normalized=True)
    b = geom.interpolate(min(frac + 0.03, 1.0), normalized=True)
    coslat = math.cos(math.radians(p.y)) or 1e-6
    ang = math.degrees(math.atan2((b.y - a.y) / coslat, b.x - a.x))
    return [round(p.x, 6), round(p.y, 6)], ang


def _bake_polygon(layer):
    import shapely.geometry as sg
    feats = []
    for geom, cls in zip(layer.gdf.geometry, layer.gdf["class"]):
        if geom is None or geom.is_empty:
            continue
        st = polygon_style(layer.name, cls)
        feats.append({"type": "Feature", "geometry": sg.mapping(geom),
                      "properties": {"fc": _rgb(st["fillColor"]) + [int(st["fillOpacity"] * 255)]}})
    return {"type": "FeatureCollection", "features": feats}


def _bake_point(layer):
    import shapely.geometry as sg
    col = _POINT_COLOR.get(layer.name, [90, 90, 90, 220])
    feats = []
    for geom in layer.gdf.geometry:
        if geom is None or geom.is_empty:
            continue
        feats.append({"type": "Feature", "geometry": sg.mapping(geom), "properties": {"pc": col}})
    return {"type": "FeatureCollection", "features": feats}


def _bake_road(layer):
    """Road geometry with width-group `g`, link flag `lk`, colour/casing/dash for per-zoom widths."""
    import shapely.geometry as sg
    feats = []
    for geom, hw in zip(layer.gdf.geometry, layer.gdf["highway"].fillna("residential")):
        if geom is None or geom.is_empty:
            continue
        s = resolve_road(hw)
        h = str(hw).strip().lower()
        feats.append({"type": "Feature", "geometry": sg.mapping(geom),
                      "properties": {"g": road_group(hw), "lk": h.endswith("_link"),
                                     "c": _rgb(s.fill), "cc": _rgb(s.casing) if s.casing else None,
                                     "dash": list(s.dash) if s.dash else None}})
    return {"type": "FeatureCollection", "features": feats}


def _bake_road_labels(layer):
    """One upright name label at each named road's midpoint (viewer shows them at zoom >= names_min)."""
    gdf = layer.gdf
    names = gdf["name"] if "name" in gdf else [None] * len(gdf)
    feats = []
    for geom, hw, nm in zip(gdf.geometry, gdf["highway"].fillna(""), names):
        if geom is None or geom.is_empty or not nm or road_group(hw) not in NAME_GROUPS:
            continue
        pos, ang = _pt_angle(geom, 0.5)
        while ang > 90:
            ang -= 180
        while ang <= -90:
            ang += 180
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": pos},
                      "properties": {"nm": nm, "na": round(ang, 1)}})
    return {"type": "FeatureCollection", "features": feats}


def _bake_road_arrows(layer, stride_m=130):
    """Direction arrows sampled along each oneway road (needs a truthy `oneway` gdf column)."""
    gdf = layer.gdf
    if "oneway" not in gdf:
        return {"type": "FeatureCollection", "features": []}
    feats = []
    for geom, ow in zip(gdf.geometry, gdf["oneway"]):
        if geom is None or geom.is_empty or not ow:
            continue
        n = max(1, int(geom.length * 111320 / stride_m))
        for i in range(n):
            pos, ang = _pt_angle(geom, (i + 0.5) / n)
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": pos},
                          "properties": {"ang": round(ang, 1)}})
    return {"type": "FeatureCollection", "features": feats}


def _bake_line(layer):
    """Non-road line (e.g. waterways): fixed width + colour (Layer.color override)."""
    import shapely.geometry as sg
    col = _rgb(layer.color) if layer.color else [120, 120, 120]
    feats = []
    for geom in layer.gdf.geometry:
        if geom is None or geom.is_empty:
            continue
        feats.append({"type": "Feature", "geometry": sg.mapping(geom),
                      "properties": {"c": col, "w": 1.4}})
    return {"type": "FeatureCollection", "features": feats}


def render_web_features(layers, out_dir, basemap="none", title="mapstyle — features",
                        style="osm_carto", names=True, arrows=True):
    out = Path(out_dir)
    (out / "data").mkdir(parents=True, exist_ok=True)
    rstyle = load_style(style).get("roads", {})

    defs, road_ids, xs, ys = [], [], [], []
    for layer in sorted(layers, key=lambda x: x.z):
        if layer.kind == "polygon":
            fc, kind = _bake_polygon(layer), "polygon"
        elif layer.kind == "point":
            fc, kind = _bake_point(layer), "point"
        elif layer.name in ROAD_LAYERS:
            fc, kind = _bake_road(layer), "road"
            (out / "data" / f"{layer.name}_labels.geojson").write_text(json.dumps(_bake_road_labels(layer)))
            (out / "data" / f"{layer.name}_arrows.geojson").write_text(json.dumps(_bake_road_arrows(layer)))
            road_ids.append(layer.name)
        else:
            fc, kind = _bake_line(layer), "line"
        (out / "data" / f"{layer.name}.geojson").write_text(json.dumps(fc))
        defs.append({"id": layer.name, "kind": kind})
        if not layer.gdf.empty:
            rp = layer.gdf.geometry.representative_point()
            xs.extend(rp.x.tolist()); ys.extend(rp.y.tolist())

    def _pct(vals, p):
        s = sorted(vals)
        return s[min(len(s) - 1, max(0, int(p * (len(s) - 1))))]
    bounds = ([[_pct(xs, 0.01), _pct(ys, 0.01)], [_pct(xs, 0.99), _pct(ys, 0.99)]]
              if xs else [[-0.1, -0.1], [0.1, 0.1]])

    default_bm = _BM_ALIAS.get(basemap, basemap if basemap in BASEMAPS else "None")
    nstyle = load_style(style).get("names", {})
    astyle = load_style(style).get("arrows", {})
    html = (_TEMPLATE
            .replace("__DEFS__", json.dumps(defs))
            .replace("__ROADIDS__", json.dumps(road_ids))
            .replace("__BOUNDS__", json.dumps(bounds))
            .replace("__BASEMAPS__", json.dumps(BASEMAPS))
            .replace("__DEFAULT_BM__", default_bm)
            .replace("__TITLE__", title)
            .replace("__WIDTH__", json.dumps(rstyle.get("width", {})))
            .replace("__HIRATE__", json.dumps(rstyle.get("hi_rate", {})))
            .replace("__CASING__", json.dumps(rstyle.get("casing_ratio", {})))
            .replace("__NAMESMINZ__", str(nstyle.get("min_zoom", 14)))
            .replace("__ARROWSMINZ__", str(astyle.get("min_zoom", 16)))
            .replace("__NAMES__", "true" if names else "false")
            .replace("__ARROWS__", "true" if arrows else "false")
            .replace("__NAMESCHK__", "checked" if names else "")
            .replace("__ARROWSCHK__", "checked" if arrows else ""))
    (out / "index.html").write_text(html)
    return str(out / "index.html")


_TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8"/><title>__TITLE__</title>
<meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no"/>
<script src="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.js"></script>
<link href="https://unpkg.com/maplibre-gl@4/dist/maplibre-gl.css" rel="stylesheet"/>
<script src="https://unpkg.com/deck.gl@9/dist.min.js"></script>
<style>
  body{margin:0} #map{position:absolute;inset:0}
  #panel{position:absolute;top:10px;left:10px;z-index:2;background:#fff;padding:10px 12px;
    border-radius:6px;font:13px/1.5 system-ui,sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.3)}
  #panel b{display:block;margin-bottom:4px;margin-top:6px}
  #panel select{width:100%;margin-bottom:4px}
  #panel label{display:block;cursor:pointer;white-space:nowrap}
  #zoom{position:absolute;bottom:12px;right:10px;z-index:2;background:#fff;padding:4px 9px;
    border-radius:5px;font:12px system-ui;box-shadow:0 1px 4px rgba(0,0,0,.3)}
</style></head><body>
<div id="map"></div>
<div id="panel"><b>Base layer</b><select id="basemap"></select><b>Overlays</b>
  <label><input type="checkbox" id="names_cb" __NAMESCHK__> street names (z>=__NAMESMINZ__)</label>
  <label><input type="checkbox" id="arrows_cb" __ARROWSCHK__> oneway arrows (z>=__ARROWSMINZ__)</label>
  <b>Layers</b></div>
<div id="zoom">zoom -</div>
<script>
const DEFS = __DEFS__, ROADIDS = __ROADIDS__, BOUNDS = __BOUNDS__, BASEMAPS = __BASEMAPS__, DEFAULT_BM = "__DEFAULT_BM__";
const FILL = __WIDTH__, HI_RATE = __HIRATE__, CASING = __CASING__;
const NAMESMINZ = __NAMESMINZ__, ARROWSMINZ = __ARROWSMINZ__;
const S = {names: __NAMES__, arrows: __ARROWS__};
const state = {}; DEFS.forEach(d => state[d.id] = true);

const map = new maplibregl.Map({container:"map", style:BASEMAPS[DEFAULT_BM],
  bounds:BOUNDS, fitBoundsOptions:{padding:24}});
const overlay = new deck.MapboxOverlay({interleaved:false, layers:[]});
map.addControl(overlay); map.addControl(new maplibregl.NavigationControl());
const DASH = deck.PathStyleExtension ? [new deck.PathStyleExtension({dash:true})] : [];

function interp(t, z, hi){
  const k = Object.keys(t).map(Number).sort((a,b)=>a-b);
  if(!k.length) return 1.5;
  if(z <= k[0]) return t[k[0]];
  const last = k[k.length-1];
  if(z >= last) return t[last]*Math.pow(hi, z-last);
  for(let i=0;i<k.length-1;i++) if(z<=k[i+1]){ const f=(z-k[i])/(k[i+1]-k[i]); return t[k[i]]+(t[k[i+1]]-t[k[i]])*f; }
  return t[last];
}
const LINK_W = 0.6;
function fillW(f){ const g=f.properties.g; const w=interp(FILL[g]||FILL.residential||{13:2}, map.getZoom(), HI_RATE[g]||1.9); return f.properties.lk ? w*LINK_W : w; }
function casW(f){ return f.properties.cc ? fillW(f)*(CASING[f.properties.g]||1.3) : 0; }

let zt = 0;
function layersFor(d){
  const url = "data/"+d.id+".geojson";
  if(d.kind === "polygon")
    return [new deck.GeoJsonLayer({id:d.id, data:url, visible:state[d.id], stroked:false, filled:true, getFillColor:f=>f.properties.fc})];
  if(d.kind === "point")
    return [new deck.GeoJsonLayer({id:d.id, data:url, visible:state[d.id], pointType:"circle",
      getFillColor:f=>f.properties.pc, pointRadiusUnits:"pixels", getPointRadius:3.5, pointRadiusMinPixels:2.5,
      stroked:true, getLineColor:[255,255,255,200], lineWidthMinPixels:0.5})];
  if(d.kind === "road")
    return [
      new deck.GeoJsonLayer({id:d.id+"-cas", data:url, visible:state[d.id], stroked:true, filled:false,
        lineWidthUnits:"pixels", lineWidthMinPixels:0.5, opacity:0.9,
        getLineColor:f=>f.properties.cc||[0,0,0,0], getLineWidth:casW, updateTriggers:{getLineWidth:[zt]}}),
      new deck.GeoJsonLayer({id:d.id+"-fill", data:url, visible:state[d.id], stroked:true, filled:false,
        lineWidthUnits:"pixels", lineWidthMinPixels:0.6, getLineColor:f=>f.properties.c, getLineWidth:fillW,
        extensions:DASH, dashJustified:true, getDashArray:f=>f.properties.dash||[0,0], updateTriggers:{getLineWidth:[zt]}}),
    ];
  return [new deck.GeoJsonLayer({id:d.id, data:url, visible:state[d.id], stroked:true, filled:false,
    lineWidthUnits:"pixels", lineWidthMinPixels:0.5, getLineColor:f=>f.properties.c, getLineWidth:f=>f.properties.w})];
}
function overlayLayers(){                                   // names + arrows (deck TextLayers)
  const z = map.getZoom(), out = [];
  for(const rid of ROADIDS){
    if(state[rid] && S.names)
      out.push(new deck.TextLayer({id:rid+"-nm", data:"data/"+rid+"_labels.geojson", dataTransform:d=>d.features||[],
        visible: z >= NAMESMINZ, getPosition:f=>f.geometry.coordinates, getText:f=>f.properties.nm,
        getAngle:f=>f.properties.na, getSize:12, getColor:[45,45,45], fontFamily:"system-ui, sans-serif",
        getTextAnchor:"middle", getAlignmentBaseline:"center",
        outlineWidth:3, outlineColor:[255,255,255,230], fontSettings:{sdf:true}}));
    if(state[rid] && S.arrows)
      out.push(new deck.TextLayer({id:rid+"-ar", data:"data/"+rid+"_arrows.geojson", dataTransform:d=>d.features||[],
        visible: z >= ARROWSMINZ, getPosition:f=>f.geometry.coordinates, getText:()=>"\\u25B6",
        getAngle:f=>f.properties.ang, getSize:13, getColor:[120,120,120],
        getTextAnchor:"middle", getAlignmentBaseline:"center"}));
  }
  return out;
}
function rebuild(){
  zt = Math.round(map.getZoom()*5)/5;
  overlay.setProps({layers: DEFS.flatMap(layersFor).concat(overlayLayers())});
  document.getElementById("zoom").textContent = "zoom " + map.getZoom().toFixed(1);
}

const panel = document.getElementById("panel");
DEFS.slice().reverse().forEach(d => {
  const lab = document.createElement("label");
  lab.innerHTML = '<input type="checkbox" checked> ' + d.id;
  lab.querySelector("input").onchange = e => { state[d.id] = e.target.checked; rebuild(); };
  panel.appendChild(lab);
});
document.getElementById("names_cb").onchange = e => { S.names = e.target.checked; rebuild(); };
document.getElementById("arrows_cb").onchange = e => { S.arrows = e.target.checked; rebuild(); };
const sel = document.getElementById("basemap");
Object.keys(BASEMAPS).forEach(k => { const o = document.createElement("option"); o.value = k; o.text = k; if(k === DEFAULT_BM) o.selected = true; sel.appendChild(o); });
sel.onchange = e => { map.setStyle(BASEMAPS[e.target.value]); map.once("idle", rebuild); };

map.on("load", rebuild);
map.on("zoom", rebuild);
</script></body></html>"""
