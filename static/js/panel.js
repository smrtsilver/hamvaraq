/* ابزارهای پنل مدیریت: انتخاب گروهی، نمایش ستون‌ها، تراکم جدول، نماهای ذخیره‌شده (فقط در مرورگر) و میان‌برهای صفحه‌کلید */
(function () {
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };
  var key = "hv-panel:" + location.pathname;

  // ---- انتخاب گروهی ----
  var bar = document.querySelector("[data-bulk]");
  if (bar) {
    var boxes = function () { return Array.prototype.slice.call(document.querySelectorAll('input[name=ids][form="bulk-form"]')); };
    var count = bar.querySelector("[data-bulk-count]");
    var sync = function () {
      var n = boxes().filter(function (b) { return b.checked; }).length;
      count.textContent = HV.formatFaNumber(n) + " انتخاب";
      bar.classList.toggle("is-active", n > 0);
      bar.classList.add("is-ready");
      boxes().forEach(function (b) { b.closest("tr").classList.toggle("is-selected", b.checked); });
    };
    document.addEventListener("change", function (e) {
      if (e.target.matches("[data-select-all]")) boxes().forEach(function (b) { b.checked = e.target.checked; });
      if (e.target.matches("[data-select-all], input[name=ids]")) sync();
    });
    bar.addEventListener("submit", function (e) { if (!boxes().some(function (b) { return b.checked; })) { e.preventDefault(); HV.announce("اول چند مورد رو انتخاب کن.", "error"); } });
    sync();
  }

  // ---- ابزار جدول: ستون‌ها و تراکم ----
  var table = document.querySelector("[data-ptable]");
  if (table) {
    var prefs = store.get(key, { hidden: [], dense: false, views: [] });
    var heads = Array.prototype.slice.call(table.querySelectorAll("thead th"));
    function apply() {
      table.classList.toggle("is-dense", !!prefs.dense);
      heads.forEach(function (th, i) {
        var hide = prefs.hidden.indexOf(i) > -1;
        table.querySelectorAll("tr").forEach(function (tr) { var c = tr.children[i]; if (c && !c.hasAttribute("colspan")) c.hidden = hide; });
      });
    }
    var tools = document.createElement("div");
    tools.className = "ptools";
    var det = document.createElement("details");
    det.className = "ptools-cols";
    var sum = document.createElement("summary"); sum.textContent = "ستون‌ها"; det.appendChild(sum);
    var list = document.createElement("div"); list.className = "ptools-menu";
    heads.forEach(function (th, i) {
      var label = th.textContent.trim();
      if (!label || th.classList.contains("sel")) return;
      var l = document.createElement("label"), cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = prefs.hidden.indexOf(i) === -1;
      cb.addEventListener("change", function () {
        prefs.hidden = prefs.hidden.filter(function (x) { return x !== i; });
        if (!cb.checked) prefs.hidden.push(i);
        store.set(key, prefs); apply();
      });
      l.append(cb, document.createTextNode(" " + label)); list.appendChild(l);
    });
    det.appendChild(list);
    var dense = document.createElement("button");
    dense.type = "button"; dense.className = "btn btn-ghost btn-sm";
    var paintDense = function () { dense.textContent = prefs.dense ? "تراکم: فشرده" : "تراکم: راحت"; dense.setAttribute("aria-pressed", String(!!prefs.dense)); };
    dense.addEventListener("click", function () { prefs.dense = !prefs.dense; store.set(key, prefs); paintDense(); apply(); });
    paintDense();

    // نماهای ذخیره‌شده: همین فیلتر و جستجو با یه اسم، فقط تو همین مرورگر
    var views = document.createElement("div"); views.className = "ptools-views";
    function paintViews() {
      views.replaceChildren();
      (prefs.views || []).forEach(function (v, idx) {
        var a = document.createElement("a"); a.className = "chip"; a.href = location.pathname + v.qs; a.textContent = v.name;
        var x = document.createElement("button"); x.type = "button"; x.className = "chip-x-btn"; x.setAttribute("aria-label", "حذف نمای " + v.name); x.textContent = "×";
        x.addEventListener("click", function () { prefs.views.splice(idx, 1); store.set(key, prefs); paintViews(); });
        var w = document.createElement("span"); w.className = "view-chip"; w.append(a, x); views.appendChild(w);
      });
      var save = document.createElement("button"); save.type = "button"; save.className = "btn btn-ghost btn-sm"; save.textContent = "+ ذخیره‌ی این نما";
      save.addEventListener("click", function () {
        HV.modal.prompt({ title: "ذخیره‌ی نما", message: "یه اسم کوتاه برای این فیلتر و جستجو:", confirmLabel: "ذخیره" }).then(function (name) {
          if (!name) return;
          prefs.views = (prefs.views || []).concat([{ name: name.slice(0, 30), qs: location.search }]).slice(-8);
          store.set(key, prefs); paintViews();
        });
      });
      views.appendChild(save);
    }
    paintViews();
    tools.append(views, det, dense);
    table.closest(".ptable-wrap").before(tools);
    apply();
  }

  // ---- میان‌برهای صفحه‌کلید ----
  var NAV = { r: "reports", t: "tickets", u: "users", b: "books", p: "posts", a: "announcements", c: "clubs", s: "stats", h: "" };
  var pendingG = false, timer = null;
  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey || e.target.closest("input, textarea, select, [contenteditable]")) return;
    if (e.key === "/") { var s = document.querySelector(".psearch input[type=search]"); if (s) { e.preventDefault(); s.focus(); } return; }
    if (e.key === "?") { e.preventDefault(); HV.modal.info({ title: "میان‌برها", message: "/ جستجو · g سپس r گزارش‌ها، t مشکلات، u کاربران، b کتاب‌ها، p معرفی‌ها، a اطلاعیه‌ها، c باشگاه‌ها، s آمار، h نمای کلی" }); return; }
    if (e.key === "g") { pendingG = true; clearTimeout(timer); timer = setTimeout(function () { pendingG = false; }, 900); return; }
    if (pendingG && e.key in NAV) { pendingG = false; location.href = "/panel/" + (NAV[e.key] ? NAV[e.key] + "/" : ""); }
  });
})();
