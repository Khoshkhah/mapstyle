// mapstyle's feature layers on a roadstyle page (docs/design/feature_layers.md). Each layer is a
// roadstyle overlay (window.RS_OVERLAYS, by label); this adds what an overlay can't draw: colour by
// `kind`, zoom ranges, dashes, textures, icons. Every layer added here is pushed into the overlay's
// `layers`, so rsSetOverlay / the Layers control hide it with its overlay.
(function(){
const MS = __MS__, map = window.map;
// keep roadstyle's hover / select `case` around a new base colour
const swap = (e, v) => Array.isArray(e) && e[0] === "case" ? e.slice(0, -1).concat([v]) : v;
const match = (by) => ["match", ["get", "kind"], ...Object.entries(by.map).flat(), by.default];
const loadImage = ([name, url]) => new Promise(done => {
  const img = new Image();
  img.onload = () => { if (!map.hasImage(name)) map.addImage(name, img); done(); };
  img.onerror = done;
  img.src = url;
});
const run = async () => {
  await Promise.all(Object.entries(MS.images).map(loadImage));
  const byLabel = Object.fromEntries((window.RS_OVERLAYS || []).map(o => [o.label, o]));
  MS.layers.forEach(L => {
    const ov = byLabel[L.label]; if (!ov) return;
    const body = ov.layers[0], vis = ov.visible === false ? "none" : "visible";
    const add = (spec, before) => {
      map.addLayer({...spec, source: ov.source, layout: {...(spec.layout || {}), visibility: vis}}, before);
      ov.layers.push(spec.id);
    };
    const paint = {fill: "fill-color", line: "line-color", circle: "circle-color"}[L.kind];
    if (L.color_by) map.setPaintProperty(body, paint, swap(map.getPaintProperty(body, paint), match(L.color_by)));
    if (L.outline_by) map.setPaintProperty(ov.layers[1], "line-color", match(L.outline_by));
    if (L.dash) map.setPaintProperty(body, "line-dasharray", L.dash);
    if (L.patterns) add({id: ov.source + "-pattern", type: "fill",
      filter: ["match", ["get", "kind"], Object.keys(L.patterns), true, false],
      paint: {"fill-pattern": ["match", ["get", "kind"], ...Object.entries(L.patterns).flat(),
                               Object.values(L.patterns)[0]]}}, ov.layers[1]);
    if (L.icon) {
      add({id: ov.source + "-icon", type: "symbol",
        layout: {"icon-image": L.icon.image, "icon-allow-overlap": true,
                 "icon-size": ["interpolate", ["linear"], ["zoom"], ...L.icon.size.flat()],
                 "icon-rotate": ["coalesce", ["get", "bearing"], 0], "icon-rotation-alignment": "map"},
        paint: {"icon-opacity": L.icon.opacity}});
      // the circle stays as the click / hover target, unseen under the icon
      map.setPaintProperty(body, "circle-opacity", 0);
      map.setPaintProperty(body, "circle-stroke-width", 0);
    }
    if (L.min_zoom) ov.layers.forEach(id => map.setLayerZoomRange(id, L.min_zoom, 24));
  });
};
if (map.isStyleLoaded()) run(); else map.on("load", run);
})();
