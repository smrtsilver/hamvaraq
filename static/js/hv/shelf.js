/* قفسه‌ی افقی: دکمه‌های قبلی/بعدی (راست‌به‌چپ؛ scrollBy در RTL مقدار منفی می‌گیره) */
(function () {
  document.querySelectorAll("[data-shelf]").forEach(function (sh) {
    var track = sh.querySelector(".hv-shelf-track"), nav = sh.querySelector(".shelf-nav");
    function go(dir) {
      var rtl = getComputedStyle(track).direction === "rtl";
      track.scrollBy({ left: dir * (rtl ? -1 : 1) * track.clientWidth * 0.85, behavior: HV.prefersReducedMotion() ? "auto" : "smooth" });
    }
    var n = sh.querySelector("[data-shelf-next]"), p = sh.querySelector("[data-shelf-prev]");
    n.addEventListener("click", function () { go(-1); });
    p.addEventListener("click", function () { go(1); });
    function fit() { nav.classList.toggle("no-scroll", track.scrollWidth <= track.clientWidth + 2); }
    fit(); addEventListener("resize", HV.debounce(fit, 150));
  });
})();
