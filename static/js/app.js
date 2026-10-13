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


// دکمه‌ی بازگشت و تازه‌سازی (به‌جای javascript:)؛ تأیید اقدام خطرناک تو hv/modal.js
document.addEventListener("click", (e) => {
    const back = e.target.closest("[data-back]");
    if (back) { e.preventDefault(); if (history.length > 1) history.back(); else location.href = back.getAttribute("href") || "/"; return; }
    if (e.target.closest("[data-reload]")) location.reload();
});

// اشتراک‌گذاری: Web Share API (موبایل)، وگرنه کپی لینک
document.querySelectorAll("[data-share]").forEach((btn) => {
    if (!navigator.share && !(navigator.clipboard && navigator.clipboard.writeText)) return;
    btn.hidden = false;
    document.querySelectorAll("[data-share-fallback]").forEach((a) => { a.hidden = true; });
    btn.addEventListener("click", async () => {
        const data = {title: btn.dataset.shareTitle, url: btn.dataset.shareUrl};
        try {
            if (navigator.share) await navigator.share(data);
            else { await navigator.clipboard.writeText(data.url); const old = btn.textContent; btn.textContent = "لینک کپی شد"; setTimeout(() => { btn.textContent = old; }, 2000); }
        } catch (_) { /* کاربر انصراف داد */ }
    });
});

// باز/بسته کردن دیالوگ‌های ساده (مثل برگه‌ی افزودن به قفسه)؛ بدون JS لینک به صفحه‌ی جدا می‌ره
document.addEventListener("click", (e) => {
    const open = e.target.closest("[data-open-dialog]");
    if (open) {
        const d = document.getElementById(open.dataset.openDialog);
        if (d && d.showModal) { e.preventDefault(); d.showModal(); const f = d.querySelector("input:not([type=hidden])"); if (f) f.focus(); }
        return;
    }
    const close = e.target.closest("[data-close-dialog]");
    if (close) close.closest("dialog").close();
    else if (e.target.matches("dialog.sheet")) e.target.close();
});

// دکمه‌ی چاپ (نسخه‌ی چاپی قفسه)
document.addEventListener("click", (e) => { if (e.target.closest("[data-print]")) window.print(); });

// بنر پروفام: بستن تا ۳۰ روز (فقط تو همین مرورگر)
document.addEventListener("click", (e) => {
    const x = e.target.closest("[data-porfam-x]");
    if (!x) return;
    try { localStorage.setItem("hv-pf-off", String(Date.now() + 30 * 864e5)); } catch (_) { /* بسته */ }
    const box = x.closest("[data-porfam]");
    box.classList.add("is-closing");
    setTimeout(() => { document.documentElement.classList.add("pf-off"); }, 260);
});

// دکمه‌ی بازگشت هدر: اگه از همین سایت اومده، برگرد به صفحه‌ی قبلی (با اسکرول قبلی)؛ وگرنه صفحه‌ی والد
document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-back]");
    if (!a || e.metaKey || e.ctrlKey) return;
    let same = false;
    try { same = document.referrer && new URL(document.referrer).origin === location.origin && document.referrer !== location.href; } catch (_) { /* ارجاع نامعتبر */ }
    if (same && history.length > 1) { e.preventDefault(); history.back(); }
});

// رأی مبادله: دکمه‌ی دیسلایک فقط پنل «چرا؟» رو باز/بسته می‌کنه؛ لایک مستقیم ثبت می‌شه
document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-vote-down]");
    if (!b) return;
    const panel = document.getElementById(b.getAttribute("aria-controls"));
    if (!panel) return;
    const open = panel.hidden;
    panel.hidden = !open;
    b.setAttribute("aria-expanded", String(open));
    if (open) { const s = panel.querySelector("select"); if (s) s.focus(); }
});

// لودینگ ارسال فرم: دکمه‌ی ارسال قفل می‌شه و چرخنده می‌گیره تا کاربر دوباره نزنه (فرم‌های GET مثل جستجو مستثنی‌ان).
// اگه اسکریپت دیگه‌ای ارسال رو متوقف کرده باشه (اعتبارسنجی، استعلام شابک) کاری نمی‌کنیم؛ با برگشت به صفحه (bfcache) آزاد می‌شه.
document.addEventListener("submit", (e) => {
    const form = e.target;
    if ((form.method || "get").toLowerCase() !== "post" || form.hasAttribute("data-no-busy")) return;
    setTimeout(() => {
        if (e.defaultPrevented) return;
        const btns = [...form.querySelectorAll("button:not([type=button]), input[type=submit]")];
        const main = e.submitter && btns.includes(e.submitter) ? e.submitter : btns[btns.length - 1];
        form.setAttribute("aria-busy", "true");
        btns.forEach((b) => { b.disabled = true; });
        if (main) main.classList.add("is-loading");
    }, 0);
});
addEventListener("pageshow", () => {
    document.querySelectorAll("form[aria-busy=true]").forEach((form) => {
        form.removeAttribute("aria-busy");
        form.querySelectorAll("button, input[type=submit]").forEach((b) => { b.disabled = false; b.classList.remove("is-loading"); });
    });
});
