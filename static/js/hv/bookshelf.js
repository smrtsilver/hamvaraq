/* قفسه‌ی چوبی: نمایش دو ردیف اول، «مشاهده‌ی بیشتر» با انیمیشن، و کارت اطلاعات کتاب با لمس هر جلد */
(function () {
  var shelf = document.querySelector("[data-wshelf]");
  if (!shelf) return;
  var books = shelf.querySelector(".wshelf-books"), more = shelf.querySelector("[data-wshelf-more]");
  var rows = parseInt(shelf.dataset.rows, 10) || 2;
  shelf.style.setProperty("--rows", rows);

  function rowH() { return parseFloat(getComputedStyle(shelf).getPropertyValue("--row-h")) || 190; }
  function fits() { return books.scrollHeight <= rowH() * rows + 2; }
  function collapse() { shelf.classList.add("is-collapsed"); books.style.maxHeight = ""; more.textContent = "مشاهده‌ی بیشتر"; more.setAttribute("aria-expanded", "false"); }
  function setup() {
    if (fits()) { more.hidden = true; shelf.classList.remove("is-collapsed"); return; }
    more.hidden = false;
    if (more.getAttribute("aria-expanded") !== "true") collapse();
  }
  more.addEventListener("click", function () {
    var open = more.getAttribute("aria-expanded") === "true";
    if (open) {
      books.style.maxHeight = books.scrollHeight + "px";
      requestAnimationFrame(function () { collapse(); shelf.scrollIntoView({ block: "nearest", behavior: HV.prefersReducedMotion() ? "auto" : "smooth" }); });
    } else {
      shelf.classList.remove("is-collapsed");
      books.style.maxHeight = rowH() * rows + "px";
      requestAnimationFrame(function () { books.style.maxHeight = books.scrollHeight + "px"; });
      more.textContent = "نمایش کمتر"; more.setAttribute("aria-expanded", "true");
    }
  });
  setup();
  addEventListener("resize", HV.debounce(setup, 200));

  // کارت اطلاعات کتاب
  var dlg = document.createElement("dialog");
  dlg.className = "hv-modal book-dialog";
  dlg.setAttribute("aria-label", "اطلاعات کتاب");
  document.body.appendChild(dlg);
  var last = null;
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; }
  function chip(t) { return el("span", "chip", t); }
  function open(a) {
    var d = a.dataset;
    dlg.replaceChildren();
    var box = el("div", "bd");
    var cover = el("div", "bd-cover");
    if (d.cover) { var im = document.createElement("img"); im.alt = ""; im.src = d.cover; cover.appendChild(im); } else { cover.textContent = d.title; cover.classList.add("is-text"); }
    var info = el("div");
    var h = el("h2", "", d.title); info.append(h, el("p", "bd-author", d.author));
    var chips = el("div", "cluster");
    if (d.status) chips.appendChild(chip(d.status));
    if (d.swap) { var sw = chip("برای معاوضه"); sw.className = "ribbon-chip"; chips.appendChild(sw); }
    info.appendChild(chips);
    if (d.stars) info.appendChild(el("p", "stars bd-stars", "★★★★★".slice(0, +d.stars) + "☆☆☆☆☆".slice(0, 5 - d.stars)));
    if (d.added) info.appendChild(el("p", "small muted", "تو قفسه از " + d.added));
    box.append(cover, info);
    if (d.desc) { var q = el("blockquote", "bd-desc", d.desc); box.appendChild(q); }
    var act = el("div", "bd-actions"), go = null;
    if (d.go && a.getAttribute("href") !== "#") { go = el("a", "btn", d.go); go.href = a.href; }
    var close = el("button", "btn btn-ghost", "بستن"); close.type = "button"; close.addEventListener("click", function () { dlg.close(); });
    if (go) act.appendChild(go); act.appendChild(close); box.appendChild(act);
    dlg.appendChild(box);
    last = a; dlg.showModal();
  }
  books.addEventListener("click", function (e) {
    var a = e.target.closest("[data-sp]");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || !dlg.showModal) return;
    e.preventDefault(); open(a);
  });
  dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("close", function () { if (last) last.focus(); });
})();
