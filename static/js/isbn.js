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

    // دکمه‌ی جستجو کنار هر فیلد شابک
    document.querySelectorAll("[data-isbn-url]").forEach((input) => {
        if (input.closest(".isbn-row")) return;
        const row = document.createElement("div"); row.className = "isbn-row";
        input.before(row); row.append(input);
        const b = document.createElement("button");
        b.type = "button"; b.className = "btn btn-secondary isbn-go"; b.textContent = "جستجو";
        b.addEventListener("click", () => lookup(input));
        row.append(b);
        const scan = input.id && document.querySelector(`[data-scan][data-scan-target="${input.id}"]`);
        if (scan) { scan.classList.add("isbn-scan"); scan.setAttribute("aria-label", "اسکن بارکد"); row.append(scan); }
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); lookup(input); } });
    });
    // ثبت فرم با شابکِ جستجونشده: اول جستجو، بعد ارسال
    document.addEventListener("submit", async (e) => {
        const input = e.target.querySelector && e.target.querySelector("[data-isbn-url]");
        if (!input || !input.value.trim() || input.dataset.looked === input.value || e.target.dataset.isbnWait) return;
        e.preventDefault();
        e.target.dataset.isbnWait = "1";
        await lookup(input);
        delete e.target.dataset.isbnWait;
        if (input.getAttribute("aria-invalid") !== "true") e.target.requestSubmit(e.submitter || undefined);
    }, true);

    // شابک پیدا نشد: جستجوی عنوان/نویسنده تو کتابخانه‌ی ملی؛ انتخاب یه چاپ، عنوان و نویسنده رو پر می‌کنه
    let fbSeq = 0;
    function fallback(input, scope, title, author, isbn) {
        const url = input.dataset.catalogUrl;
        if (!url) return null;
        const wrap = document.createElement("div");
        wrap.className = "isbn-fb";
        const id = (input.id || "isbn") + "-fb";
        wrap.innerHTML = '<label class="isbn-fb-label"></label><div class="isbn-row"><input type="search" enterkeyhint="search" autocomplete="off">' +
            '<button type="button" class="btn btn-secondary">بگرد</button></div><p class="isbn-fb-msg" role="status" aria-live="polite"></p><ul class="isbn-fb-list"></ul>';
        const label = wrap.querySelector("label"), q = wrap.querySelector("input"), go = wrap.querySelector("button");
        const msg = wrap.querySelector(".isbn-fb-msg"), list = wrap.querySelector("ul");
        label.textContent = "با عنوان یا نویسنده تو کتابخانه‌ی ملی بگرد و چاپ درست رو انتخاب کن:";
        label.htmlFor = q.id = id;
        q.placeholder = "مثلاً عنوان کتاب";
        q.value = (title && title.value.trim()) || "";
        const say = (text) => { msg.textContent = text; msg.hidden = !text; };
        say("");
        async function run() {
            const text = q.value.trim();
            if (text.length < 3) { say("دست‌کم ۳ حرف از عنوان یا نویسنده رو بنویس."); q.focus(); return; }
            const mine = ++fbSeq;
            list.replaceChildren();
            say("در حال جستجو تو کتابخانه‌ی ملی…");
            go.disabled = true;
            try {
                const r = await fetch(url + "?q=" + encodeURIComponent(text), {credentials: "same-origin"});
                if (mine !== fbSeq) return;
                const d = await r.json().catch(() => ({}));
                if (!r.ok) { say(d.message || (r.status === 429 ? "جستجوهات زیاد بود؛ یه دقیقه صبر کن." : "جستجو ناموفق بود؛ دستی پر کن.")); return; }
                if (!d.items || !d.items.length) { say("چیزی پیدا نشد؛ عنوان و نویسنده رو خودت بنویس (برای نفر بعدی ذخیره می‌شه)."); return; }
                say(faNum(d.items.length) + " نتیجه؛ روی چاپ درست بزن:");
                d.items.forEach((it) => {
                    const li = document.createElement("li");
                    const b = document.createElement("button");
                    b.type = "button";
                    b.className = "isbn-fb-item";
                    const t = document.createElement("strong");
                    t.textContent = it.title + (it.subtitle ? ": " + it.subtitle : "") + (it.volume ? " (" + it.volume + ")" : "");
                    const m = document.createElement("span");
                    m.textContent = [it.author, it.translators && it.translators.length ? "ترجمه‌ی " + it.translators.join("، ") : "", it.publisher,
                        it.year ? faNum(it.year) : "", it.pages ? faNum(it.pages) + " صفحه" : ""].filter(Boolean).join(" · ");
                    b.append(t, m);
                    b.addEventListener("click", () => pick(it, b));
                    li.append(b);
                    list.append(li);
                });
            } catch (_) { if (mine === fbSeq) say("ارتباط برقرار نشد؛ دوباره بزن یا دستی پر کن."); }
            finally { if (mine === fbSeq) go.disabled = false; }
        }
        function pick(it, b) {
            if (title) { title.value = it.title; title.dispatchEvent(new Event("input", {bubbles: true})); }
            if (author && it.author) { author.value = it.author; author.dispatchEvent(new Event("input", {bubbles: true})); }
            list.querySelectorAll(".isbn-fb-item").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
            say(it.isbn && it.isbn !== isbn
                ? "پر شد ✓ (این رکورد مال چاپ دیگه‌ایه؛ شابک خودت حفظ می‌شه و برای بقیه هم ذخیره می‌شه)."
                : "پر شد ✓");
            document.dispatchEvent(new CustomEvent("hv:isbn", {detail: {scope, data: Object.assign({}, it, {source: "nlai"})}}));
        }
        go.addEventListener("click", run);
        q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); run(); } });
        if (q.value.length >= 3) setTimeout(run, 0);
        return wrap;
    }

    let seq = 0;
    document.addEventListener("change", (e) => { if (e.target.matches("[data-isbn-url]")) lookup(e.target); });
    async function lookup(input) {
        if (input.dataset.looked === input.value && input.value) return;
        input.dataset.looked = input.value;
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
        const mine = ++seq;
        show(box, [line("isbn-wait", "در حال جستجو…")]);
        try {
            const r = await fetch(input.dataset.isbnUrl + "?isbn=" + encodeURIComponent(value), {credentials: "same-origin"});
            if (mine !== seq) return;
            // شکل استاندارد خط‌تیره‌دار (کاربر هر جور نوشته باشه) رو تو فیلد نشون می‌دیم
            const showStd = (d) => { if (d && d.isbn_display && isbn13(input.value) === d.isbn) { input.value = d.isbn_display; input.dataset.looked = input.value; } };
            if (r.status === 404) {
                showStd(await r.clone().json().catch(() => null));
                const items = [line("isbn-warn", "این شابک هنوز تو منبع‌های آنلاین (کتابخانه‌ی ملی و…) ثبت نشده؛ معمولاً یعنی چاپ تازه‌ست.")];
                const fb = fallback(input, scope, title, author, clean);
                items.push(fb || line("isbn-note", "عنوان و نویسنده رو خودت بنویس؛ برای نفر بعدی ذخیره می‌شه."));
                show(box, items);
                return;
            }
            if (!r.ok) { show(box, [line("isbn-err", (await r.json().catch(() => ({}))).message || "استعلام ناموفق بود؛ دستی پر کن.")]); return; }
            const d = await r.json();
            showStd(d);
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
    }
})();
