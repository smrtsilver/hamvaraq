/* ظاهر شدن نرم بخش‌ها هنگام اسکرول + «ادامه‌ی متن» برای نوشته‌های بلند (بدون کتابخانه‌ی خارجی) */
(function () {
  document.querySelectorAll(".rich[data-long]").forEach(function (el) {
    el.classList.add("is-clamped");
    var b = document.createElement("button");
    b.type = "button"; b.className = "btn btn-secondary btn-sm rich-more"; b.textContent = "ادامه‌ی نوشته";
    b.setAttribute("aria-expanded", "false");
    b.addEventListener("click", function () { el.classList.remove("is-clamped"); b.remove(); });
    el.after(b);
  });
  if (HV.prefersReducedMotion() || !("IntersectionObserver" in window)) return;
  var vh = innerHeight;
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
  }, { rootMargin: "0px 0px -8% 0px" });
  document.querySelectorAll("main .section-sm, main .lp-section .how-step, main .feature, main .event-list .event-card, main .post-grid .post-card").forEach(function (el) {
    if (el.getBoundingClientRect().top < vh) return;       // بالای صفحه بدون تأخیر دیده بشه
    el.classList.add("reveal"); io.observe(el);
  });
})();

/* فیلتر تاشو روی موبایل: فرم‌های data-fold تو یه <details> می‌رن؛ اگه فیلتری فعاله باز می‌مونه */
(function () {
  if (!matchMedia("(max-width: 640px)").matches) return;
  document.querySelectorAll("form[data-fold]").forEach(function (form) {
    var q = new URLSearchParams(location.search), n = 0;
    q.forEach(function (v, k) { if (v && !/^(page|tab|sort)$/.test(k)) n++; });
    var d = document.createElement("details"), s = document.createElement("summary");
    d.className = "filter-fold"; d.open = n > 0;
    s.textContent = n ? "فیلترها (" + HV.formatFaNumber(n) + " فعال)" : "فیلترها و جستجو";
    d.append(s);
    form.before(d); d.append(form);
  });
})();
