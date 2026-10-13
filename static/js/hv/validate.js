/* اعتبارسنجی زنده: بعد از ترک فیلد اجباری یا نامعتبر پیام فارسی می‌ده؛ فرم در هر صورت سمت سرور هم بررسی می‌شه */
(function () {
  function msg(el) {
    var v = el.validity;
    if (v.valueMissing) return el.tagName === "SELECT" ? "یکی از گزینه‌ها رو انتخاب کن." : "این فیلد رو پر کن.";
    if (v.typeMismatch) return el.type === "email" ? "ایمیل معتبر وارد کن." : el.type === "url" ? "آدرس اینترنتی معتبر وارد کن." : "مقدار نامعتبره.";
    if (v.tooShort) return "حداقل " + HV.formatFaNumber(el.minLength) + " نویسه بنویس.";
    if (v.patternMismatch) return "قالب وارد‌شده درست نیست.";
    return "";
  }
  function show(el, text) {
    var field = el.closest(".field");
    if (!field) return;
    var id = (el.id || el.name) + "-live-err", p = field.querySelector(".live-err");
    if (!text) { if (p) p.remove(); el.removeAttribute("aria-invalid"); el.removeAttribute("aria-describedby"); return; }
    if (!p) { p = document.createElement("p"); p.className = "err live-err"; p.id = id; p.setAttribute("role", "alert"); field.append(p); }
    p.textContent = text;
    el.setAttribute("aria-invalid", "true");
    el.setAttribute("aria-describedby", id);
  }
  document.addEventListener("focusout", function (e) {
    var el = e.target;
    if (!el.form || !el.form.noValidate || !el.willValidate || el.type === "file" || el.type === "hidden" || el.name === "isbn") return;
    if (!el.matches("input, select, textarea") || (!el.required && !el.value)) return;
    el.setCustomValidity("");
    show(el, msg(el));
  });
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (el.getAttribute && el.getAttribute("aria-invalid") === "true") { el.setCustomValidity(""); if (el.checkValidity()) show(el, ""); }
  });
})();
