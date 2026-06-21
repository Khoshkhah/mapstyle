"""'web' backend — a self-contained deck.gl + MapLibre page with per-layer toggle checkboxes.

lonboard's standalone HTML has no layer switch; this does. Each layer is baked to a GeoJSON
file (per-feature color/width from roadstyle for lines, palette for polygons) and drawn by a
deck.gl GeoJsonLayer; checkboxes flip each layer's visibility live. Reuses roadstyle.resolve
for the road styling, so it matches the other backends.

basemap: "osm" = the real OSM Standard raster tiles (so the underlay IS osm.org's base layer),
"positron"/"dark" = Carto vector styles.
"""

import json
from pathlib import Path

from mapstyle.roads import resolve_road
from mapstyle.palettes import polygon_style

def _raster(tiles, attr, tile_size=256):
    return {"version": 8,
            "sources": {"r": {"type": "raster", "tileSize": tile_size, "tiles": tiles,
                              "attribution": attr}},
            "layers": [{"id": "r", "type": "raster", "source": "r"}]}


_BLANK = {"version": 8, "sources": {},
          "layers": [{"id": "bg", "type": "background", "paint": {"background-color": "#f7f5f1"}}]}

# label -> MapLibre style (URL string or inline object); selectable in the viewer.
BASEMAPS = {
    "OSM Standard": _raster(["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
                            "© OpenStreetMap contributors"),
    "Carto Positron": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    "Carto Dark": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    "Satellite": _raster(
        ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        "© Esri"),
    "None (layers only)": _BLANK,
}
_BM_ALIAS = {"osm": "OSM Standard", "positron": "Carto Positron", "dark": "Carto Dark",
             "satellite": "Satellite", "none": "None (layers only)"}


_SERVE_PY = '''#!/usr/bin/env python3
"""Static server for this mapstyle render dir.
   python serve.py [port]   ->  http://localhost:8080/index.html"""
import sys, http.server, socketserver
from functools import partial
from pathlib import Path


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
here = str(Path(__file__).resolve().parent)
with socketserver.TCPServer(("", port), partial(Handler, directory=here)) as httpd:
    print(f"serving {here} at http://localhost:{port}/index.html")
    httpd.serve_forever()
'''


def write_serve(out_dir) -> "Path":
    from pathlib import Path
    p = Path(out_dir) / "serve.py"
    p.write_text(_SERVE_PY)
    return p


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _bake_line(layer, theme):
    import shapely.geometry as sg
    override = _rgb(layer.color) if layer.color else None
    feats = []
    gdf = layer.gdf
    for geom, hw in zip(gdf.geometry, gdf["highway"].fillna("unclassified")):
        if geom is None or geom.is_empty:
            continue
        s = resolve_road(hw)
        feats.append({
            "type": "Feature", "geometry": sg.mapping(geom),
            "properties": {
                "c": override or _rgb(s.fill), "w": s.width,
                "cc": _rgb(s.casing) if s.casing else None,
                "cw": max(s.casing_width, s.width + 0.6) if s.casing else 0,
                "dash": list(s.dash) if s.dash else None,
            },
        })
    return {"type": "FeatureCollection", "features": feats}


def _bake_polygon(layer):
    import shapely.geometry as sg
    name = layer.name
    feats = []
    for geom, cls in zip(layer.gdf.geometry, layer.gdf["class"]):
        if geom is None or geom.is_empty:
            continue
        st = polygon_style(name, cls)
        feats.append({
            "type": "Feature", "geometry": sg.mapping(geom),
            "properties": {"fc": _rgb(st["fillColor"]) + [int(st["fillOpacity"] * 255)]},
        })
    return {"type": "FeatureCollection", "features": feats}


def render_web(layers, out_dir, theme="light", basemap="osm", title="mapstyle — Tartu"):
    out = Path(out_dir)
    (out / "data").mkdir(parents=True, exist_ok=True)

    defs, bbox = [], None
    for layer in sorted(layers, key=lambda x: x.z):
        fc = _bake_line(layer, theme) if layer.kind == "line" else _bake_polygon(layer)
        (out / "data" / f"{layer.name}.geojson").write_text(json.dumps(fc))
        defs.append({"id": layer.name, "kind": layer.kind})
        if not layer.gdf.empty:
            minx, miny, maxx, maxy = layer.gdf.total_bounds
            bbox = [minx, miny, maxx, maxy] if bbox is None else [
                min(bbox[0], minx), min(bbox[1], miny), max(bbox[2], maxx), max(bbox[3], maxy)]

    center = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2] if bbox else [0, 0]
    default_bm = _BM_ALIAS.get(basemap, basemap if basemap in BASEMAPS else "OSM Standard")
    html = (_TEMPLATE
            .replace("__DEFS__", json.dumps(defs))
            .replace("__CENTER__", json.dumps(center))
            .replace("__BASEMAPS__", json.dumps(BASEMAPS))
            .replace("__DEFAULT_BM__", default_bm)
            .replace("__TITLE__", title))
    index = out / "index.html"
    index.write_text(html)
    return str(index)


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
</style></head><body>
<div id="map"></div><div id="panel"><b>Base layer</b><select id="basemap"></select><b>Layers</b></div>
<script>
const DEFS = __DEFS__, CENTER = __CENTER__, BASEMAPS = __BASEMAPS__, DEFAULT_BM = "__DEFAULT_BM__";
const state = {}; DEFS.forEach(d => state[d.id] = true);

const map = new maplibregl.Map({container:"map", style:BASEMAPS[DEFAULT_BM], center:CENTER, zoom:13});
const overlay = new deck.MapboxOverlay({interleaved:false, layers:[]});
map.addControl(overlay);
map.addControl(new maplibregl.NavigationControl());

const DASH = deck.PathStyleExtension ? [new deck.PathStyleExtension({dash:true})] : [];

function layersFor(d){
  const url = "data/"+d.id+".geojson";
  if(d.kind === "polygon"){
    return [new deck.GeoJsonLayer({id:d.id, data:url, visible:state[d.id],
      stroked:false, filled:true, getFillColor:f=>f.properties.fc})];
  }
  return [
    new deck.GeoJsonLayer({id:d.id+"-cas", data:url, visible:state[d.id], stroked:true, filled:false,
      lineWidthUnits:"pixels", lineWidthMinPixels:0.6, opacity:0.9,
      getLineColor:f=>f.properties.cc||[0,0,0,0], getLineWidth:f=>f.properties.cw||0}),
    new deck.GeoJsonLayer({id:d.id+"-fill", data:url, visible:state[d.id], stroked:true, filled:false, pickable:true,
      lineWidthUnits:"pixels", lineWidthMinPixels:0.5,
      getLineColor:f=>f.properties.c, getLineWidth:f=>f.properties.w,
      extensions:DASH, dashJustified:true, dashGapPickable:true,
      getDashArray:f=>f.properties.dash||[0,0]}),
  ];
}
function rebuild(){ overlay.setProps({layers: DEFS.flatMap(layersFor)}); }

const panel = document.getElementById("panel");
DEFS.slice().reverse().forEach(d => {            // top layer first in the panel
  const lab = document.createElement("label");
  lab.innerHTML = '<input type="checkbox" checked> ' + d.id;
  lab.querySelector("input").onchange = e => { state[d.id] = e.target.checked; rebuild(); };
  panel.appendChild(lab);
});

// base-layer selector
const sel = document.getElementById("basemap");
Object.keys(BASEMAPS).forEach(k => {
  const o = document.createElement("option");
  o.value = k; o.text = k; if(k === DEFAULT_BM) o.selected = true;
  sel.appendChild(o);
});
sel.onchange = e => { map.setStyle(BASEMAPS[e.target.value]); map.once("idle", rebuild); };

map.on("load", rebuild);
</script></body></html>"""
