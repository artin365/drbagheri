(() => {
  const r = document.documentElement, b = document.getElementById("theme");
  const dark = () => r.dataset.theme ? r.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  const icon = () => { b.textContent = dark() ? "☀" : "☾"; };
  b.onclick = () => {
    const t = dark() ? "light" : "dark";
    r.dataset.theme = t;
    try { localStorage.setItem("theme", t); } catch (e) {}
    icon();
  };
  icon();
})();
