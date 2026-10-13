/* انتخاب‌گر جلد: حالت «طرح آماده / عکس خودم»، دسته‌ها، پیش‌نمایش زنده با عنوان و نویسنده‌ی تایپ‌شده،
   و آلبوم عکس واقعی (کشیدن‌ورها کردن، پیش‌نمایش، سقف ۴ عکس و ۵ مگابایت قبل از ارسال). */
(function () {
  var picker = document.querySelector("[data-cover-picker]");
  if (picker) {
    var form = picker.closest("form");
    var panels = picker.querySelectorAll("[data-cover-panel]");
    function mode() { var r = picker.querySelector("input[name=cover_mode]:checked"); return r ? r.value : "design"; }
    function syncMode() { panels.forEach(function (p) { p.hidden = p.dataset.coverPanel !== mode(); }); }
    picker.addEventListener("change", function (e) { if (e.target.name === "cover_mode") syncMode(); });
    syncMode();

    picker.querySelectorAll("[data-cp-cat]").forEach(function (b) {
      b.addEventListener("click", function () {
        picker.querySelectorAll("[data-cp-cat]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        picker.querySelectorAll("[data-cp-item]").forEach(function (it) { it.hidden = !!b.dataset.cpCat && it.dataset.cpItem !== b.dataset.cpCat; });
      });
    });

    var base = picker.dataset.previewUrl;
    var title = form.querySelector("[name=title]"), author = form.querySelector("[name=author]");
    var refresh = HV.debounce(function () {
      var q = "?t=" + encodeURIComponent(title.value.trim()) + "&a=" + encodeURIComponent(author.value.trim());
      picker.querySelectorAll("[data-cp-img]").forEach(function (img) {
        var next = base.replace("KEY", img.dataset.cpImg) + q;
        if (img.getAttribute("src") !== next) {
          img.classList.add("is-loading");
          img.onload = function () { img.classList.remove("is-loading"); };
          img.src = next;
        }
      });
    }, 600);
    [title, author].forEach(function (el) { if (el) el.addEventListener("input", refresh); });
  }

  // ---- آلبوم عکس واقعی ----
  var drop = document.querySelector("[data-album-drop]");
  if (!drop) return;
  var input = drop.querySelector("input[type=file]");
  var box = drop.querySelector("[data-album-previews]");
  var existing = document.querySelectorAll(".ae-item").length;
  var MAX = 4 - existing, MB = 5 * 1024 * 1024, OK = /^image\/(jpeg|png|webp)$/;
  input.setAttribute("accept", "image/jpeg,image/png,image/webp");
  function render() {
    box.replaceChildren();
    var files = Array.prototype.slice.call(input.files || []);
    files.forEach(function (f, i) {
      var url = URL.createObjectURL(f);
      var fig = document.createElement("figure"); fig.className = "ap-item";
      var img = document.createElement("img"); img.src = url; img.alt = ""; img.onload = function () { URL.revokeObjectURL(url); };
      var cap = document.createElement("figcaption"); cap.textContent = HV.formatFaNumber(i + 1);
      fig.append(img, cap); box.appendChild(fig);
    });
  }
  function accept(files) {
    var list = Array.prototype.slice.call(files), msg = "";
    list = list.filter(function (f) {
      if (!OK.test(f.type)) { msg = "فقط عکس جی‌پی‌جی، پی‌ان‌جی یا وب‌پی."; return false; }
      if (f.size > MB * 3) { msg = "حجم «" + f.name + "» خیلی زیاده (حداکثر ۵ مگابایت بعد از فشرده‌سازی)."; return false; }
      return true;
    });
    if (list.length > MAX) { msg = MAX > 0 ? "حداکثر " + HV.formatFaNumber(MAX) + " عکس دیگه می‌تونی اضافه کنی." : "آلبوم پره (۴ عکس)؛ اول یکی رو حذف کن."; list = list.slice(0, Math.max(0, MAX)); }
    if (msg) HV.announce(msg, "error");
    var dt = new DataTransfer(); list.forEach(function (f) { dt.items.add(f); });
    input.files = dt.files;
    render();
    busy = true;
    input.dispatchEvent(new Event("change", { bubbles: true }));     // فشرده‌سازی compress.js و نام فایل‌ها
    busy = false;
  }
  var busy = false;
  input.addEventListener("change", function () { if (!busy) accept(input.files); });
  ["dragenter", "dragover"].forEach(function (t) { drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.add("is-over"); }); });
  ["dragleave", "drop"].forEach(function (t) { drop.addEventListener(t, function () { drop.classList.remove("is-over"); }); });
  drop.addEventListener("drop", function (e) { e.preventDefault(); if (e.dataTransfer && e.dataTransfer.files.length) accept(e.dataTransfer.files); });
})();
