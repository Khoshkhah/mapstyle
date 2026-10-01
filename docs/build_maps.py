"""The site's live maps (docs/maps/*.html), from a duckOSM db of Monaco. CI builds the db with
duckOSM's sample (data/sample/monaco.osm.pbf, sea included) and runs this before `mkdocs build`:

    python docs/build_maps.py monaco.duckdb

The maps are not committed (.gitignore): each is a ~3-5 MB self-contained page.
"""
import sys
from pathlib import Path

import mapstyle as ms

DB = sys.argv[1]
OUT = Path(__file__).parent / "maps"

MAPS = {
    "all": dict(),
    "driving": dict(mode="driving"),
    "walking": dict(mode="walking"),
    "cycling": dict(mode="cycling"),
    "paths_osm": dict(paths="osm"),
    "paths_komoot": dict(mode="walking", paths="komoot"),
    "dashboard": dict(dashboard=True),
    "planner": dict(planner=True),
    "theme_google": dict(theme="google"),
    "theme_grey": dict(theme="grey"),
}

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, opts in MAPS.items():
        ms.render_map(DB, **opts).save(str(OUT / f"{name}.html"))
        print(f"docs/maps/{name}.html  {(OUT / f'{name}.html').stat().st_size / 1e6:.1f} MB")
