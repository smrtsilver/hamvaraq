/* حالت‌های سیستم به‌صورت زنده: کاهش حرکت و تیره/روشن (تا وقتی کاربر خودش انتخاب نکرده) */
(function () {
  var root = document.documentElement;
  function motion() { root.toggleAttribute("data-reduced-motion", HV.prefersReducedMotion()); }
  function theme() {
    var stored = null;
    try { stored = localStorage.getItem("hv-theme"); } catch (e) {}
    var dark = stored ? stored === "dark" : HV.prefersDark();
    document.querySelectorAll("[data-theme-toggle] use").forEach(function (u) { u.setAttribute("href", dark ? "#i-sun" : "#i-moon"); });
  }
  [["(prefers-reduced-motion: reduce)", motion], ["(prefers-color-scheme: dark)", theme]].forEach(function (p) {
    var m = matchMedia(p[0]);
    m.addEventListener ? m.addEventListener("change", p[1]) : m.addListener(p[1]);
  });
  motion();
})();
