(() => {
  const $ = s => document.querySelector(s);
  document.querySelectorAll("table[data-table]").forEach(t => {
    const body = t.tBodies[0], rows = [...body.rows], q = $("#q"), st = $("#st"), cnt = $("#cnt");
    const apply = () => {
      const s = (q ? q.value : "").trim().toLowerCase(), f = st ? st.value : "";
      let n = 0;
      rows.forEach(r => { const ok = (!s || r.textContent.toLowerCase().includes(s)) && (!f || r.dataset.status === f); r.hidden = !ok; n += ok; });
      if (cnt) cnt.textContent = n;
    };
    if (q) q.addEventListener("input", apply);
    if (st) st.addEventListener("change", apply);
    t.querySelectorAll("th[data-k]").forEach(th => {
      let asc = true;
      th.onclick = () => {
        const k = th.cellIndex, val = r => r.cells[k].dataset.v ?? r.cells[k].textContent.trim();
        rows.sort((a, b) => {
          const x = val(a), y = val(b), nx = parseFloat(x), ny = parseFloat(y);
          const c = isNaN(nx) || isNaN(ny) ? x.localeCompare(y, "fa") : nx - ny;
          return asc ? c : -c;
        });
        asc = !asc;
        rows.forEach(r => body.appendChild(r));
      };
    });
    apply();
  });
  // انتخاب همه (جدول یا کارت‌ها) و شمارندهٔ انتخاب‌شده‌ها
  const all = $("#all"), sel = $("#sel"), picks = () => [...document.querySelectorAll(".pick")];
  const bar = $("#bulkbar");
  const count = () => { const n = picks().filter(c => c.checked).length; if (sel) sel.textContent = n; if (bar) bar.hidden = !n; };
  if (all) all.onchange = () => { picks().forEach(c => { const r = c.closest("tr"); if (!r || !r.hidden) c.checked = all.checked; }); count(); };
  document.addEventListener("change", e => { if (e.target.classList && e.target.classList.contains("pick")) count(); });
  count();
  // فیلدهایی که فقط با مقدار مشخصی از یک فیلد دیگر نمایش داده می‌شوند: data-show-if="#id=value"
  document.querySelectorAll("[data-show-if]").forEach(box => {
    const [sl, v] = box.dataset.showIf.split("="), src = $(sl);
    if (!src) return;
    const upd = () => { box.hidden = src.value !== v; };
    src.addEventListener("change", upd);
    upd();
  });
})();
