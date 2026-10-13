// ابزارهای مشترک هم‌ورق (تنها فضای‌نام سراسری: window.HV). بدون وابستگی؛ قبل از بقیه‌ی اسکریپت‌ها لود می‌شه.
// no-JS fallback: هیچ‌چیز به این فایل وابسته‌ی حیاتی نیست؛ همه‌ی صفحه‌ها بدون جاوااسکریپت هم کار می‌کنن.
(() => {
    const HV = (window.HV = window.HV || {});
    const FA = "۰۱۲۳۴۵۶۷۸۹";

    HV.$ = (sel, root = document) => root.querySelector(sel);
    HV.$$ = (sel, root = document) => [...root.querySelectorAll(sel)];

    HV.debounce = (fn, ms) => {
        let t;
        const wrapped = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
        wrapped.cancel = () => clearTimeout(t);
        return wrapped;
    };
    HV.throttle = (fn, ms) => {
        let last = 0, timer = null;
        return (...a) => {
            const left = ms - (Date.now() - last);
            if (left <= 0) { last = Date.now(); fn(...a); }
            else if (!timer) timer = setTimeout(() => { timer = null; last = Date.now(); fn(...a); }, left);
        };
    };

    HV.prefersDark = () => matchMedia("(prefers-color-scheme: dark)").matches;
    HV.prefersReducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
    HV.formatFaNumber = (n) => String(n).replace(/\d/g, (d) => FA[d]);
    HV.faDigitsToEn = (s) => String(s || "").replace(/[۰-۹]/g, (d) => FA.indexOf(d)).replace(/[٠-٩]/g, (d) => d.charCodeAt(0) - 1632);

    // fetch → JSON با خطای نرمال (error.status) و پشتیبانی از AbortController
    HV.fetchJSON = async (url, {signal, method = "GET", body, headers = {}} = {}) => {
        let res;
        try {
            res = await fetch(url, {signal, method, body, credentials: "same-origin", headers: {Accept: "application/json", ...headers}});
        } catch (err) {
            if (err.name === "AbortError") throw err;
            const e = new Error("network"); e.status = 0; throw e;
        }
        let data = null;
        try { data = await res.json(); } catch (_) { /* بدنه‌ی غیر JSON */ }
        if (!res.ok) { const e = new Error((data && (data.message || data.error)) || `http ${res.status}`); e.status = res.status; e.data = data; throw e; }
        return data;
    };

    // اعلان گذرا تو ناحیه‌ی .toasts (aria-live از قالب پایه می‌آد)
    HV.announce = (msg, kind = "info", ms = 5000) => {
        const region = HV.$(".toasts");
        if (!region) return;
        const t = document.createElement("div");
        t.className = `toast toast-${kind}`;
        const p = document.createElement("p");
        p.textContent = msg;
        const b = document.createElement("button");
        b.type = "button";
        b.setAttribute("aria-label", "بستن");
        b.textContent = "✕";
        const close = () => { t.classList.add("toast-out"); setTimeout(() => t.remove(), 260); };
        b.addEventListener("click", close);
        t.append(p, b);
        region.append(t);
        setTimeout(close, ms);
    };

    // عرض/ارتفاع درصدی، LQIP و نام view-transition (بدون style درون‌خطی؛ با CSSOM) برای محتوای تازه هم صدا زده می‌شه
    HV.enhance = (root = document) => {
        HV.$$("[data-w]", root).forEach((el) => { el.style.width = el.dataset.w + "%"; });
        HV.$$("[data-h]", root).forEach((el) => { el.style.height = el.dataset.h + "%"; });
        HV.$$("[data-pct]", root).forEach((el) => { el.style.setProperty("--pct", el.dataset.pct); });
        HV.$$("img[data-lqip]", root).forEach((img) => {
            const box = img.closest(".hv-card-cover, .cover");
            if (box && !box.style.backgroundImage) box.style.backgroundImage = `url("${img.dataset.lqip}")`;
        });
        const seen = new Set();          // نام انتقال باید یکتا باشه؛ یه کتاب ممکنه تو دو قفسه‌ی صفحه باشه
        HV.$$("[data-book-id]", root).filter((el) => !seen.has(el.dataset.bookId) && seen.add(el.dataset.bookId)).slice(0, 40)
            .forEach((el) => { el.style.viewTransitionName = `book-${el.dataset.bookId}`; });
    };
    HV.enhance();
})();
