/* نمایش بزرگ عکس‌های آلبوم: قبلی/بعدی، کشیدن با انگشت، زوم با لمس (فقط transform)، بستن با Escape یا بیرون */
(function () {
  var album = document.querySelector("[data-album]");
  if (!album) return;
  var items = Array.prototype.slice.call(album.querySelectorAll("[data-lb-src]"));
  var dlg = document.createElement("dialog");
  dlg.className = "lightbox";
  dlg.setAttribute("aria-label", "عکس‌های کتاب");
  dlg.innerHTML = '<figure class="lb-fig"><img alt=""><figcaption aria-live="polite"></figcaption></figure>' +
    '<button type="button" class="lb-btn lb-prev" aria-label="عکس قبلی"><svg class="i" aria-hidden="true"><use href="#i-chevron-right"/></svg></button>' +
    '<button type="button" class="lb-btn lb-next" aria-label="عکس بعدی"><svg class="i" aria-hidden="true"><use href="#i-chevron-left"/></svg></button>' +
    '<button type="button" class="lb-btn lb-close" aria-label="بستن"><svg class="i" aria-hidden="true"><use href="#i-x"/></svg></button>';
  document.body.appendChild(dlg);
  var img = dlg.querySelector("img"), cap = dlg.querySelector("figcaption"), idx = 0, zoom = false, last = null, x0 = null;
  function show(i) {
    idx = (i + items.length) % items.length; zoom = false; img.classList.remove("is-zoom"); img.style.transformOrigin = "";
    img.src = items[idx].dataset.lbSrc;
    img.alt = items[idx].querySelector("img").alt;
    cap.textContent = HV.formatFaNumber(idx + 1) + " از " + HV.formatFaNumber(items.length);
    dlg.querySelector(".lb-prev").hidden = dlg.querySelector(".lb-next").hidden = items.length < 2;
  }
  items.forEach(function (b, i) { b.addEventListener("click", function () { last = b; show(i); dlg.showModal(); }); });
  dlg.querySelector(".lb-prev").addEventListener("click", function () { show(idx - 1); });
  dlg.querySelector(".lb-next").addEventListener("click", function () { show(idx + 1); });
  dlg.querySelector(".lb-close").addEventListener("click", function () { dlg.close(); });
  dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("close", function () { if (last) last.focus(); });
  dlg.addEventListener("keydown", function (e) { if (e.key === "ArrowLeft") show(idx + 1); if (e.key === "ArrowRight") show(idx - 1); });
  img.addEventListener("click", function (e) {
    var r = img.getBoundingClientRect();
    img.style.transformOrigin = ((e.clientX - r.left) / r.width * 100) + "% " + ((e.clientY - r.top) / r.height * 100) + "%";
    zoom = !zoom; img.classList.toggle("is-zoom", zoom);
  });
  img.addEventListener("touchstart", function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  img.addEventListener("touchend", function (e) {
    if (x0 === null || zoom) return;
    var dx = e.changedTouches[0].clientX - x0; x0 = null;
    if (Math.abs(dx) > 50) show(dx > 0 ? idx + 1 : idx - 1);   // راست‌به‌چپ: کشیدن به راست = بعدی
  }, { passive: true });
})();
