/* پیش‌نویس فرم‌ها (data-draft): ذخیره‌ی خودکار در مرورگر، بازیابی با نوار پیشنهاد؛ فایل و رمز ذخیره نمی‌شه */
(function () {
  var uid = document.body.dataset.uid;
  if (!uid) return;
  var MAX_AGE = 10 * 60 * 1000;
  document.querySelectorAll("form[data-draft]").forEach(function (form) {
    var key = "hv-draft:" + uid + ":" + form.dataset.draft;
    function store(v) { try { v === null ? localStorage.removeItem(key) : localStorage.setItem(key, JSON.stringify(v)); } catch (e) {} }
    function load() { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { return null; } }
    function fields() {
      return Array.prototype.filter.call(form.elements, function (el) {
        return el.name && el.name !== "csrfmiddlewaretoken" && !/^(file|password|hidden|submit|button)$/.test(el.type);
      });
    }
    function snapshot() {
      var d = {};
      fields().forEach(function (el) {
        if (el.type === "checkbox" || el.type === "radio") { if (el.checked) (d[el.name] = d[el.name] || []).push(el.value); }
        else if (el.value) d[el.name] = el.value;
      });
      return d;
    }
    function save() { var d = snapshot(); store(Object.keys(d).length ? { t: Date.now(), d: d } : null); }
    function apply(d) {
      fields().forEach(function (el) {
        var v = d[el.name];
        if (el.type === "checkbox" || el.type === "radio") el.checked = Array.isArray(v) && v.indexOf(el.value) > -1;
        else if (typeof v === "string") el.value = v;
        el.dispatchEvent(new Event("change", { bubbles: true }));
      });
    }
    var saved = load();
    if (saved && Date.now() - saved.t < MAX_AGE && !form.querySelector(".field-error, .errorlist")) {
      var bar = document.createElement("div");
      bar.className = "alert draft-bar";
      bar.setAttribute("role", "status");
      var p = document.createElement("p");
      p.textContent = "یه پیش‌نویس ذخیره‌شده داری.";
      var yes = document.createElement("button"), no = document.createElement("button");
      yes.type = no.type = "button";
      yes.className = "btn btn-sm"; no.className = "btn btn-sm btn-ghost";
      yes.textContent = "بازیابی"; no.textContent = "دور بریز";
      yes.onclick = function () { apply(saved.d); bar.remove(); };
      no.onclick = function () { store(null); bar.remove(); };
      bar.append(p, yes, no);
      form.prepend(bar);
    } else if (saved) store(null);
    var save1 = HV.debounce(save, 1000);
    form.addEventListener("input", save1);
    form.addEventListener("change", save1);
    addEventListener("beforeunload", save);
    form.addEventListener("submit", function () { removeEventListener("beforeunload", save); store(null); });
  });
})();
