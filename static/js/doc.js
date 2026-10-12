(function () {
  var links = [].slice.call(document.querySelectorAll(".doc-toc a"));
  if (!links.length || !("IntersectionObserver" in window)) return;
  var map = {};
  links.forEach(function (a) { map[a.getAttribute("href").slice(1)] = a; });
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (e.isIntersecting) {
        links.forEach(function (a) { a.classList.remove("active"); });
        var a = map[e.target.id]; if (a) a.classList.add("active");
      }
    });
  }, { rootMargin: "-20% 0px -65% 0px" });
  Object.keys(map).forEach(function (id) { var el = document.getElementById(id); if (el) io.observe(el); });
})();
