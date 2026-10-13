/* پیش‌نویس فرم‌ها (data-draft): ذخیره‌ی خودکار در مرورگر، بازیابی با نوار پیشنهاد؛ فایل و رمز ذخیره نمی‌شه.
   فقط چیزهایی که کاربر واقعاً عوض کرده (فرق با حالت اولیه‌ی صفحه) ذخیره می‌شن؛ مقدارهای پیش‌فرض (وضعیت «دست‌دوم»،
   طرح جلد، استان پروفایل…) پیش‌نویس حساب نمی‌شن، وگرنه نوار «پیش‌نویس داری» بی‌دلیل میاد و «بازیابی» کاری نمی‌کنه. */
(function () {
  var uid = document.body.dataset.uid;
  if (!uid) return;
  var MAX_AGE = 30 * 60 * 1000;      // برگشت از دوربین/برنامه‌ی دیگه گاهی چند دقیقه طول می‌کشه
  document.querySelectorAll("form[data-draft]").forEach(function (form) {
    var key = "hv-draft:" + uid + ":" + form.dataset.draft;
    function store(v) { try { v === null ? localStorage.removeItem(key) : localStorage.setItem(key, JSON.stringify(v)); } catch (e) {} }
    function load() { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { return null; } }
    function fields() {
      return Array.prototype.filter.call(form.elements, function (el) {
        return el.name && el.name !== "csrfmiddlewaretoken" && !/^(file|password|hidden|submit|button|search)$/.test(el.type);
      });
    }
    function snapshot() {
      var d = {};
      fields().forEach(function (el) {
        if (el.type === "checkbox" || el.type === "radio") { if (el.checked) (d[el.name] = d[el.name] || []).push(el.value); }
        else d[el.name] = el.value;
      });
      return d;
    }
    var initial = snapshot();
    function same(a, b) { return JSON.stringify(a === undefined ? "" : a) === JSON.stringify(b === undefined ? "" : b); }
    function changes() {
      var now = snapshot(), d = {};
      Object.keys(now).forEach(function (k) { if (!same(now[k], initial[k])) d[k] = now[k]; });
      return d;
    }
    function save() {
      var d = changes(), dirty = Object.keys(d).length > 0;
      form.toggleAttribute("data-dirty", dirty);
      store(dirty ? { t: Date.now(), d: d } : null);
    }
    function apply(d) {
      // ترتیب DOM رعایت می‌شه (استان قبل از شهر)؛ هر فیلد رویداد خودش رو می‌گیره تا بقیه‌ی اسکریپت‌ها (پیش‌نمایش، شابک…) به‌روز شن
      fields().forEach(function (el) {
        if (!(el.name in d)) return;
        var v = d[el.name];
        if (el.type === "checkbox" || el.type === "radio") el.checked = Array.isArray(v) && v.indexOf(el.value) > -1;
        else if (typeof v === "string") el.value = v;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });
      // شهر بعد از پر شدن فهرست شهرهای استان
      if ("city" in d && form.elements.city) setTimeout(function () { form.elements.city.value = d.city; form.elements.city.dispatchEvent(new Event("change", { bubbles: true })); }, 0);
      save();
    }
    var saved = load();
    var usable = saved && saved.d && Object.keys(saved.d).length && Date.now() - saved.t < MAX_AGE && !form.querySelector(".field-error, .errorlist");
    if (usable) {
      var bar = document.createElement("div");
      bar.className = "alert draft-bar";
      bar.setAttribute("role", "status");
      var p = document.createElement("p");
      var labels = Object.keys(saved.d).map(function (k) {
        var el = form.elements[k], f = el && (el.length && !el.tagName ? el[0] : el), lab = f && f.labels && f.labels[0];
        return lab ? lab.textContent.replace("*", "").trim() : "";
      }).filter(Boolean).slice(0, 3);
      p.textContent = "یه پیش‌نویس ذخیره‌شده داری" + (labels.length ? " (" + labels.join("، ") + ")" : "") + ".";
      var yes = document.createElement("button"), no = document.createElement("button");
      yes.type = no.type = "button";
      yes.className = "btn btn-sm"; no.className = "btn btn-sm btn-ghost";
      yes.textContent = "بازیابی"; no.textContent = "دور بریز";
      yes.addEventListener("click", function () {
        apply(saved.d);
        bar.remove();
        HV.announce && HV.announce("پیش‌نویس بازیابی شد.");
        var first = form.querySelector("[name=isbn], [name=title]");
        if (first) first.scrollIntoView({ block: "center", behavior: HV.prefersReducedMotion() ? "auto" : "smooth" });
      });
      no.addEventListener("click", function () { store(null); bar.remove(); });
      bar.append(p, yes, no);
      form.prepend(bar);
    } else if (saved) store(null);
    var save1 = HV.debounce(save, 800);
    form.addEventListener("input", save1);
    form.addEventListener("change", save1);
    addEventListener("pagehide", save);
    document.addEventListener("visibilitychange", function () { if (document.hidden) save(); });   // قبل از رفتن به دوربین/برنامه‌ی دیگه
    form.addEventListener("submit", function () { removeEventListener("pagehide", save); store(null); form.removeAttribute("data-dirty"); });
  });
})();
