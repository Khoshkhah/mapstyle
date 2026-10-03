"""Browser check for a route planner page (``mapstyle db --planner``), ported from duckOSM's
``scripts/route_map_stress.py``: for every choice in the mode menu, random trips between road
points at zoom 13.5 and 16 with both markers on screen, and at 17 with the end marker off screen;
prints how many routed and why the others didn't. Needs playwright (``pip install playwright &&
playwright install chromium``).

    python scripts/planner_check.py monaco_planner.html [trips per zoom, default 20]
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

JS = """async ([zoom, n, offscreen]) => {
  const ids = rsQuery(() => true), fs = map.getSource('roads')._data.features;
  const pt = () => { const c = fs[ids[Math.floor(Math.random() * ids.length)]].geometry.coordinates; return c[Math.floor(c.length / 2)]; };
  const out = {};
  for (let i = 0; i < n; i++) {
    const a = pt(), b = pt();
    map.jumpTo({center: offscreen ? a : [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], zoom});
    await new Promise((r) => map.once('idle', r));
    rmRoute(a, b);
    const t = document.getElementById('rm-result').innerText.split('\\n')[0];
    const key = (window.rmLast && window.rmLast.res && t.includes('·')) ? 'ok'
      : window.rmLast && window.rmLast.error ? 'no road within the radius' : t.slice(0, 50);
    out[key] = (out[key] || 0) + 1;
  }
  return out;
}"""


async def main(path, n):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1100, "height": 750})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + os.path.abspath(path))
        await pg.wait_for_function("window.rmLast && (window.rmLast.res || window.rmLast.error)", timeout=600000)
        await pg.wait_for_timeout(800)
        choices = await pg.evaluate("[...document.querySelectorAll('#rm-mode option')].map(o => o.text)")
        print(os.path.basename(path), "menu:", choices, "| note:", await pg.evaluate("document.getElementById('rm-note').innerText"))
        for i, label in enumerate(choices):
            await pg.click(f"#rm-modes button >> nth={i}")
            for zoom, off in [(13.5, False), (16, False), (17, True)]:
                print(f"  {label:13s} zoom {zoom:4}", "B off screen " if off else "both on screen",
                      await pg.evaluate(JS, [zoom, n, off]), flush=True)
        print("errors", errs[:2])
        await b.close()


asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 20))
