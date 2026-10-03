// mapstyle's dashboard (docs/design/dashboard.md) on roadstyle's report panel: a Modes box, and
// under each feature layer's box its clickable / tooltip / popup switches and its kinds. UI only,
// over rsSetModes, rsSetInteraction and rsSetKinds (layers.js). Without the report's panel
// (#rp-ovs) it falls back to a box in the page's corner.
(function wait(){
  if (!(window.rsSetKinds && window.RS_KINDS && rsQuery(() => true).length)) return setTimeout(wait, 200);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const fmt = (n) => n.toLocaleString();
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; return e; };
  const check = (text, on, change, count) => {
    const lab = el("label", "rp-chk"), cb = el("input");
    cb.type = "checkbox"; cb.checked = on; cb.onchange = () => change(cb.checked);
    lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + text));
    if (count != null) lab.appendChild(el("span", "rp-ct", fmt(count)));
    return lab;
  };
  document.head.appendChild(el("style", null,
    ".ms-grp{margin:0 0 10px;border:1px solid var(--line,#e5e7eb);border-radius:10px;padding:2px 10px 6px}" +
    ".ms-grp>summary{display:flex;align-items:center;gap:6px;cursor:pointer;font-size:11px;font-weight:600;" +
    "letter-spacing:.05em;text-transform:uppercase;color:var(--mut,#6b7280);padding:6px 0}" +
    ".ms-grp>summary .ms-n{font-weight:400;opacity:.7}.ms-grp>summary .ms-all{margin-left:auto;text-transform:none;letter-spacing:0;font-weight:400}" +
    ".ms-row{display:flex;flex-wrap:wrap;align-items:center}.ms-row>label{flex:1}.ms-set{flex-basis:100%;margin:0 0 4px 22px;font-size:12px}" +
    ".ms-gear{border:0;background:none;cursor:pointer;color:var(--mut,#9ca3af);font-size:13px;padding:0 4px;opacity:.7}.ms-gear:hover,.ms-gear.on{opacity:1}" +
    "#rp-kpis{display:grid!important;grid-template-columns:repeat(3,1fr);gap:6px}#rp-kpis .rp-kpi{padding:6px 8px;min-width:0}#rp-kpis .rp-kv{font-size:17px}" +
    ".ms-modes{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px}.ms-modes .rp-grp{flex-basis:100%;margin:2px 0 0}" +
    ".ms-modes .rp-chk{display:inline-flex;align-items:center;gap:4px;margin:0;padding:2px 9px;border:1px solid var(--line,#e5e7eb);border-radius:14px}" +
    ".ms-modes .rp-ct{margin-left:4px}" +
    "#rp-cls{max-height:260px;overflow-y:auto}#rp-cls .rp-grp{position:sticky;top:0;background:var(--bg,#fff);z-index:1;padding:2px 0}" +
    ".ms-sw{display:flex;gap:10px;margin:3px 0}.ms-sw label{cursor:pointer}" +
    ".ms-kinds{max-height:160px;overflow-y:auto}.ms-kinds .rp-chk{font-size:12px}" +
    ".ms-all{font-size:11px;margin:2px 0}.ms-all a{margin-right:8px;cursor:pointer;color:#555}" +
    ".ms-float{position:fixed;left:10px;bottom:30px;z-index:5;max-height:60vh;overflow-y:auto;" +
    "background:#fff;padding:8px 10px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);font:13px system-ui}"));
  // ---- a road cut into pieces is one edge: the report counts rows, so count the first piece only ---
  // (docs/design/levels_plan.md; the extra pieces carry _piece)
  (function recount(n) {
    const kv = [...document.querySelectorAll(".rp-kpi")].find((k) => /edges/.test(k.textContent));
    const wrap = document.getElementById("rp-cls");
    if (!kv || !wrap || !wrap.querySelector(".rp-ct")) return n > 0 && setTimeout(() => recount(n - 1), 300);
    const real = rsQuery((p) => !p._piece), props = rsGetProps(real), col = window.RS_CLASS_COL, cnt = {};
    props.forEach((p) => { const c = p[col]; if (c != null && c !== "") cnt[c] = (cnt[c] || 0) + 1; });
    kv.querySelector(".rp-kv").textContent = fmt(real.length);
    wrap.querySelectorAll("label.rp-chk").forEach((lab) => {
      const ct = lab.querySelector(".rp-ct"); if (!ct) return;
      ct.textContent = fmt(cnt[lab.textContent.replace(ct.textContent, "").trim()] || 0);
    });
  })(20);
  const ovs = document.getElementById("rp-ovs");
  const host = ovs ? ovs.parentNode : document.body.appendChild(el("div", "ms-float"));

  // ---- Modes: the roads any ticked mode can use ------------------------------------------------
  const modes = ["driving", "walking", "cycling"]
    .map((m) => [m, rsQuery((p) => !p._piece && (p[m] === true || p[m] === "true")).length]).filter(([, n]) => n);
  const on = new Set(modes.map(([m]) => m)), box = el("div", "ms-modes", '<div class="rp-grp">Modes</div>');
  for (const [m, n] of modes) box.appendChild(check(m, true, (c) => {
    c ? on.add(m) : on.delete(m);
    rsSetModes(on.size === modes.length ? null : [...on]);
  }, n));
  // the roads you may not use (private, bus): shown / hidden like a mode (layers.js rsSetAccess)
  for (const [k, label] of [["private", "private roads"], ["bus", "bus lanes"]])
    if ((window.RS_ACCESS || {})[k]) box.appendChild(check(label, true, (c) => rsSetAccess(k, c), RS_ACCESS[k]));
  host.insertBefore(box, ovs);

  // ---- popup off also keeps a layer out of the panel's read-out --------------------------------
  // the report fills #rp-detail from every rs:select, a road click listing the clickable layers
  // under it; this listener runs after the report's and redraws it (the report's own markup)
  // without the layers whose popup is off
  const detail = document.getElementById("rp-detail"), idle = detail && detail.innerHTML;
  const rowsOf = (p, only) => (only && only.length ? only : Object.keys(p))
    .filter((k) => k[0] !== "_" && k !== "lvl" && p[k] != null && p[k] !== "")
    .map((k) => "<b>" + esc(k) + "</b>: " + esc(p[k])).join("<br>");
  const popupOn = (label) => { const s = rsGetInteraction(label); return !s || s.popup; };
  if (detail) document.addEventListener("rs:select", (e) => {
    const d = e.detail;
    if (d.overlay) { if (!popupOn(d.overlay)) detail.innerHTML = idle; return; }
    const ovs = (d.overlays || []).filter((o) => popupOn(o.label));
    if (ovs.length === (d.overlays || []).length) return;
    detail.innerHTML = rowsOf(d.properties, d.fields) + ovs.map((o) =>
      '<hr style="border:none;border-top:1px solid var(--line);margin:6px 0"><span style="color:var(--mut)">'
      + esc(o.label) + "</span><br>" + rowsOf(o.properties, o.fields)).join("");
  });

  // ---- per layer: a row with a gear (switches and kinds), the layers grouped by meaning ---------
  // (docs/design/dashboard_panel.md)
  const GROUPS = [["Nature and water", ["ocean", "landcover", "institutional", "water", "waterways"]],
                  ["Buildings and places", ["buildings", "parking", "parking_p", "platform", "bus_station"]],
                  ["Transport", ["railways", "crossings", "traffic_signals", "bus_stations", "train_stations", "bicycle"]]];
  const grpOf = (label) => (GROUPS.find(([, l]) => l.includes(label)) || [])[0] || "Other";
  const rows = ovs ? [...ovs.querySelectorAll("label.rp-chk")] : [];
  const sets = {};                                  // layer -> its switches / kinds box
  for (const ov of window.RS_OVERLAYS || []) {
    const st = rsGetInteraction(ov.label); if (!st) continue;
    const d = el("div", "ms-set"), sw = el("div", "ms-sw"), cb = {};
    // a layer that isn't clickable opens no popup: its popup switch waits, greyed
    const grey = () => { const off = !cb.clickable.checked; cb.popup.disabled = off;
      cb.popup.parentNode.style.opacity = off ? 0.45 : 1; cb.popup.parentNode.title = off ? "needs clickable" : ""; };
    for (const k of ["clickable", "tooltip", "popup"]) {
      const lab = check(k, st[k], (c) => { rsSetInteraction(ov.label, {[k]: c}); grey(); });
      cb[k] = lab.querySelector("input"); sw.appendChild(lab);
    }
    grey();
    d.appendChild(sw);
    const counts = window.RS_KINDS[ov.label] || {}, names = Object.keys(counts);
    if (names.length > 1) {
      const shown = new Set(names), list = el("div", "ms-kinds"), cbs = {};
      const apply = () => rsSetKinds(ov.label, shown.size === names.length ? null : [...shown]);
      const all = el("div", "ms-all", "<a>all</a><a>none</a>");
      const setAll = (v) => { names.forEach((n) => { cbs[n].querySelector("input").checked = v; v ? shown.add(n) : shown.delete(n); }); apply(); };
      all.children[0].onclick = () => setAll(true);
      all.children[1].onclick = () => setAll(false);
      d.appendChild(all);
      for (const n of names) {
        cbs[n] = check(n, true, (c) => { c ? shown.add(n) : shown.delete(n); apply(); }, counts[n]);
        list.appendChild(cbs[n]);
      }
      d.appendChild(list);
    }
    sets[ov.label] = d;
  }
  const rowOf = (label) => rows.find((r) => r.textContent.trim() === label);
  const groups = new Map();
  for (const r of rows) {                           // the report's own rows, in its order, into their group
    const label = r.textContent.trim(), g = grpOf(label);
    if (!groups.has(g)) {
      const det = el("details", "ms-grp"), sum = el("summary", null, "<span>" + esc(g) + '</span><b class="ms-n"></b>');
      const all = el("span", "ms-all", "<a>all</a><a>none</a>");
      det.open = g !== "Other"; det.appendChild(sum); sum.appendChild(all);
      const setAll = (v) => (e) => { e.preventDefault(); for (const q of det.querySelectorAll(".ms-row > label input")) if (q.checked !== v) q.click(); };
      all.children[0].onclick = setAll(true); all.children[1].onclick = setAll(false);
      groups.set(g, det);
    }
    const det = groups.get(g), wrap = el("div", "ms-row"), set = sets[label];
    wrap.appendChild(r);
    if (set) {
      const gear = el("button", "ms-gear", "⚙"); gear.type = "button"; gear.title = "clicks, kinds";
      gear.onclick = () => { set.hidden = !set.hidden; gear.classList.toggle("on", !set.hidden); };
      set.hidden = true; wrap.appendChild(gear); wrap.appendChild(set);
    }
    det.appendChild(wrap);
  }
  const count = () => groups.forEach((det) => {
    const q = [...det.querySelectorAll(".ms-row > label input")];
    det.querySelector(".ms-n").textContent = q.filter((c) => c.checked).length + "/" + q.length;
  });
  if (ovs) {
    const head = ovs.querySelector(".rp-grp"); if (head) head.remove();      // "Layers": the groups say it
    // Roads first (modes, road types), then the layer groups
    const roads = el("details", "ms-grp"), cls = document.getElementById("rp-cls");
    roads.open = true; roads.appendChild(el("summary", null, "<span>Roads</span>"));
    roads.appendChild(box);
    if (cls) roads.appendChild(cls);
    ovs.before(roads);
    groups.forEach((det) => ovs.appendChild(det));
    ovs.addEventListener("change", count); count();
  } else for (const [, det] of groups) host.appendChild(det);

  // ---- the legend repeats Road type when roads are coloured by class: shown for the other colourings ---
  const co = document.getElementById("rp-co"), lg = document.getElementById("rp-legend");
  if (co && lg) {
    const legend = lg.closest("details"), roadType = () => (co.options[co.selectedIndex].text || "") === "Road class";
    const sync = () => { legend.hidden = roadType(); };
    co.addEventListener("change", sync); sync();
  }
})();
