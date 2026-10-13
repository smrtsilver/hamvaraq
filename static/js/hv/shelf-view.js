// قفسه‌ی من: نمایش قفسه/فهرست (به خاطر سپرده می‌شه) و فیلتر وضعیت با انیمیشن FLIP (فقط transform و opacity).
(() => {
    const root = document.querySelector("[data-shelf-views]");
    const tabs = document.querySelector("[data-shelf-tabs]");
    if (!root || !tabs) return;
    const seg = document.querySelector("[data-view-seg]");
    const shelf = root.querySelector("[data-wshelf]");
    const empty = root.querySelector("[data-filter-empty]");
    const reduce = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const KEY = "hv-shelf-view";
    const store = {get() { try { return localStorage.getItem(KEY); } catch (_) { return null; } },
        set(v) { try { localStorage.setItem(KEY, v); } catch (_) { /* حالت خصوصی */ } }};

    // ---- قفسه / فهرست ----
    function setView(v) {
        root.dataset.view = v;
        seg.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === v)));
        if (v === "shelf" && shelf) shelf.dispatchEvent(new Event("hv:wshelf-update"));
    }
    if (seg) {
        seg.hidden = false;
        setView(store.get() || seg.dataset.default || "shelf");
        seg.addEventListener("click", (e) => {
            const b = e.target.closest("[data-view]");
            if (!b) return;
            store.set(b.dataset.view);
            setView(b.dataset.view);
        });
    }

    // ---- فیلتر ----
    // قفسه‌ی بدون کتابِ قابل‌نمایش: طبقه‌های خالی + پیام روی خود قفسه (و پیام متنی در حالت فهرست)
    function syncEmpty(items) {
        const none = !items.some((el) => !el.classList.contains("is-out"));
        if (empty) empty.hidden = !none;
        root.classList.toggle("is-empty", none);
    }
    const match = (el, f) => !f || (f === "swap" ? el.dataset.swap === "1" : el.dataset.rs === f);
    function filter(f) {
        const container = root.dataset.view === "list" ? root.querySelector(".shelf-list") : root.querySelector(".wshelf-books");
        const items = [...container.querySelectorAll("[data-item]")];
        const other = [...root.querySelectorAll("[data-item]")].filter((el) => !container.contains(el));
        other.forEach((el) => el.classList.toggle("is-out", !match(el, f)));
        const animate = !reduce() && "animate" in Element.prototype;
        const before = new Map();
        if (animate) items.forEach((el) => { if (!el.classList.contains("is-out")) before.set(el, el.getBoundingClientRect()); });
        const leaving = items.filter((el) => !el.classList.contains("is-out") && !match(el, f));
        const entering = items.filter((el) => el.classList.contains("is-out") && match(el, f));
        const finish = () => {
            leaving.forEach((el) => el.classList.add("is-out"));
            entering.forEach((el) => el.classList.remove("is-out"));
            syncEmpty(items);
            if (shelf) shelf.dispatchEvent(new Event("hv:wshelf-update"));
            if (!animate) return;
            items.forEach((el) => {
                if (el.classList.contains("is-out")) return;
                const a = before.get(el), b = el.getBoundingClientRect();
                if (a) {
                    const dx = a.left - b.left, dy = a.top - b.top;
                    if (dx || dy) el.animate([{transform: `translate(${dx}px,${dy}px)`}, {transform: "none"}], {duration: 320, easing: "cubic-bezier(.2,.8,.2,1)"});
                } else {
                    el.animate([{opacity: 0, transform: "translateY(18px) scale(.94)"}, {opacity: 1, transform: "none"}],
                        {duration: 300, delay: Math.min(entering.indexOf(el), 12) * 22, easing: "cubic-bezier(.2,.8,.2,1)", fill: "backwards"});
                }
            });
        };
        if (animate && leaving.length) {
            Promise.all(leaving.map((el) => el.animate([{opacity: 1, transform: "none"}, {opacity: 0, transform: "translateY(-10px) scale(.92)"}],
                {duration: 160, easing: "ease-in", fill: "forwards"}).finished.then((anim) => anim))).then((anims) => {
                finish();
                anims.forEach((a) => a.cancel());
            });
        } else finish();
    }
    syncEmpty([...root.querySelectorAll(root.dataset.view === "list" ? ".shelf-list [data-item]" : ".wshelf-books [data-item]")]);
    tabs.addEventListener("click", (e) => {
        const a = e.target.closest("[data-filter]");
        if (!a || e.metaKey || e.ctrlKey) return;
        e.preventDefault();
        tabs.querySelectorAll("[data-filter]").forEach((x) => x.toggleAttribute("aria-current", x === a));
        tabs.querySelectorAll("[aria-current]").forEach((x) => x.setAttribute("aria-current", "page"));
        const f = a.dataset.filter;
        history.replaceState(null, "", f ? `?s=${f}` : location.pathname);
        filter(f);
    });
})();
