"""Browser check for a dashboard page (``mapstyle db --dashboard``): mapstyle's rs* functions
(rsSetModes, rsSetKinds, rsSetInteraction) and the panel's boxes, on what the map actually draws.
Prints one line per check and saves a screenshot next to the page. Needs playwright.

    python scripts/dashboard_check.py monaco_dashboard.html
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

DRAWN = """([layer, prop]) => { const ids = map.getStyle().layers.map(l => l.id).filter(i => i.startsWith(layer));
  return [...new Set(map.queryRenderedFeatures({layers: ids}).map(f => f.properties[prop]))].sort(); }"""


async def main(path):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1300, "height": 850})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + os.path.abspath(path))
        await pg.wait_for_function("window.rsSetKinds && document.querySelector('.ms-set')", timeout=600000)
        ev = pg.evaluate
        idle = "() => new Promise(r => { map.once('idle', r); map.triggerRepaint(); })"
        ov = await ev("() => Object.fromEntries(RS_OVERLAYS.map(o => [o.label, o.source]))")
        await ev("() => { map.jumpTo({center: [7.4215, 43.737], zoom: 16.5}); }"); await ev(idle)

        # modes: walking only -> no drawn road that walking can't use
        await ev("() => rsSetModes(['walking'])"); await ev(idle)
        print("rsSetModes(['walking']): drawn walking flags", await ev(DRAWN, ["roads-fill", "walking"]),
              "| rsGetModes", await ev("() => rsGetModes()"))
        await ev("() => rsSetModes(null)"); await ev(idle)

        # kinds: only parks among the landcover
        before = await ev(DRAWN, [ov["landcover"], "kind"])
        await ev("() => rsSetKinds('landcover', ['park'])"); await ev(idle)
        print("rsSetKinds('landcover', ['park']): drawn kinds", before, "->",
              await ev(DRAWN, [ov["landcover"], "kind"]), "| rsGetKinds", await ev("() => rsGetKinds('landcover')"))
        await ev("() => rsSetKinds('landcover', null)"); await ev(idle)

        # interaction: click a building with the popup on, then off
        # a point inside a building with no road within roadstyle's 4 px pick box (buildings sit
        # under the roads, so a road that close takes the click)
        await ev("() => { map.jumpTo({center: [7.4215, 43.737], zoom: 18}); }"); await ev(idle)
        pt = await ev("""() => { const ids = map.getStyle().layers.map(l => l.id).filter(i => i.startsWith('%s'));
            const r = map.getCanvas().getBoundingClientRect();
            for (const f of map.queryRenderedFeatures({layers: ids})) {
              const ring = f.geometry.coordinates[0], n = ring.length - 1;
              const c = ring.slice(0, n).reduce((a, p) => [a[0] + p[0] / n, a[1] + p[1] / n], [0, 0]);
              const q = map.project(c), hit = map.queryRenderedFeatures([q.x, q.y]);
              const near = map.queryRenderedFeatures([[q.x - 8, q.y - 8], [q.x + 8, q.y + 8]]);
              if (near.every(h => !h.layer.id.startsWith('roads')) && hit.some(h => ids.includes(h.layer.id)))
                return [r.left + q.x, r.top + q.y];
            } return null; }""" % ov["buildings"])
        print("building click point", pt)
        await ev("() => { window._msSel = []; document.addEventListener('rs:select', e => _msSel.push(e.detail.overlay || 'road')); }")
        popups = "() => document.querySelectorAll('.maplibregl-popup:not(.rs-tip)').length"
        for opts in ("{popup: true}", "{popup: false}", "{clickable: false}"):
            await ev("() => document.querySelectorAll('.maplibregl-popup').forEach(p => p.remove())")
            await ev(f"() => rsSetInteraction('buildings', {opts})")
            await pg.mouse.click(*pt); await pg.wait_for_timeout(500)
            print(f"rsSetInteraction('buildings', {opts}): popups open {await ev(popups)},",
                  f"rs:select {await ev('() => _msSel.splice(0)')},", "state", await ev("() => rsGetInteraction('buildings')"))
        await ev("() => rsSetInteraction('buildings', {clickable: true, popup: true})")

        # the panel: untick Driving
        await pg.locator(".rp-chk", has_text="driving").first.locator("input").uncheck()
        print("panel: Driving unticked -> rsGetModes", await ev("() => rsGetModes()"))
        await pg.locator(".rp-chk", has_text="driving").first.locator("input").check()
        await pg.select_option("#rp-co", label="Modes"); await ev(idle)
        shot = os.path.splitext(path)[0] + "_check.png"
        await pg.screenshot(path=shot)
        print("colour by Modes; screenshot", shot)
        print("errors", errs[:3])
        await b.close()


asyncio.run(main(sys.argv[1]))
