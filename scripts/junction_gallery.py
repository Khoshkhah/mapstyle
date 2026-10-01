"""A gallery of every kind of road junction and road end, for judging how a map draws them.

1. Finds the cases in a duckOSM db (one row per case: kind, node, edges, coordinates), plus the
   edges Kaveh reported, and writes them to ``cases.json``.
2. Screenshots each case from one page (a map built by mapstyle / roadstyle): one page load,
   then jump to each case.
3. Writes ``index.html``: the screenshots with their kind and edge_ids, a check box and a note per
   case (kept in the browser), and a button that copies the marks to paste back.

Run it again on another page to get "after" pictures of the same cases::

    python scripts/junction_gallery.py DB PAGE OUT_DIR [--label before]

Needs playwright. Everything is read only.
"""
import argparse
import asyncio
import json
import math
import os
from collections import defaultdict

REPORTED = {   # edges Kaveh reported on 2026-09-30, with what he said
    "4628183342609875807": "link over street (Avenue de la Costa / Bretelle Ostende)",
    "6471016024852816111": "link over street (Avenue de la Costa)",
    "284593073383310203": "link over street (Avenue de la Costa)",
    "9144234404296452426": "overlap with the pedestrian square outline",
    "8228482316931532933": "pedestrian square outline drawn as a street",
    "7541936896269179755": "a road connected to it could not be clicked",
    "4632831168260494548": "connection (Avenue des Spélugues)",
    "3506361516268757248": "connection (Avenue Princesse Grace)",
    "9057315353055030859": "connection (Allées des Boulingrins)",
    "7241999400775147456": "connection (Boulevard des Moulins)",
    "2044305374183025658": "connection (Avenue de la Costa)",
    "441704187184649227": "twin end shape (Rue du Castelleretto)",
    "5990211243552773545": "looks like a dead end at its tunnel (Rue du Castelleretto)",
    "4146834466225551101": "casing at the end point (Rue du Castelleretto tunnel)",
    "7910395095814073287": "casing at the end point (Rue du Castelleretto tunnel)",
    "2569262511564654469": "tunnel ends look like an ordinary road",
    "5645184677067318427": "crossing not split at the road it crosses",
    "6583882243050388082": "crossing and avenue not connected",
}
PATHS = ("footway", "path", "cycleway", "steps", "pedestrian", "bridleway", "corridor")
RANK = {c: i for i, c in enumerate(("motorway", "trunk", "primary", "secondary", "tertiary",
                                    "unclassified", "residential", "living_street", "service"))}
PER_KIND = 3


def _truthy(v):
    return str(v).lower() in ("yes", "true", "1", "-1")


def find_cases(db):
    import duckdb
    from mapstyle.map import _is_directed, load_roads

    g = load_roads(db)
    con = duckdb.connect(str(db), read_only=True)
    jn = {}
    for m in ("driving", "walking", "cycling"):
        try:
            for e, j in con.execute(f"SELECT CAST(edge_id AS VARCHAR), junction FROM {m}.edges").fetchall():
                jn.setdefault(e, j)
        except duckdb.Error:
            pass
    g["junction"] = g["edge_id"].map(jn)
    g["dirn"] = _is_directed(g)
    key = lambda c: (round(c[0], 6), round(c[1], 6))                    # noqa: E731
    E = []
    for r in g.itertuples():
        c = list(r.geometry.coords)
        try:
            ly = int(float(r.layer))
        except (TypeError, ValueError):
            ly = 0
        br, tu = _truthy(r.bridge), _truthy(r.tunnel)
        E.append(dict(id=r.edge_id, hw=r.highway or "", name=r.name or "", wt=r.walk_type, a=key(c[0]),
                      b=key(c[-1]), c=c, lvl=ly or (1 if br else -1 if tu else 0), br=br, tu=tu,
                      dirn=bool(r.dirn), road=(r.highway or "") not in PATHS,
                      rb=r.junction in ("roundabout", "circular"), drive=bool(r.driving)))
    dirs = {(e["a"], e["b"]) for e in E if e["dirn"]}
    for e in E:                    # two lanes: directed, and so is its reverse edge (roadstyle's rule)
        e["two"] = e["dirn"] and (e["b"], e["a"]) in dirs
    at = defaultdict(list)
    for i, e in enumerate(E):
        at[e["a"]].append(i)
        at[e["b"]].append(i)

    def segs(n):   # the physical segments at a node: twins (same line, reversed) count once
        seen, out = set(), []
        for i in at[n]:
            k = frozenset((E[i]["a"], E[i]["b"])), round(len(E[i]["c"]))
            if k not in seen:
                seen.add(k)
                out.append(i)
        return out

    def bearing(i, n):   # from the node into the edge, ~15 m along
        c = E[i]["c"] if E[i]["a"] == n else E[i]["c"][::-1]
        x0, y0 = c[0]
        kx = math.cos(math.radians(y0)) * 111320
        for x, y in c[1:]:
            if math.hypot((x - x0) * kx, (y - y0) * 111320) >= 15:
                break
        return math.degrees(math.atan2((x - x0) * kx, (y - y0) * 111320))

    cases = defaultdict(list)

    def add(kind, n, ids, note=""):
        cases[kind].append(dict(kind=kind, lon=n[0], lat=n[1], edges=[E[i]["id"] for i in ids], note=note))

    for n in at:
        S = segs(n)
        roads = [i for i in S if E[i]["road"]]
        lv = {E[i]["lvl"] for i in S}
        if any(E[i]["tu"] for i in S) and any(E[i]["lvl"] == 0 and E[i]["road"] for i in S):
            add("tunnel mouth", n, S)
        if any(E[i]["br"] for i in S) and any(E[i]["lvl"] == 0 and E[i]["road"] for i in S):
            add("bridge end", n, S)
        if any(E[i]["lvl"] != 0 and not E[i]["br"] and not E[i]["tu"] for i in S) and 0 in lv:
            add("plain layer change (layer tag, no bridge / tunnel)", n, S)
        if any(E[i]["rb"] for i in S) and any(not E[i]["rb"] and E[i]["road"] for i in S):
            add("roundabout entry", n, S)
        if len(S) == 1 and E[S[0]]["road"]:
            add("dead end, two-way road" if E[S[0]]["two"] else "dead end, one-way road", n, S)
        if len(roads) == 2 and len(S) == 2:
            a, b = (E[i] for i in roads)
            if a["hw"].endswith("_link") != b["hw"].endswith("_link"):
                add("road meets its link end to end", n, roads)
            elif a["two"] != b["two"]:
                add("two-way becomes one-way", n, roads)
            elif a["hw"] != b["hw"]:
                add("road continues, class changes", n, roads)
            else:
                add("road continues, same class", n, roads)
            d = abs((bearing(roads[0], n) - bearing(roads[1], n) + 180) % 360 - 180)
            if d < 35:
                add("sharp V (two roads under 35°)", n, roads)
        if len(roads) == 3:
            cls = {E[i]["hw"] for i in roads}
            if any(E[i]["hw"].endswith("_link") for i in roads):
                add("link leaves / joins a road", n, roads)
            elif sum(not E[i]["two"] for i in roads) == 2 and len(cls) == 1:
                add("dual carriageway split (two-way into two one-ways)", n, roads)
            elif len(cls) == 1:
                add("T junction, same class", n, roads)
            else:
                add("T junction, different classes", n, roads)
        if len(roads) == 4:
            add("X junction", n, roads)
        foot = [i for i in S if not E[i]["road"]]
        if roads and foot:
            if any(E[i]["wt"] == "crossing" for i in foot):
                add("crossing meets its road", n, S)
            elif any(E[i]["wt"] == "sidewalk" for i in foot):
                add("sidewalk meets a road", n, S)
            elif any(E[i]["hw"] == "steps" for i in foot):
                add("steps meet a road", n, S)
            elif any(E[i]["wt"] == "plaza" for i in foot):
                add("pedestrian square outline meets a road", n, S)
            else:
                add("footway ends at a road", n, S)

    # data cases: a path way not cut at a node the road network uses; a one-way street's walking reverse
    try:
        for osm_id, n_id, lon, lat in con.execute("""
            WITH w AS (SELECT DISTINCT osm_id FROM walking.edges WHERE highway IN ('footway','path','cycleway','steps','pedestrian','bridleway','corridor')),
                 inner_nodes AS (SELECT w.osm_id, unnest(r.refs[2:len(r.refs)-1]) n FROM w JOIN raw.ways r ON r.osm_id = w.osm_id),
                 ends AS (SELECT source n FROM walking.edges UNION SELECT target FROM walking.edges)
            SELECT i.osm_id, i.n, nd.lon, nd.lat FROM inner_nodes i JOIN main.global_junctions g ON g.node_id = i.n
            JOIN raw.nodes nd ON nd.osm_id = i.n WHERE i.n NOT IN (SELECT n FROM ends)""").fetchall():
            ids = [e["id"] for e in E if abs(e["c"][0][0] - lon) + abs(e["c"][0][1] - lat) < 0.0003][:4]
            cases["path not cut where it meets a road (data)"].append(
                dict(kind="path not cut where it meets a road (data)", lon=lon, lat=lat, edges=ids,
                     note=f"OSM way {osm_id}, node {n_id}"))
    except duckdb.Error:
        pass
    for i, e in enumerate(E):
        if e["road"] and not e["two"] and not e["drive"]:
            rev = [j for j in at[e["a"]] if E[j]["a"] == e["b"] and E[j]["b"] == e["a"] and E[j]["drive"]]
            if rev:
                m = e["c"][len(e["c"]) // 2]
                cases["one-way street with a walking-only reverse edge"].append(
                    dict(kind="one-way street with a walking-only reverse edge", lon=m[0], lat=m[1],
                         edges=[e["id"], E[rev[0]]["id"]]))
    con.close()

    # pick a few per kind: the most important roads first, spread over the map
    out = []
    for kind, cs in sorted(cases.items()):
        def imp(c):
            rk = [RANK.get(next((e["hw"] for e in E if e["id"] == x), ""), 20) for x in c["edges"][:3]]
            return (min(rk) if rk else 20, c["lon"], c["lat"])
        picked, used = [], []
        for c in sorted(cs, key=imp):
            if all(abs(c["lon"] - u[0]) + abs(c["lat"] - u[1]) > 0.003 for u in used):
                picked.append({**c, "count": len(cs)})
                used.append((c["lon"], c["lat"]))
            if len(picked) == PER_KIND:
                break
        out += picked
    byid = {e["id"]: e for e in E}
    for eid, said in REPORTED.items():
        e = byid.get(eid)
        if e is None:
            out.append(dict(kind="reported by Kaveh", lon=None, lat=None, edges=[eid],
                            note=f"{said} (edge not in this build: split since)"))
        else:
            m = e["c"][len(e["c"]) // 2]
            out.append(dict(kind="reported by Kaveh", lon=m[0], lat=m[1], edges=[eid],
                            note=f"{said}: {e['hw']} {e['name']}".strip()))
    return out


async def shoot(page, cases, out_dir, label, zoom, workers=10):
    """One fresh page per case, ``workers`` browsers at a time."""
    from playwright.async_api import async_playwright
    todo = []
    for i, c in enumerate(cases):               # resume: a picture already taken is kept
        f = f"{label}_{i:03d}.png"
        if os.path.exists(os.path.join(out_dir, f)):
            c.setdefault("img", {})[label] = f
        elif c["lon"] is not None:
            todo.append((i, c))
    done = [0]

    async def one(b, i, c):
        pg = await b.new_page(viewport={"width": 520, "height": 380})
        try:
            await pg.goto("file://" + os.path.abspath(page))
            await pg.wait_for_function("window.map && map.isStyleLoaded && map.isStyleLoaded() && "
                                       "window.rsQuery && rsQuery(() => true).length", timeout=300000)
            await pg.add_style_tag(content=".maplibregl-ctrl-top-left,.maplibregl-ctrl-top-right,.rs-tl,"
                                           ".flt-ctrl,.ov-ctrl,#rp,#sb,#rp-show,#sb-show{display:none!important}")
            await pg.evaluate(f"() => {{ map.jumpTo({{center: [{c['lon']}, {c['lat']}], zoom: {zoom}}}); }}")   # no return: the Map object is ~85 MB to Python
            await pg.evaluate("() => new Promise(r => { const t = setTimeout(r, 4000); "
                              "map.once('idle', () => { clearTimeout(t); r(); }); map.triggerRepaint(); })")
            await pg.wait_for_timeout(300)
            c.setdefault("img", {})[label] = f"{label}_{i:03d}.png"
            await pg.screenshot(path=os.path.join(out_dir, c["img"][label]))
        finally:
            await pg.close()
        done[0] += 1
        print(f"{done[0]}/{len(todo)} {c['kind']}", flush=True)

    async def worker(queue):
        async with async_playwright() as p:
            b = await p.chromium.launch()
            while queue:
                i, c = queue.pop(0)
                try:
                    await one(b, i, c)
                except Exception as e:
                    print(f"case {i + 1} failed: {str(e)[:120]}", flush=True)
            await b.close()

    queue = list(todo)
    await asyncio.gather(*(worker(queue) for _ in range(min(workers, len(todo)))))


HTML = """<!doctype html><meta charset="utf-8"><title>Junction gallery</title>
<style>
body{font:14px system-ui,sans-serif;margin:16px;color:#222;background:#fafafa}
h1{font-size:20px;margin:0 0 4px}.hint{color:#555;margin:0 0 12px;max-width:900px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px}
.case{background:#fff;border:1px solid #ddd;border-radius:6px;padding:8px}
.case.bad{border-color:#d33;box-shadow:0 0 0 2px #f7c6c6}
.case img{width:100%;border:1px solid #eee}.imgs{display:flex;gap:4px}.imgs figure{margin:0;flex:1}
.imgs figcaption{font-size:11px;color:#777}
.k{font-weight:600}.e{font:11px monospace;color:#444;word-break:break-all;user-select:all}.n{color:#555;font-size:12px}
.m{display:flex;gap:6px;align-items:center;margin-top:6px}.m input[type=text]{flex:1;font:inherit;padding:3px}
#bar{position:sticky;top:0;background:#fafafa;padding:6px 0;z-index:2}button{font:inherit;padding:4px 10px}
</style>
<div id="bar"><h1>Junction gallery</h1>
<p class="hint">Every kind of junction and road end, a few real examples each, and every edge you reported.
Tick <b>wrong</b> on the ones that look wrong and add a word on what; then <button id="copy">Copy my marks</button>
and paste them to Claude. Marks are kept in this browser. <span id="st"></span></p></div>
<div class="grid" id="g"></div>
<script>
const CASES = __CASES__, LABELS = __LABELS__, KEY = "junction-gallery-marks";
let marks = {}; try { marks = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(marks)); } catch (e) {} };
const g = document.getElementById("g");
CASES.forEach((c, i) => {
  const d = document.createElement("div"); d.className = "case";
  const imgs = LABELS.filter(l => c.img && c.img[l]).map(l =>
    `<figure><img loading="lazy" src="${c.img[l]}"><figcaption>${l}</figcaption></figure>`).join("");
  d.innerHTML = `<div class="k">${i + 1}. ${c.kind}${c.count ? ` <span class="n">(${c.count} in the map)</span>` : ""}</div>
    <div class="n">${c.note || ""} ${c.lon != null ? `· ${c.lon.toFixed(5)}, ${c.lat.toFixed(5)}` : ""}</div>
    <div class="imgs">${imgs || "<i>no picture: not in this build</i>"}</div>
    <div class="e">${c.edges.join(" ")}</div>
    <div class="m"><label><input type="checkbox"> wrong</label><input type="text" placeholder="what's wrong"></div>`;
  const cb = d.querySelector("input[type=checkbox]"), tx = d.querySelector("input[type=text]"), m = marks[i] || {};
  cb.checked = !!m.bad; tx.value = m.note || ""; d.classList.toggle("bad", cb.checked);
  cb.onchange = () => { marks[i] = {...(marks[i] || {}), bad: cb.checked}; d.classList.toggle("bad", cb.checked); save(); };
  tx.oninput = () => { marks[i] = {...(marks[i] || {}), note: tx.value}; save(); };
  g.appendChild(d);
});
document.getElementById("copy").onclick = () => {
  const lines = CASES.map((c, i) => [i, c, marks[i] || {}]).filter(([, , m]) => m.bad || m.note)
    .map(([i, c, m]) => `${i + 1}. ${m.bad ? "WRONG" : "ok"} | ${c.kind} | ${c.edges.slice(0, 4).join(" ")} | ${m.note || ""}`);
  const t = lines.join("\\n") || "(nothing marked)";
  (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(
    () => document.getElementById("st").textContent = `copied ${lines.length} marks`,
    () => { prompt("Copy this:", t); });
};
</script>
"""


def write_html(cases, out_dir):
    labels = sorted({l for c in cases for l in (c.get("img") or {})}, key=lambda l: (l != "before", l))
    html = (HTML.replace("__CASES__", json.dumps(cases).replace("</", "<\\/"))
            .replace("__LABELS__", json.dumps(labels)))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("db"), ap.add_argument("page"), ap.add_argument("out_dir")
    ap.add_argument("--label", default="now", help="picture label (e.g. before / after)")
    ap.add_argument("--zoom", type=float, default=18.5)
    ap.add_argument("--workers", type=int, default=10, help="browsers in parallel")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    path = os.path.join(a.out_dir, "cases.json")
    if os.path.exists(path):                      # same cases for before and after
        cases = json.load(open(path))
    else:
        cases = find_cases(a.db)
    for i, c in enumerate(cases):               # the page works from the start, with what exists
        if os.path.exists(os.path.join(a.out_dir, f"{a.label}_{i:03d}.png")):
            c.setdefault("img", {})[a.label] = f"{a.label}_{i:03d}.png"
    json.dump(cases, open(path, "w"), indent=1)
    write_html(cases, a.out_dir)
    asyncio.run(shoot(a.page, cases, a.out_dir, a.label, a.zoom, a.workers))
    json.dump(cases, open(path, "w"), indent=1)
    write_html(cases, a.out_dir)
    print(f"{len(cases)} cases -> {os.path.join(a.out_dir, 'index.html')}")


if __name__ == "__main__":
    main()
