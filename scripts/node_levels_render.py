"""PROTOTYPE renderer for Approach B (docs/design/node_levels.md): builds a page where each edge's casing is drawn at the
lowest level of its two nodes and its fill at the highest, one casing layer and one fill layer per level. Done in the
browser on top of a normal page, with no change to roadstyle or to the library. Tunnel / bridge looks are not redone.

    python scripts/node_levels_render.py DB OUT.html
    python scripts/node_levels_render.py DB OUT_DIR lon,lat,zoom [lon,lat,zoom ...]     # screenshots
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

PREP = """() => {
  const L = map.getStyle().layers, find = (id) => L.find((l) => l.id === id);
  const casing = find("roads-casing"), fill = find("roads-fill");
  const levels = [...new Set(map.queryRenderedFeatures().filter(f => f.properties && f.properties._cl !== undefined)
        .flatMap(f => [f.properties._cl, f.properties._fl]))];
  return JSON.stringify({levels, ok: !!(casing && fill)});
}"""

BUILD = """(levels) => {
  const keep = (id) => /highlight|label|arrow|dash|bridge|ends/.test(id);
  for (const l of map.getStyle().layers)
    if (/^roads-/.test(l.id) && !keep(l.id)) map.setLayoutProperty(l.id, "visibility", "none");
  const get = (id) => map.getStyle().layers.find((l) => l.id === id);
  const c0 = get("roads-casing"), f0 = get("roads-fill"), before = "roads-highlight";
  for (const lv of levels) {
    const part = (base, key, name) => ({...JSON.parse(JSON.stringify(base)), id: "nl-" + name + "-" + lv,
      filter: ["==", ["get", key], lv], layout: {...base.layout, visibility: "visible"}});
    map.addLayer(part(c0, "_cl", "casing"), before);
    map.addLayer(part(f0, "_fl", "fill"), before);
  }
}"""


def build_page(db, out, ct=None):
    import mapstyle as ms
    import mapstyle.map as mm
    from node_levels import report
    if ct is None:
        edges, pairs, p, left, ct, dropped = report(db)
    orig = mm.load_roads

    def load(d):
        roads = orig(d)
        roads["_cl"] = [ct.get(e, (0, 0))[0] for e in roads["edge_id"]]
        roads["_fl"] = [ct.get(e, (0, 0))[1] for e in roads["edge_id"]]
        return roads
    mm.load_roads = load
    try:
        ms.render_map(str(db), pieces=False).save(str(out))
    finally:
        mm.load_roads = orig
    return ct


def shoot(page, out_dir, spots, size=(760, 460), build=True, levels=(-3, -2, -1, 0, 1, 2, 3)):
    from playwright.sync_api import sync_playwright
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)
    hide = ".maplibregl-ctrl,.maplibregl-ctrl-top-left,.maplibregl-ctrl-top-right,.rs-tl,.flt-ctrl,.ov-ctrl{display:none!important}"
    idle = "() => new Promise(r => { const t = setTimeout(r, 6000); map.once('idle', () => { clearTimeout(t); r(); }); map.triggerRepaint(); })"
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": size[0], "height": size[1]})
        pg.goto("file://" + str(page))
        pg.wait_for_function("window.map", timeout=120000)
        pg.add_style_tag(content=hide)
        pg.wait_for_timeout(3000)
        built = False
        for name, (x, y, z) in spots.items():
            for _ in range(2):
                pg.evaluate("([x,y,z]) => { map.setMaxZoom(24); map.stop(); map.jumpTo({center: [x, y], zoom: z}); }", [x, y, z])
                pg.evaluate(idle)
                pg.wait_for_timeout(1200)
            if build and not built:      # a casing layer and a fill layer for each level in use (-3 .. 3: harmless when empty)
                pg.evaluate(BUILD, list(levels))
                built = True
                pg.evaluate(idle)
                pg.wait_for_timeout(1200)
            pg.screenshot(path=str(out_dir / f"{name}.png"))
        b.close()


if __name__ == "__main__":
    db, out = sys.argv[1], Path(sys.argv[2])
    if len(sys.argv) == 3:
        build_page(db, out)
    else:
        page = out / "page.html"
        out.mkdir(exist_ok=True)
        build_page(db, page)
        spots = {f"s{i}": tuple(float(v) for v in a.split(",")) for i, a in enumerate(sys.argv[3:])}
        shoot(page, out, spots)
