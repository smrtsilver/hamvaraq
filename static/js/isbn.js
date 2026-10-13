// شابک: اعتبارسنجی رقم کنترل سمت کلاینت، استعلام از سرور (عنوان/نویسنده/ناشر…)، و نمایش وضعیت زیر فیلد
// (منتظرها، کتاب تکراری، نسخه‌ی دیگر). رویداد hv:isbn برای پیش‌نمایش زنده منتشر می‌شه.
(() => {
    const FA = "۰۱۲۳۴۵۶۷۸۹";
    const toEn = (s) => (s || "").replace(/[۰-۹]/g, (d) => FA.indexOf(d)).replace(/[٠-٩]/g, (d) => d.charCodeAt(0) - 1632);
    const faNum = (n) => String(n).replace(/\d/g, (d) => FA[d]);

    function isbn13(raw) {
        const d = toEn(raw).replace(/[\s\-‐-―]/g, "").toUpperCase();
        if (/^\d{13}$/.test(d)) return d.split("").reduce((s, c, i) => s + c * (i % 2 ? 3 : 1), 0) % 10 === 0 ? d : null;
        if (/^\d{9}[\dX]$/.test(d) && d.split("").reduce((s, c, i) => s + (c === "X" ? 10 : +c) * (10 - i), 0) % 11 === 0) {
            const b = "978" + d.slice(0, 9);
            return b + ((10 - b.split("").reduce((s, c, i) => s + c * (i % 2 ? 3 : 1), 0) % 10) % 10);
        }
        return null;
    }
    window.HVIsbn = {normalize: isbn13};

    function statusBox(input) {
        const field = input.closest(".field") || input.parentElement;
        let box = field.querySelector(".isbn-status");
        if (!box) {
            box = document.createElement("div");
            box.className = "isbn-status";
            box.setAttribute("role", "status");
            box.setAttribute("aria-live", "polite");
            box.id = (input.id || "isbn") + "-status";
            input.setAttribute("aria-describedby", box.id);
            field.append(box);
        }
        return box;
    }
    const line = (cls, text) => { const p = document.createElement("p"); p.className = cls; p.textContent = text; return p; };
    function show(box, items) { box.replaceChildren(...items); box.hidden = !items.length; }

    let seq = 0;
    document.addEventListener("change", async (e) => {
        const input = e.target;
        if (!input.matches("[data-isbn-url]")) return;
        const box = statusBox(input), scope = input.closest("[data-isbn-scope]") || input.form;
        const title = scope.querySelector("[data-isbn-title]"), author = scope.querySelector("[data-isbn-author]");
        const value = input.value.trim();
        input.removeAttribute("aria-invalid");
        if (!value) { show(box, []); document.dispatchEvent(new CustomEvent("hv:isbn", {detail: {scope, data: null}})); return; }
        const clean = isbn13(value);
        if (!clean) {
            input.setAttribute("aria-invalid", "true");
            const digits = toEn(value).replace(/[\s\-]/g, "");
            show(box, [line("isbn-err", /^\d{10}$|^\d{9}X$|^\d{13}$/i.test(digits) ? "رقم کنترل این شابک درست نیست؛ یه بار دیگه چک کن." : "شابک باید ۱۰ یا ۱۳ رقم باشه.")]);
            return;
        }
        input.value = clean;
        const mine = ++seq;
        show(box, [line("isbn-wait", "در حال جستجو…")]);
        try {
            const r = await fetch(input.dataset.isbnUrl + "?isbn=" + encodeURIComponent(clean), {credentials: "same-origin"});
            if (mine !== seq) return;
            if (r.status === 404) { show(box, [line("isbn-note", "این شابک تو منبع‌ها پیدا نشد؛ عنوان و نویسنده رو خودت بنویس.")]); return; }
            if (!r.ok) { show(box, [line("isbn-err", (await r.json().catch(() => ({}))).message || "استعلام ناموفق بود؛ دستی پر کن.")]); return; }
            const d = await r.json();
            if (title && !title.value) title.value = d.title;
            if (author && !author.value) author.value = d.author;
            const items = [];
            const meta = [d.publisher, d.year ? faNum(d.year) + (d.year_calendar === "jalali" ? " شمسی" : "") : "", d.pages ? faNum(d.pages) + " صفحه" : ""].filter(Boolean).join(" · ");
            items.push(line("isbn-ok", (d.confidence >= 40 && d.source !== "user" ? "مشخصات پیدا شد" : "مشخصات ثبت‌شده توسط کاربران") + (meta ? ": " + meta : "")));
            if (d.mine) items.push(line("isbn-warn", "این کتاب (همین شابک) رو قبلاً ثبت کردی؛ مطمئنی دوباره می‌خوای؟"));
            if (d.demand) items.push(line("isbn-demand", faNum(d.demand) + " نفر دنبال این کتاب بوده‌ن؛ ثبتش شانس مبادله‌ات رو بالا می‌بره."));
            if (d.available_elsewhere) items.push(line("isbn-note", faNum(d.available_elsewhere) + " نسخه‌ی دیگه‌ی همین کتاب الان تو هم‌ورق موجوده."));
            show(box, items);
            document.dispatchEvent(new CustomEvent("hv:isbn", {detail: {scope, data: d}}));
        } catch (_) { show(box, []); /* پر کردن دستی هنوز ممکنه */ }
    });
})();
