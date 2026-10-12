// پنجره‌ی جستجو: دکمه‌ی جستجو (یا کلید «/» و Ctrl+K) یه پنجره‌ی بزرگ باز می‌کنه و نتیجه‌ها زنده نشون داده می‌شن.
(() => {
    const dialog = document.getElementById("search-dialog");
    if (!dialog || typeof dialog.showModal !== "function") return; // بدون پشتیبانی، لینک عادی به فهرست کتاب‌ها می‌ره
    const input = dialog.querySelector("#sd-input");
    const body = dialog.querySelector("#sd-results");
    const form = dialog.querySelector("form");
    const url = dialog.dataset.quickUrl;
    const KEY = "hv-recent-search";
    let timer = null, seq = 0, active = -1;

    const recent = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (_) { return []; } };
    const remember = (q) => {
        if (!q) return;
        try { localStorage.setItem(KEY, JSON.stringify([q, ...recent().filter((x) => x !== q)].slice(0, 6))); } catch (_) { /* اختیاریه */ }
    };
    const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text) n.textContent = text; return n; };
    const toFa = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
    const links = () => [...body.querySelectorAll("a.sd-item, a.sd-all")];
    const setActive = (i) => {
        const items = links();
        items.forEach((a) => a.classList.remove("on"));
        active = items.length ? (i + items.length) % items.length : -1;
        if (active >= 0) { items[active].classList.add("on"); items[active].scrollIntoView({block: "nearest"}); }
    };

    function showHint() {
        const items = recent();
        const wrap = el("div", "sd-hint");
        if (items.length) {
            wrap.append(el("p", "sd-title", "جستجوهای اخیر"));
            const row = el("div", "sd-chips");
            items.forEach((q) => {
                const b = el("button", "chip", q);
                b.type = "button";
                b.addEventListener("click", () => { input.value = q; search(); input.focus(); });
                row.append(b);
            });
            wrap.append(row);
        }
        wrap.append(el("p", "muted", "با تایپ، نتیجه‌ها همین‌جا نشون داده می‌شن؛ با کلید ورود همه‌ی نتیجه‌ها رو می‌بینی."));
        const all = el("a", "btn btn-secondary btn-sm", "دیدن همه‌ی کتاب‌ها");
        all.href = form.action;
        wrap.append(all);
        body.replaceChildren(wrap);
        input.setAttribute("aria-expanded", "false");
    }

    function render(d, q) {
        const frag = document.createDocumentFragment();
        if (d.books.length) {
            frag.append(el("p", "sd-title", "کتاب‌ها"));
            d.books.forEach((b) => {
                const a = el("a", "sd-item"); a.href = b.url;
                const img = el("span", "sd-thumb");
                if (b.thumb) { const i = new Image(); i.src = b.thumb; i.alt = ""; i.loading = "lazy"; img.append(i); }
                const txt = el("span", "sd-text");
                txt.append(el("strong", "", b.title), el("small", "", [b.author, b.city].filter(Boolean).join(" · ")));
                a.append(img, txt);
                if (!b.free) a.append(el("span", "pill", "رزرو"));
                frag.append(a);
            });
        }
        if (d.posts.length) {
            frag.append(el("p", "sd-title", "معرفی‌ها"));
            d.posts.forEach((p) => {
                const a = el("a", "sd-item"); a.href = p.url;
                const txt = el("span", "sd-text");
                txt.append(el("strong", "", p.title), el("small", "", "از " + p.by));
                a.append(el("span", "sd-thumb sd-note"), txt);
                frag.append(a);
            });
        }
        if (!d.books.length && !d.posts.length) {
            const empty = el("div", "sd-hint");
            empty.append(el("p", "sd-title", "چیزی پیدا نشد"), el("p", "muted", "عبارت کوتاه‌تر یا نام نویسنده رو امتحان کن."));
            frag.append(empty);
        }
        const all = el("a", "sd-all", d.total ? `دیدن همه‌ی ${toFa(d.total)} نتیجه برای «${q}»` : `جستجوی «${q}» در همه‌ی کتاب‌ها`);
        all.href = `${form.action}?q=${encodeURIComponent(q)}`;
        frag.append(all);
        body.replaceChildren(frag);
        input.setAttribute("aria-expanded", "true");
        setActive(-1);
    }

    async function search() {
        const q = input.value.trim();
        if (q.length < 2) return showHint();
        const mine = ++seq;
        try {
            const r = await fetch(`${url}?q=${encodeURIComponent(q)}`, {credentials: "same-origin"});
            if (!r.ok || mine !== seq) return;
            render(await r.json(), q);
        } catch (_) { /* با Enter به صفحه‌ی نتیجه می‌ره */ }
    }

    const open = () => { if (!dialog.open) { dialog.showModal(); showHint(); } input.focus(); input.select(); };
    document.addEventListener("click", (e) => {
        const t = e.target.closest("[data-search-open]");
        if (t && !e.metaKey && !e.ctrlKey) { e.preventDefault(); open(); }
        if (e.target.closest("[data-search-close]") || e.target === dialog) dialog.close();
    });
    document.addEventListener("keydown", (e) => {
        const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
        if ((e.key === "/" && !typing) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k")) { e.preventDefault(); open(); }
    });
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 180); });
    input.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown") { e.preventDefault(); setActive(active + 1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); setActive(active - 1); }
        else if (e.key === "Enter" && active >= 0) { e.preventDefault(); links()[active].click(); }
    });
    form.addEventListener("submit", () => remember(input.value.trim()));
    body.addEventListener("click", (e) => { if (e.target.closest("a.sd-item, a.sd-all")) remember(input.value.trim()); });
    dialog.addEventListener("close", () => { input.value = ""; });
})();
