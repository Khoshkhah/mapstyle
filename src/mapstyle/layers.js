// mapstyle's part of a roadstyle page (docs/design/feature_layers.md, docs/design/dashboard.md).
// 1. Feature layers: each is a roadstyle overlay (window.RS_OVERLAYS, by label); this adds what an
//    overlay can't draw: colour by `kind`, zoom ranges, dashes, textures, icons. Every layer added
//    here is pushed into the overlay's `layers`, so rsSetOverlay / the Layers control hide it too.
// 2. The rs* functions mapstyle adds, defined like roadstyle's own (and only where the page has
//    none yet): rsSetModes / rsGetModes, rsSetAccess / rsGetAccess / RS_ACCESS, rsSetKinds /
//    rsGetKinds / RS_KINDS, rsSetInteraction / rsGetInteraction; and the colour and Roads-box rows
//    of the roads you may not use (private, bus).
// 3. The Roads and Layers boxes: both folded at the start, Layers under Roads and foldable like it.
// 3. (below) the Roads and Layers boxes: folded at the start, Layers under Roads; map.py keeps both
//    unseen until they are placed, so neither jumps (a fallback shows them after 8 s regardless).
setTimeout(() => placeBoxes(), 8000);
(function start(){
// poll, like roadstyle's own page code: `window.map` is the container <div> until the map is built,
// and `load` / `idle` can fire before this runs or not at all (offline, failed tile requests)
const MS = __MS__, map = window.map;
if (!(map && typeof map.getSource === "function" && map.isStyleLoaded() &&
      window.rsQuery && rsQuery(() => true).length)) return setTimeout(start, 100);   // the roads loaded too
placeBoxes();
// keep roadstyle's hover / select `case` around a new base colour
const swap = (e, v) => Array.isArray(e) && e[0] === "case" ? e.slice(0, -1).concat([v]) : v;
// colour by kind; with no kinds listed (a theme can empty a list) just the default
const match = (by) => Object.keys(by.map).length ? ["match", ["get", "kind"], ...Object.entries(by.map).flat(), by.default] : by.default;
const loadImage = ([name, url]) => new Promise(done => {
  const img = new Image();
  img.onload = () => { if (!map.hasImage(name)) map.addImage(name, img); done(); };
  img.onerror = done;
  img.src = url;
});
const define = (name, fn) => { if (!(name in window)) window[name] = fn; };
const fire = (type, detail) => document.dispatchEvent(new CustomEvent(type, {detail}));
const byLabel = {};
const overlay = (l) => typeof l === "number" ? (window.RS_OVERLAYS || [])[l] : byLabel[l];

// ---- rsSetModes: the roads any of these modes can use (the driving / walking / cycling flags), and
// rsSetAccess: show / hide the roads you may not use (`access`: private, bus); one rsFilter for both
let modes = null;
const hiddenAccess = new Set();
const roadFilter = () => {
  const ok = (p) => (modes == null || modes.some((m) => p[m] === true || p[m] === "true")) &&
    !(p.access && hiddenAccess.has(p.access));
  rsFilter(modes == null && !hiddenAccess.size ? null : rsQuery(ok));
};
define("rsSetModes", (list) => {
  modes = list == null ? null : Array.from(list);
  roadFilter();
  fire("rs:filterchange", {modes: modes && modes.slice()});
});
define("rsGetModes", () => modes && modes.slice());
define("rsSetAccess", (kind, on) => {
  on ? hiddenAccess.delete(kind) : hiddenAccess.add(kind);
  roadFilter();
  const box = document.getElementById("ms-flt-" + kind); if (box) box.checked = !!on;
  fire("rs:filterchange", {access: kind, visible: !!on});
});
define("rsGetAccess", () => Object.fromEntries(ACCESS.map(([k]) => [k, !hiddenAccess.has(k)])));

// ---- roads you may not use (duckOSM's private_edges; docs/design/private_and_bus.md): their own
// colour as the BASE of every road fill (so rsColor and the colour options still paint over them),
// again after each recolouring, and a row each in the Roads box after Bridges / Tunnels
const ACCESS = [["private", "#c8c8c8", "Private roads"], ["bus", "#9db8d9", "Bus lanes"]];
// The colour is set by edge id, not by the `access` property: tiles (tiles=True) do not carry it, but rsQuery reads
// it from the page's own table. Simple mode: only the fill pieces (__rs_k == 1) of roads-simple; full look: the fill layers.
const accessIds = {};
const isAccess = (k, edge) => ["any", ["match", edge, accessIds[k], true, false], ["match", ["get", "__rs_edge2"], accessIds[k], true, false]];
const withAccess = (e, edge, only) => {
  const mine = ACCESS.filter(([k]) => accessIds[k].length);
  if (!mine.length) return e;
  const cond = (k) => only ? ["all", only, isAccess(k, edge)] : isAccess(k, edge);
  if (Array.isArray(e) && e[0] === "case") {
    if (JSON.stringify(e[1]) === JSON.stringify(cond(mine[0][0]))) return e;           // already painted
    if (!only) return e.slice(0, -1).concat([withAccess(e[e.length - 1], edge, only)]); // under rsColor's cases
  }
  return ["case", ...mine.flatMap(([k, c]) => [cond(k), c]), e];
};
const paintAccess = () => {
  ACCESS.forEach(([k]) => { accessIds[k] = rsQuery((p) => p.access === k).map(Number).sort((a, b) => a - b); });
  const layers = map.getStyle().layers;
  const simple = layers.find((l) => l.id === "roads-simple");
  (simple ? [simple] : layers.filter((l) => l.type === "line" && /^roads-.*fill/.test(l.id))).forEach((l) => {
    const edge = !simple && l.source === "roads" ? ["id"] : ["get", "__rs_edge"];   // a simple piece names its edge in __rs_edge (its own id is the piece's)
    map.setPaintProperty(l.id, "line-color", withAccess(map.getPaintProperty(l.id, "line-color"), edge, simple ? ["==", ["get", "__rs_k"], 1] : null));
  });
};

const run = async () => {
  await Promise.all(Object.entries(MS.images).map(loadImage));
  (window.RS_OVERLAYS || []).forEach((o) => { byLabel[o.label] = o; });
  const paint = {fill: "fill-color", line: "line-color", circle: "circle-color"};
  const state = {};                                   // label -> {clickable, tooltip, popup}
  const base = {};                                    // label -> {layer id: own filter}
  const kinds = {};                                   // label -> kinds shown, or null
  MS.layers.forEach(L => {
    const ov = byLabel[L.label]; if (!ov) return;
    const body = ov.layers[0], vis = ov.visible === false ? "none" : "visible";
    // the body layers: one for a plain overlay, one for each (fill number, order) for an overlay attached to edges (docs/design/edge_features.md); not the outline of a polygon
    const bodies = ov.layers.filter((id) => map.getLayer(id).type === map.getLayer(body).type);
    const add = (spec, before) => {
      map.addLayer({...spec, source: ov.source, layout: {...(spec.layout || {}), visibility: vis}}, before);
      ov.layers.push(spec.id);
    };
    const p = paint[L.kind];
    if (L.color_by) map.setPaintProperty(body, p, swap(map.getPaintProperty(body, p), match(L.color_by)));
    if (L.outline_by) map.setPaintProperty(ov.layers[1], "line-color", match(L.outline_by));
    if (L.dash) map.setPaintProperty(body, "line-dasharray", L.dash);
    if (L.patterns && Object.keys(L.patterns).length) add({id: ov.source + "-pattern", type: "fill",
      filter: ["match", ["get", "kind"], Object.keys(L.patterns), true, false],
      paint: {"fill-pattern": ["match", ["get", "kind"], ...Object.entries(L.patterns).flat(),
                               Object.values(L.patterns)[0]]}}, ov.layers[1]);
    if (L.icon) {
      // on a road's level: an icon layer right after each circle layer, with its filter; else one icon layer on top of the map
      const onEdge = bodies.some((id) => JSON.stringify(map.getFilter(id) || null).includes("__rs_fl"));
      bodies.forEach((id, k) => {
        const ids = map.getStyle().layers.map((l) => l.id);
        add({id: ov.source + "-icon" + (k || ""), type: "symbol", ...(onEdge ? {filter: map.getFilter(id)} : {}),
          layout: {"icon-image": L.icon.image, "icon-allow-overlap": true,
                   "icon-size": ["interpolate", ["linear"], ["zoom"], ...L.icon.size.flat()],
                   "icon-rotate": ["coalesce", ["get", "bearing"], 0], "icon-rotation-alignment": "map"},
          paint: {"icon-opacity": L.icon.opacity}}, onEdge ? ids[ids.indexOf(id) + 1] : undefined);
      });
      // the circle stays as the click / hover target, unseen and as big as the icon (an icon is
      // 48 px scaled by icon-size, so its radius is 24 x that): a click anywhere on the icon is its
      // click, not the road's under it
      bodies.forEach((id) => {
        map.setPaintProperty(id, "circle-opacity", 0);
        map.setPaintProperty(id, "circle-stroke-width", 0);
        map.setPaintProperty(id, "circle-radius",
          ["interpolate", ["linear"], ["zoom"], ...L.icon.size.map(([z, s]) => [z, s * 24]).flat()]);
      });
    }
    if (L.min_zoom) ov.layers.forEach(id => map.setLayerZoomRange(id, L.min_zoom, 24));
    base[L.label] = Object.fromEntries(ov.layers.map((id) => [id, map.getFilter(id) || null]));
    kinds[L.label] = null;
    // every layer is built clickable with a tooltip, so each switch can go both ways; the page
    // opens with the state render_map(interaction=) asked for
    state[L.label] = {clickable: true, tooltip: true, popup: true,
                      color: map.getPaintProperty(body, p), paint: p, body, bodies, tip: ov.tooltip};
    setInteraction(L.label, L.interaction);
    rsSetOverlay(L.label, true);                       // built hidden (map.py): shown once styled
  });

  // ---- rsSetInteraction: a layer's clicks, hover tooltip and click popup ----------------------
  // roadstyle reads ov.interactive on every click and ov.tooltip on every hover; its hover recolour
  // follows the layer's colour `case`, dropped while the layer isn't clickable
  function setInteraction(label, opts) {
    const ov = overlay(label), s = ov && state[ov.label]; if (!s) return;
    for (const k of ["clickable", "tooltip", "popup"]) if (opts && k in opts) s[k] = !!opts[k];
    ov.interactive = s.clickable;
    ov.tooltip = s.tooltip ? s.tip : null;
    const c = s.color;
    s.bodies.forEach((id) => map.setPaintProperty(id, s.paint, s.clickable || !Array.isArray(c) || c[0] !== "case" ? c : c[c.length - 1]));
    fire("rs:interactionchange", {overlay: ov.label, clickable: s.clickable, tooltip: s.tooltip, popup: s.popup});
  }
  // popup off: roadstyle opens a popup for every clicked layer and sends rs:select right after, so
  // close it there; the click still selects and still reaches every rs:select listener
  document.addEventListener("rs:select", (e) => {
    const s = e.detail.overlay && state[e.detail.overlay];
    if (s && !s.popup) {
      const ps = document.querySelectorAll(".maplibregl-popup:not(.rs-tip)");
      if (ps.length) ps[ps.length - 1].remove();
    }
  });
  define("rsSetInteraction", setInteraction);
  define("rsGetInteraction", (label) => {
    const ov = overlay(label), s = ov && state[ov.label];
    return s ? {clickable: s.clickable, tooltip: s.tooltip, popup: s.popup} : null;
  });

  // ---- rsSetKinds: only these kinds of a layer, on top of each of its layers' own filters -------
  define("rsSetKinds", (label, list) => {
    const ov = overlay(label); if (!ov || !base[ov.label]) return;
    kinds[ov.label] = list == null ? null : Array.from(list);
    for (const id of ov.layers) {
      const own = base[ov.label][id], k = kinds[ov.label];
      const kf = k == null ? null : ["in", ["get", "kind"], ["literal", k]];
      map.setFilter(id, kf && own ? ["all", own, kf] : kf || own);
    }
    fire("rs:filterchange", {overlay: ov.label, kinds: kinds[ov.label] && kinds[ov.label].slice()});
  });
  define("rsGetKinds", (label) => { const ov = overlay(label), k = ov && kinds[ov.label]; return k ? k.slice() : null; });
  if (!("RS_KINDS" in window)) window.RS_KINDS = MS.kinds;
  const restricted = ACCESS.filter(([k]) => rsQuery((p) => p.access === k).length);
  if (restricted.length) {
    paintAccess();
    document.addEventListener("rs:colorchange", paintAccess);
    const body = document.querySelector(".flt-ctrl .flt-body");
    restricted.forEach(([k, c, label], i) => {
      if (!body) return;
      const lab = document.createElement("label"), cb = document.createElement("input"), sw = document.createElement("span");
      if (i === 0) lab.style.cssText = "margin-top:4px;padding-top:4px;border-top:1px solid #ddd";
      cb.type = "checkbox"; cb.checked = true; cb.id = "ms-flt-" + k;
      cb.onchange = () => rsSetAccess(k, cb.checked);
      sw.className = "flt-sw"; sw.style.background = c;
      lab.append(cb, sw, document.createTextNode(" " + label));
      body.appendChild(lab);
    });
  }
  window.RS_ACCESS = Object.fromEntries(restricted.map(([k]) => [k, rsQuery((p) => p.access === k).length]));
  fire("ms:ready", {});
};
run();
})();

// ---- 3. The Roads and Layers boxes ---------------------------------------------------------------
// (Kaveh, 2026-09-30) Both start folded; the Layers box (roadstyle's, fixed at the bottom right with
// no fold) goes under Roads in the top-left stack and folds like it (a page with no stack, the
// planner, keeps it in place; panel pages have none: their layers sit in the Roads card). map.py's
// head CSS keeps a box unseen until it has data-ms, so it never shows unfolded or in the wrong place
// ("it first creates that box and then moves it"); placed once the map is ready, when the planner's
// side panel is docked too.
function placeBoxes() {
  const flt = document.querySelector(".flt-ctrl"), ovBox = document.querySelector(".ov-ctrl");
  const stack = document.getElementById("rs-tl");
  if (flt && !flt.dataset.ms) {
    flt.classList.add("collapsed");
    const hd = flt.querySelector(".flt-hd");
    if (hd) hd.textContent = "Roads ▸";
    flt.dataset.ms = "1";
  }
  if (ovBox && !ovBox.dataset.ms) {
    const hd = ovBox.querySelector(".ov-hd"), body = ovBox.querySelector(".ov-body");
    if (stack) Object.assign(ovBox.style, {position: "static", maxHeight: "none", overflow: "auto", minHeight: "0"});
    Object.assign(hd.style, {cursor: "pointer", userSelect: "none"});
    body.style.display = "none";
    hd.textContent = "Layers ▸";
    hd.onclick = () => {
      const open = body.style.display === "none";
      body.style.display = open ? "" : "none";
      hd.textContent = "Layers " + (open ? "▾" : "▸");
    };
    if (stack) stack.appendChild(ovBox);
    ovBox.dataset.ms = "1";
  }
}
