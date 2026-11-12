(() => {
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const R = $("#exam"), csrf = R.dataset.csrf, U = JSON.parse(R.dataset.urls);
  const saved = JSON.parse($("#saved").textContent);
  const total = +R.dataset.left, end = performance.now() + total * 1000;
  const fa = n => String(n).replace(/\d/g, d => "۰۱۲۳۴۵۶۷۸۹"[d]);
  const qs = $$(".q"), dots = $$(".dot");
  let cur = 0, closed = false, lastV = 0;

  const post = (u, b) => fetch(u, {method: "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json", "X-CSRFToken": csrf}, body: JSON.stringify(b || {})})
    .then(async r => ({s: r.status, d: await r.json().catch(() => ({}))}));
  const leave = () => { closed = true; window.onbeforeunload = null; location.href = U.result; };

  function show(i) {
    cur = i;
    qs.forEach((q, k) => q.hidden = k !== i);
    dots.forEach((d, k) => d.classList.toggle("cur", k === i));
    $("#prev").disabled = i === 0; $("#next").disabled = i === qs.length - 1;
  }
  function mark(qid, cid) {
    $$(`.opt[data-q="${qid}"]`).forEach(o => o.classList.toggle("sel", o.dataset.c === String(cid)));
    $(`.dot[data-qid="${qid}"]`).classList.add("done");
  }
  Object.entries(saved).forEach(([q, c]) => mark(q, c));

  $$(".opt").forEach(o => o.onclick = async () => {
    mark(o.dataset.q, o.dataset.c);
    const {s} = await post(U.answer, {question: +o.dataset.q, choice: +o.dataset.c});
    if (s === 409) leave();
    else if (s !== 200) alert("پاسخ ذخیره نشد. اتصال را بررسی و دوباره انتخاب کنید.");
  });
  dots.forEach(d => d.onclick = () => show(+d.dataset.i));
  $("#prev").onclick = () => show(cur - 1);
  $("#next").onclick = () => show(cur + 1);
  const submit = async () => { await post(U.submit); leave(); };
  $("#finish").onclick = () => {
    const miss = qs.length - $$(".dot.done").length;
    if (!miss || confirm(fa(miss) + " سؤال بی‌پاسخ است. آزمون نهایی شود؟")) submit();
  };

  setInterval(() => {  // نمایش زمان؛ مرجع واقعی ساعت سرور است
    const left = Math.max(0, Math.round((end - performance.now()) / 1000));
    const t = $("#timer");
    t.textContent = fa(String(Math.floor(left / 60)).padStart(2, "0")) + ":" + fa(String(left % 60).padStart(2, "0"));
    t.classList.toggle("low", left < 60);
    $("#bar").style.width = (left / total * 100) + "%";
    if (left === 0 && !closed) submit();
  }, 250);

  async function violate(kind) {
    const now = Date.now();
    if (closed || now - lastV < 1500) return;
    lastV = now;
    const {d} = await post(U.violation, {kind});
    if (d.closed) return leave();
    $("#warnmsg").textContent = `خروج از صفحهٔ آزمون ثبت شد. تخلف ${fa(d.violations)} از ${fa(d.max)}. با رسیدن به سقف، آزمون بسته می‌شود.`;
    $("#warn").hidden = false;
  }
  $("#ok").onclick = () => $("#warn").hidden = true;
  document.addEventListener("visibilitychange", () => document.hidden && violate("tab_hidden"));
  window.addEventListener("blur", () => setTimeout(() => !document.hidden && violate("window_blur"), 200));
  ["copy", "cut", "paste"].forEach(ev => document.addEventListener(ev, e => { e.preventDefault(); violate("copy_paste"); }));
  document.addEventListener("contextmenu", e => e.preventDefault());
  window.onbeforeunload = e => { e.preventDefault(); e.returnValue = ""; };

  show(0);
  const kx = () => window.renderMathInElement && renderMathInElement(R, {delimiters: [{left: "$$", right: "$$", display: true}, {left: "$", right: "$", display: false}]});
  window.addEventListener("load", kx);
})();
