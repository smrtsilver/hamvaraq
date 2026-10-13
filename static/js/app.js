// رفتارهای عمومی سایت: حالت تیره، منوی کاربر، اعلان‌های گذرا، گالری، پیام‌های فارسی اعتبارسنجی فرم.
(() => {
    const root = document.documentElement;

    // ---- حالت روشن/تیره ----
    const prefersDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = () => (root.dataset.theme ? root.dataset.theme === "dark" : prefersDark());
    function paintToggle() {
        document.querySelectorAll("[data-theme-toggle] use").forEach((u) => u.setAttribute("href", isDark() ? "#i-sun" : "#i-moon"));
    }
    document.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-theme-toggle]");
        if (!btn) return;
        const next = isDark() ? "light" : "dark";
        root.dataset.theme = next;
        try { localStorage.setItem("hv-theme", next); } catch (_) { /* حافظه بسته‌ست */ }
        paintToggle();
    });
    paintToggle();

    // ---- منوی کاربر: با کلیک بیرون یا Escape بسته می‌شه ----
    document.addEventListener("click", (e) => {
        document.querySelectorAll("details[data-menu][open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; });
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") document.querySelectorAll("details[data-menu][open]").forEach((d) => { d.open = false; d.querySelector("summary").focus(); });
    });

    // ---- اعلان‌های گذرا ----
    document.querySelectorAll("[data-toast]").forEach((t) => {
        const close = () => { t.style.transition = "opacity .25s"; t.style.opacity = "0"; setTimeout(() => t.remove(), 260); };
        t.querySelector("button").addEventListener("click", close);
        setTimeout(close, t.classList.contains("toast-error") ? 9000 : 6000);
    });

    // ---- گالری عکس کتاب ----
    document.querySelectorAll("[data-gallery]").forEach((g) => {
        const main = g.querySelector("[data-gallery-main]");
        g.querySelectorAll("[data-gallery-thumb]").forEach((b) => b.addEventListener("click", () => {
            main.src = b.dataset.src;
            g.querySelectorAll("[data-gallery-thumb]").forEach((x) => x.removeAttribute("aria-current"));
            b.setAttribute("aria-current", "true");
        }));
    });

    // ---- پیام‌های اعتبارسنجی فارسی (مرورگر به زبان خودش انگلیسی نشون می‌ده) ----
    document.addEventListener("invalid", (e) => {
        const el = e.target, v = el.validity;
        let msg = "";
        if (v.valueMissing) msg = el.type === "checkbox" ? "برای ادامه باید این گزینه رو تیک بزنی." : el.tagName === "SELECT" ? "یکی از گزینه‌ها رو انتخاب کن." : "این فیلد رو پر کن.";
        else if (v.typeMismatch) msg = el.type === "email" ? "ایمیل معتبر وارد کن." : el.type === "url" ? "آدرس اینترنتی معتبر وارد کن." : "مقدار نامعتبره.";
        else if (v.tooShort) msg = `حداقل ${el.minLength.toLocaleString("fa-IR")} نویسه بنویس.`;
        else if (v.tooLong) msg = `حداکثر ${el.maxLength.toLocaleString("fa-IR")} نویسه مجازه.`;
        else if (v.patternMismatch) msg = "قالب وارد‌شده درست نیست.";
        else if (v.rangeUnderflow || v.rangeOverflow) msg = "عدد خارج از بازه‌ی مجازه.";
        el.setCustomValidity(msg);
    }, true);
    document.addEventListener("input", (e) => { if (e.target.setCustomValidity) e.target.setCustomValidity(""); }, true);
    document.addEventListener("change", (e) => { if (e.target.setCustomValidity) e.target.setCustomValidity(""); }, true);
})();


// عرض/ارتفاع درصدی از data-w / data-h (بدون style درون‌خطی؛ سازگار با CSP)
document.querySelectorAll("[data-w]").forEach((el) => { el.style.width = el.dataset.w + "%"; });
document.querySelectorAll("[data-h]").forEach((el) => { el.style.height = el.dataset.h + "%"; });

// تأیید پیش از اقدام خطرناک (به‌جای onclick/onsubmit)، دکمه‌ی بازگشت و تازه‌سازی (به‌جای javascript:)
document.addEventListener("submit", (e) => {
    const msg = e.target.dataset && e.target.dataset.confirm;
    if (msg && !confirm(msg)) e.preventDefault();
});
document.addEventListener("click", (e) => {
    const guarded = e.target.closest("button[data-confirm], a[data-confirm]");
    if (guarded && !confirm(guarded.dataset.confirm)) { e.preventDefault(); e.stopPropagation(); return; }
    const back = e.target.closest("[data-back]");
    if (back) { e.preventDefault(); if (history.length > 1) history.back(); else location.href = back.getAttribute("href") || "/"; return; }
    if (e.target.closest("[data-reload]")) location.reload();
});
