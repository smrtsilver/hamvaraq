// شابک: اعتبارسنجی رقم کنترل سمت کلاینت، استعلام از سرور (عنوان/نویسنده/ناشر…)، و نمایش وضعیت زیر فیلد
// (منتظرها، کتاب تکراری، نسخه‌ی دیگر). رویداد hv:isbn برای پیش‌نمایش زنده منتشر می‌شه.
// - شابکِ کامل و معتبر خودکار جستجو می‌شه (نیازی به زدن «جستجو» نیست؛ دکمه برای تلاش دوباره می‌مونه).
// - تا وقتی شابکی نوشته شده و جستجو نشده، عنوان و نویسنده قفل‌ان (اول اطلاعات منبع، بعد ویرایش دستی).
// - شابک نداره/پیدا نشد ← جستجوی عنوان در کتابخانه‌ی ملی.
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
    window.HVIsbn = {normalize: isbn13, lookup: (input) => lookup(input, true)};

    const fieldOf = (input) => input.closest(".field") || input.parentElement;
    const scopeOf = (input) => input.closest("[data-isbn-scope]") || input.form;
    const targets = (input) => { const s = scopeOf(input); return {scope: s, title: s.querySelector("[data-isbn-title]"), author: s.querySelector("[data-isbn-author]")}; };

    function statusBox(input) {
        const field = fieldOf(input);
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

    // ---- لودینگ روی دکمه‌ی «جستجو» (جلوی کلیک دوباره) ----
    function busy(input, on) {
        const b = input.closest(".isbn-row") && input.closest(".isbn-row").querySelector(".isbn-go");
        if (!b) return;
        b.disabled = on;
        b.classList.toggle("is-loading", on);
        b.setAttribute("aria-busy", String(on));
    }

    // ---- قفل عنوان/نویسنده تا جستجوی شابک ----
    function lock(input, on, why) {
        const {title, author} = targets(input);
        [title, author].forEach((el) => {
            if (!el) return;
            el.readOnly = on;
            el.classList.toggle("is-locked", on);
            const field = el.closest(".field");
            let note = field && field.querySelector(".lock-note");
            if (on && field) {
                if (!note) { note = document.createElement("p"); note.className = "hint lock-note"; field.append(note); }
                note.textContent = why || "اول شابک جستجو می‌شه؛ بعدش می‌تونی ویرایش کنی.";
            } else if (note) note.remove();
        });
    }
    function syncLock(input) {
        const v = input.value.trim();
        if (!v) return lock(input, false);
        if (input.dataset.looked === input.value) return;                  // جستجو شده (پیدا یا پیدا نشد)
        lock(input, true, isbn13(v) ? "در حال جستجوی شابک…" : "شابک کامل نیست؛ درستش کن یا پاکش کن تا بتونی دستی بنویسی.");
    }

    // ---- پر کردن فیلدها با رویداد تا اعتبارسنجی/پیش‌نمایش/پیش‌نویس هم بفهمن ----
    function fill(el, value) {
        if (!el || !value) return;
        if (el.value && !el.dataset.fromIsbn) return;                     // چیزی که کاربر خودش نوشته دست نمی‌خوره
        el.value = value;
        el.dataset.fromIsbn = "1";
        el.dispatchEvent(new Event("input", {bubbles: true}));
        el.dispatchEvent(new Event("change", {bubbles: true}));
    }
    document.addEventListener("input", (e) => { if (e.isTrusted && e.target.dataset && e.target.dataset.fromIsbn) delete e.target.dataset.fromIsbn; });
    // دسته‌ی پیشنهادی سرور (از موضوع/رده‌ی دیویی)؛ فقط اگه کاربر خودش دسته‌ای انتخاب نکرده
    function fillCategory(scope, cat) {
        const sel = cat && scope.querySelector("select[name$=category]");
        if (!sel || (sel.value && !sel.dataset.fromIsbn) || ![...sel.options].some((o) => o.value === String(cat.id))) return;
        sel.value = String(cat.id);
        sel.dataset.fromIsbn = "1";
        sel.dispatchEvent(new Event("change", {bubbles: true}));      // combobox.js ظاهرش رو به‌روز می‌کنه
    }

    // ---- آماده‌سازی هر فیلد شابک ----
    document.querySelectorAll("[data-isbn-url]").forEach((input) => {
        if (input.closest(".isbn-row")) return;
        const row = document.createElement("div"); row.className = "isbn-row";
        input.before(row); row.append(input);
        input.setAttribute("inputmode", "numeric");
        const b = document.createElement("button");
        b.type = "button"; b.className = "btn btn-secondary isbn-go";
        b.innerHTML = '<span class="btn-label">جستجو</span>';
        b.addEventListener("click", () => lookup(input, true));
        row.append(b);
        const scan = input.id && document.querySelector(`[data-scan][data-scan-target="${input.id}"]`);
        if (scan) { scan.classList.add("isbn-scan"); scan.setAttribute("aria-label", "اسکن بارکد"); row.append(scan); }
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); lookup(input, true); } });
        // شابک کامل و معتبر ← جستجوی خودکار (با تأخیر کوتاه تا تایپ تموم شه)
        const auto = HV.debounce(() => { if (isbn13(input.value)) lookup(input); }, 600);
        input.addEventListener("input", () => { syncLock(input); auto(); });
        // جستجو با عنوان: همیشه در دسترس (کتاب بدون شابک یا شابکی که پیدا نشد)
        if (input.dataset.catalogUrl) {
            const t = document.createElement("button");
            t.type = "button"; t.className = "link isbn-title-link";
            t.textContent = "شابک نداره یا پیدا نشد؟ با عنوان تو کتابخانه‌ی ملی بگرد";
            t.addEventListener("click", () => {
                const {scope, title, author} = targets(input);
                const box = statusBox(input);
                const fb = fallback(input, scope, title, author, isbn13(input.value));
                show(box, [fb]);
                fb.querySelector("input").focus();
            });
            fieldOf(input).querySelector(".isbn-row").after(t);
        }
        syncLock(input);
    });

    // ثبت فرم با شابکِ جستجونشده: اول جستجو، بعد ارسال
    document.addEventListener("submit", async (e) => {
        const input = e.target.querySelector && e.target.querySelector("[data-isbn-url]");
        if (!input || !input.value.trim() || input.dataset.looked === input.value || e.target.dataset.isbnWait) return;
        e.preventDefault();
        e.target.dataset.isbnWait = "1";
        await lookup(input, true);
        delete e.target.dataset.isbnWait;
        if (input.getAttribute("aria-invalid") !== "true") e.target.requestSubmit(e.submitter || undefined);
    }, true);

    // ---- جستجوی عنوان/نویسنده تو کتابخانه‌ی ملی؛ انتخاب یه چاپ، عنوان و نویسنده رو پر می‌کنه ----
    let fbSeq = 0;
    function fallback(input, scope, title, author, isbn) {
        const url = input.dataset.catalogUrl;
        if (!url) return null;
        const wrap = document.createElement("div");
        wrap.className = "isbn-fb";
        const id = (input.id || "isbn") + "-fb";
        wrap.innerHTML = '<label class="isbn-fb-label"></label><div class="isbn-row"><input type="search" enterkeyhint="search" autocomplete="off">' +
            '<button type="button" class="btn btn-secondary"><span class="btn-label">بگرد</span></button></div><p class="isbn-fb-msg" role="status" aria-live="polite"></p><ul class="isbn-fb-list"></ul>';
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
            go.disabled = true; go.classList.add("is-loading");
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
            finally { if (mine === fbSeq) { go.disabled = false; go.classList.remove("is-loading"); } }
        }
        function pick(it, b) {
            lock(input, false);
            [[title, it.title], [author, it.author]].forEach(([el, v]) => { if (el && v) { delete el.dataset.fromIsbn; el.value = ""; fill(el, v); } });
            // شابک خالی یا ناقص بود ← شابک همین چاپ؛ شابکِ معتبرِ خود کاربر (چاپ دیگه) دست نمی‌خوره
            if (it.isbn && !isbn13(input.value)) {
                input.value = it.isbn;
                input.dataset.looked = input.value;            // همین الان اطلاعاتش رو داریم؛ دوباره استعلام لازم نیست
                input.removeAttribute("aria-invalid");
                input.dispatchEvent(new Event("change", {bubbles: false}));
            }
            fillCategory(scope, it.category);
            list.querySelectorAll(".isbn-fb-item").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
            say(it.isbn && isbn && it.isbn !== isbn
                ? "پر شد ✓ (این رکورد مال چاپ دیگه‌ایه؛ شابک خودت حفظ می‌شه و برای بقیه هم ذخیره می‌شه)."
                : "پر شد ✓");
            document.dispatchEvent(new CustomEvent("hv:isbn", {detail: {scope, data: Object.assign({}, it, {source: "nlai"})}}));
        }
        go.addEventListener("click", run);
        q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); run(); } });
        if (q.value.length >= 3) setTimeout(run, 0);
        return wrap;
    }

    // ---- عکس جلد منبع (خانه‌ی کتاب/Open Library) از مسیر امن خود سایت؛ با یه لمس جلد کتاب می‌شه ----
    function coverOffer(input, scope, d) {
        const base = input.dataset.coverImageUrl;
        if (!base) return null;
        const src = base.replace("ISBN", d.isbn);
        const file = scope.querySelector("input[type=file][name=cover]");
        const wrap = document.createElement("div");
        wrap.className = "isbn-cover";
        const img = document.createElement("img");
        img.alt = "جلد «" + d.title + "»";
        img.loading = "lazy";
        img.width = 72; img.height = 104;
        img.onerror = () => wrap.remove();                     // عکس منبع خراب بود: پیشنهادی نشون نمی‌دیم
        img.src = src;
        const side = document.createElement("div");
        const note = document.createElement("p");
        note.textContent = "عکس جلد این چاپ پیدا شد.";
        side.append(note);
        if (file) {
            const b = document.createElement("button");
            b.type = "button"; b.className = "btn btn-sm";
            b.innerHTML = '<span class="btn-label">همین عکس جلد باشه</span>';
            b.addEventListener("click", async () => {
                b.disabled = true; b.classList.add("is-loading");
                try {
                    const r = await fetch(src, {credentials: "same-origin"});
                    if (!r.ok) throw new Error("cover");
                    const blob = await r.blob();
                    const ext = (blob.type.split("/")[1] || "jpg").replace("jpeg", "jpg");
                    const dt = new DataTransfer();
                    dt.items.add(new File([blob], "cover-" + d.isbn + "." + ext, {type: blob.type, lastModified: Date.now()}));
                    file.files = dt.files;
                    const photoMode = scope.querySelector("input[name=cover_mode][value=photo]");
                    if (photoMode && !photoMode.checked) { photoMode.checked = true; photoMode.dispatchEvent(new Event("change", {bubbles: true})); }
                    file.dispatchEvent(new Event("change", {bubbles: true}));   // فشرده‌سازی و پیش‌نمایش
                    note.textContent = "✓ به‌عنوان عکس جلد گذاشته شد (تو بخش «جلد» می‌تونی عوضش کنی).";
                    b.remove();
                } catch (_) {
                    note.textContent = "عکس گرفته نشد؛ می‌تونی خودت عکس بگیری یا طرح آماده انتخاب کنی.";
                    b.disabled = false; b.classList.remove("is-loading");
                }
            });
            side.append(b);
        }
        wrap.append(img, side);
        return wrap;
    }

    // ---- استعلام ----
    let seq = 0;
    document.addEventListener("change", (e) => { if (e.target.matches && e.target.matches("[data-isbn-url]")) lookup(e.target); });
    async function lookup(input, force) {
        if (!force && input.dataset.looked === input.value && input.value) return;
        const {scope, title, author} = targets(input);
        const box = statusBox(input);
        const value = input.value.trim();
        input.removeAttribute("aria-invalid");
        if (!value) {
            input.dataset.looked = "";
            lock(input, false);
            show(box, []);
            document.dispatchEvent(new CustomEvent("hv:isbn", {detail: {scope, data: null}}));
            return;
        }
        const clean = isbn13(value);
        if (!clean) {
            input.setAttribute("aria-invalid", "true");
            const digits = toEn(value).replace(/[\s\-]/g, "");
            show(box, [line("isbn-err", /^\d{10}$|^\d{9}X$|^\d{13}$/i.test(digits) ? "رقم کنترل این شابک درست نیست؛ یه بار دیگه با پشت کتاب چک کن." : "شابک باید ۱۰ یا ۱۳ رقم باشه.")]);
            syncLock(input);
            return;
        }
        const mine = ++seq;
        input.dataset.looked = input.value;
        busy(input, true);
        lock(input, true, "در حال جستجوی شابک…");
        show(box, [line("isbn-wait", "در حال جستجو تو کتابخانه‌ی ملی و خانه‌ی کتاب…")]);
        const done = () => { if (mine === seq) { busy(input, false); lock(input, false); } };
        try {
            const r = await fetch(input.dataset.isbnUrl + "?isbn=" + encodeURIComponent(value), {credentials: "same-origin"});
            if (mine !== seq) return;
            // شکل استاندارد خط‌تیره‌دار (کاربر هر جور نوشته باشه) رو تو فیلد نشون می‌دیم
            const showStd = (d) => { if (d && d.isbn_display && isbn13(input.value) === d.isbn) { input.value = d.isbn_display; input.dataset.looked = input.value; } };
            if (r.status === 404) {
                showStd(await r.clone().json().catch(() => null));
                const items = [line("isbn-warn", "این شابک هنوز تو منبع‌های آنلاین (کتابخانه‌ی ملی، خانه‌ی کتاب…) ثبت نشده؛ عنوان رو پایین جستجو کن یا خودت بنویس.")];
                const fb = fallback(input, scope, title, author, clean);
                items.push(fb || line("isbn-note", "عنوان و نویسنده رو خودت بنویس؛ برای نفر بعدی ذخیره می‌شه."));
                show(box, items);
                return;
            }
            if (!r.ok) {
                const d = await r.json().catch(() => ({}));
                show(box, [line("isbn-err", r.status === 429 ? "جستجوهات زیاد بود؛ یه دقیقه صبر کن." : d.message || "استعلام ناموفق بود؛ دوباره «جستجو» رو بزن یا دستی پر کن.")]);
                input.dataset.looked = "";
                return;
            }
            const d = await r.json();
            showStd(d);
            lock(input, false);
            fill(title, d.title);
            fill(author, d.author);
            fillCategory(scope, d.category);
            const items = [];
            const meta = [d.translators && d.translators.length ? "ترجمه‌ی " + d.translators.join("، ") : "", d.publisher,
                d.year ? faNum(d.year) + (d.year_calendar === "jalali" ? " شمسی" : "") : "", d.pages ? faNum(d.pages) + " صفحه" : ""].filter(Boolean).join(" · ");
            items.push(line("isbn-ok", (d.confidence >= 40 && d.source !== "user" ? "✓ مشخصات پیدا شد" : "مشخصات ثبت‌شده توسط کاربران") + (meta ? ": " + meta : "")));
            if (d.mine) items.push(line("isbn-warn", "این کتاب (همین شابک) رو قبلاً ثبت کردی؛ مطمئنی دوباره می‌خوای؟"));
            if (d.demand) items.push(line("isbn-demand", faNum(d.demand) + " نفر دنبال این کتاب بوده‌ن؛ ثبتش شانس مبادله‌ات رو بالا می‌بره."));
            if (d.available_elsewhere) items.push(line("isbn-note", faNum(d.available_elsewhere) + " نسخه‌ی دیگه‌ی همین کتاب الان تو هم‌ورق موجوده."));
            const cover = d.cover_url && coverOffer(input, scope, d);
            if (cover) items.push(cover);
            show(box, items);
            document.dispatchEvent(new CustomEvent("hv:isbn", {detail: {scope, data: d}}));
        } catch (_) {
            if (mine === seq) {
                show(box, [line("isbn-err", "ارتباط برقرار نشد؛ دوباره «جستجو» رو بزن یا عنوان و نویسنده رو دستی بنویس.")]);
                input.dataset.looked = "";
            }
        } finally { done(); }
    }
})();
