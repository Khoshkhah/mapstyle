"""The docs' pictures (docs/img/*.jpg), from real mapstyle pages of Monaco. Run by hand when the look
changes (needs playwright + chromium):

    python docs/build_images.py monaco.duckdb

The live maps on the site are built in CI instead (docs/build_maps.py).
"""
import asyncio
import io
import sys
import tempfile
from pathlib import Path

from PIL import Image

import mapstyle as ms

DB = sys.argv[1]
ONLY = set(sys.argv[2:])          # optional: just these pictures
OUT = Path(__file__).parent / "img"
HIDE = (".maplibregl-ctrl-top-left,.maplibregl-ctrl-top-right,.rs-tl,.flt-ctrl,.ov-ctrl,"
        ".maplibregl-ctrl-bottom-left,.maplibregl-ctrl-bottom-right{display:none!important}")
IDLE = ("() => new Promise(r => { const t = setTimeout(r, 6000);"
        " map.once('idle', () => { clearTimeout(t); r(); }); map.triggerRepaint(); })")

# name: (page options, lon, lat, zoom, (width, height), hide the controls)
SHOTS = {
    "hero": (dict(), 7.4262, 43.7392, 15.55, (1600, 900), True),
    "mode_all": (dict(), 7.4290, 43.7418, 16.4, (900, 600), True),
    "mode_driving": (dict(mode="driving"), 7.4290, 43.7418, 16.4, (900, 600), True),
    "mode_walking": (dict(mode="walking"), 7.4290, 43.7418, 16.4, (900, 600), True),
    "mode_cycling": (dict(mode="cycling"), 7.4290, 43.7418, 16.4, (900, 600), True),
    "paths_google": (dict(mode="walking"), 7.4298, 43.7437, 17.6, (900, 600), True),
    "paths_osm": (dict(mode="walking", paths="osm"), 7.4298, 43.7437, 17.6, (900, 600), True),
    "paths_komoot": (dict(mode="walking", paths="komoot"), 7.4298, 43.7437, 17.6, (900, 600), True),
    "paths_cyclosm": (dict(mode="walking", paths="cyclosm"), 7.4298, 43.7437, 17.6, (900, 600), True),
    "layers_port": (dict(), 7.4262, 43.7394, 17.6, (900, 600), True),
    "layers_coast": (dict(), 7.4205, 43.7335, 14.2, (900, 600), True),
    "roads_tunnel": (dict(), 7.411338, 43.731241, 18.0, (900, 600), True),
    "roads_walkway": (dict(), 7.4171, 43.7318, 18.0, (900, 600), True),
    "roads_crossings": (dict(), 7.430688, 43.745301, 18.2, (900, 600), True),
    "dashboard": (dict(dashboard=True), 7.4215, 43.7362, 15.4, (1600, 900), False),
    "planner": (dict(planner=True), None, None, None, (1600, 900), False),
}


async def main():
    from playwright.async_api import async_playwright
    OUT.mkdir(exist_ok=True)
    pages = {}
    with tempfile.TemporaryDirectory() as tmp:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            for name, (opts, lon, lat, z, (w, h), hide) in SHOTS.items():
                if ONLY and name not in ONLY:
                    continue
                key = tuple(sorted(opts.items()))
                if key not in pages:
                    pages[key] = Path(tmp) / f"p{len(pages)}.html"
                    ms.render_map(DB, **opts).save(str(pages[key]))
                pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
                await pg.goto(pages[key].as_uri())
                await pg.wait_for_function("window.map && map.isStyleLoaded && map.isStyleLoaded()"
                                           " && window.rsQuery && rsQuery(() => true).length", timeout=120000)
                await pg.wait_for_function("window.RS_KINDS !== undefined", timeout=60000)
                if hide:
                    await pg.add_style_tag(content=HIDE)
                if z is not None:
                    await pg.evaluate(f"() => {{ map.jumpTo({{center: [{lon}, {lat}], zoom: {z}}}); }}")
                await pg.evaluate(IDLE)
                await pg.wait_for_timeout(800)
                img = Image.open(io.BytesIO(await pg.screenshot())).convert("RGB")
                img.save(OUT / f"{name}.jpg", quality=86, optimize=True, progressive=True)
                await pg.close()
                print(name, img.size)
            await b.close()


asyncio.run(main())
