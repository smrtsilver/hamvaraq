/* شمارش تدریجی آمار صفحه‌ی اصلی؛ مقدار نهایی از سرور می‌آد و بدون JS هم درسته */
(function () {
  var els = document.querySelectorAll("[data-stat]");
  if (!els.length || HV.prefersReducedMotion() || !("IntersectionObserver" in window)) return;
  function run(el) {
    var end = parseInt(el.dataset.stat, 10), t0 = null, dur = 1200;
    if (!end) return;
    function step(t) {
      t0 = t0 || t;
      var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = HV.formatFaNumber(Math.round(end * e));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) { if (e.isIntersecting) { io.unobserve(e.target); run(e.target); } });
  }, { threshold: 0.4 });
  els.forEach(function (el) { io.observe(el); });
})();
