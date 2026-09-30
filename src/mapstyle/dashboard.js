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
    ".ms-layer{margin:0 0 4px 22px;font-size:12px}.ms-layer summary{cursor:pointer;color:#666}" +
    ".ms-sw{display:flex;gap:10px;margin:3px 0}.ms-sw label{cursor:pointer}" +
    ".ms-kinds{max-height:160px;overflow-y:auto}.ms-kinds .rp-chk{font-size:12px}" +
    ".ms-all{font-size:11px;margin:2px 0}.ms-all a{margin-right:8px;cursor:pointer;color:#555}" +
    ".ms-float{position:fixed;left:10px;bottom:30px;z-index:5;max-height:60vh;overflow-y:auto;" +
    "background:#fff;padding:8px 10px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);font:13px system-ui}"));
  const ovs = document.getElementById("rp-ovs");
  const host = ovs ? ovs.parentNode : document.body.appendChild(el("div", "ms-float"));

  // ---- Modes: the roads any ticked mode can use ------------------------------------------------
  const modes = ["driving", "walking", "cycling"]
    .map((m) => [m, rsQuery((p) => p[m] === true || p[m] === "true").length]).filter(([, n]) => n);
  const on = new Set(modes.map(([m]) => m)), box = el("div", null, '<div class="rp-grp">Modes</div>');
  for (const [m, n] of modes) box.appendChild(check(m, true, (c) => {
    c ? on.add(m) : on.delete(m);
    rsSetModes(on.size === modes.length ? null : [...on]);
  }, n));
  host.insertBefore(box, ovs);

  // ---- per layer: switches and kinds -----------------------------------------------------------
  const rows = ovs ? [...ovs.querySelectorAll("label.rp-chk")] : [];
  for (const ov of window.RS_OVERLAYS || []) {
    const st = rsGetInteraction(ov.label); if (!st) continue;
    const d = el("details", "ms-layer", "<summary>clicks, kinds</summary>");
    const sw = el("div", "ms-sw");
    for (const k of ["clickable", "tooltip", "popup"])
      sw.appendChild(check(k, st[k], (c) => rsSetInteraction(ov.label, {[k]: c})));
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
    const row = rows.find((r) => r.textContent.trim() === ov.label);
    if (row) row.after(d);
    else { host.appendChild(el("div", "rp-grp", esc(ov.label))); host.appendChild(d); }
  }
})();
