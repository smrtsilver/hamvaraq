/* فهرست کتاب‌ها: فیلتر/مرتب‌سازی بدون بارگذاری کامل، تاریخچه‌ی مرورگر، و اسکرول بی‌نهایت (بدون JS همون صفحه‌بندی عادیه) */
(function () {
  var host = document.getElementById("book-results");
  var form = document.querySelector("form.filterbar");
  if (!host || !form || !window.fetch || !window.DOMParser) return;
  var loading = false, io = null;

  function skeleton(n) {
    var f = document.createDocumentFragment();
    for (var i = 0; i < n; i++) {
      var d = document.createElement("div");
      d.className = "hv-card--skeleton";
      d.setAttribute("aria-hidden", "true");
      d.innerHTML = '<div class="cover"></div><i></i><i></i>';
      f.appendChild(d);
    }
    return f;
  }
  function get(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (t) { return new DOMParser().parseFromString(t, "text/html"); });
  }
  function nextHref() { var a = host.querySelector(".pager a[rel=next]"); return a ? a.getAttribute("href") : null; }

  function arm() {
    if (io) { io.disconnect(); io = null; }
    var old = host.querySelector(".more-sentinel"); if (old) old.remove();
    var pager = host.querySelector(".pager"), grid = host.querySelector(".book-grid");
    if (!pager || !grid || !nextHref()) return;
    pager.hidden = true;
    var box = document.createElement("div");
    box.className = "more-sentinel";
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "btn btn-secondary"; btn.textContent = "کتاب‌های بیشتر";
    btn.addEventListener("click", more);
    box.appendChild(btn);
    host.appendChild(box);
    if ("IntersectionObserver" in window) {
      io = new IntersectionObserver(function (es) { if (es[0].isIntersecting) more(); }, { rootMargin: "400px" });
      io.observe(box);
    }
  }
  function more() {
    var href = nextHref(), grid = host.querySelector(".book-grid");
    if (!href || loading || !grid) return;
    loading = true;
    var sk = skeleton(4); var marks = Array.prototype.slice.call(sk.children);
    grid.appendChild(sk);
    get(href).then(function (doc) {
      marks.forEach(function (m) { m.remove(); });
      var src = doc.querySelector(".book-grid"), pg = doc.querySelector(".pager");
      if (src) Array.prototype.slice.call(src.children).forEach(function (c) { grid.appendChild(document.importNode(c, true)); });
      var cur = host.querySelector(".pager");
      if (cur && pg) cur.replaceWith(document.importNode(pg, true)); else if (cur) cur.remove();
      HV.enhance(grid);
      arm();
    }).catch(function () {
      marks.forEach(function (m) { m.remove(); });
      var p = host.querySelector(".pager"); if (p) p.hidden = false;
    }).then(function () { loading = false; });
  }
  function swap(url, push) {
    var grid = host.querySelector(".book-grid");
    host.setAttribute("aria-busy", "true");
    if (grid) { grid.replaceChildren(skeleton(8)); }
    return get(url).then(function (doc) {
      var next = doc.getElementById("book-results");
      if (!next) { location.href = url; return; }
      host.innerHTML = next.innerHTML;
      HV.enhance(host);
      if (push) history.pushState({ hv: 1 }, "", url);
      arm();
    }).catch(function () { location.href = url; }).then(function () { host.removeAttribute("aria-busy"); });
  }
  function urlFromForm() {
    var q = new URLSearchParams(new FormData(form));
    Array.from(q.keys()).forEach(function (k) { if (q.get(k) === "") q.delete(k); });
    var s = q.toString();
    return location.pathname + (s ? "?" + s : "");
  }
  form.addEventListener("submit", function (e) { e.preventDefault(); swap(urlFromForm(), true); });
  var sort = form.querySelector("select[name=sort]");
  if (sort) sort.addEventListener("change", function () { swap(urlFromForm(), true); });
  host.addEventListener("click", function (e) {
    var a = e.target.closest(".active-chips a");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault(); swap(a.getAttribute("href"), true);
  });
  addEventListener("popstate", function () { swap(location.pathname + location.search, false); });
  arm();
})();
