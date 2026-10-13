// پیشنهاد عنوان/نویسنده از کتاب‌های موجود هنگام تایپ؛ انتخاب عنوان، نویسنده و شابک رو هم (اگه خالی باشن) پر می‌کنه.
(() => {
    function attach(input) {
        const kind = input.dataset.suggest;
        const url = input.dataset.suggestUrl;
        const scope = input.closest("[data-isbn-scope]") || input.form;
        const list = document.createElement("ul");
        list.className = "combo-list";
        list.hidden = true;
        list.setAttribute("role", "listbox");
        const wrap = document.createElement("div");
        wrap.className = "combo";
        input.before(wrap);
        wrap.append(input, list);
        input.setAttribute("role", "combobox");
        input.setAttribute("aria-autocomplete", "list");
        input.setAttribute("aria-expanded", "false");
        let timer = null, seq = 0;

        const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); };
        const pick = (item) => {
            if (kind === "title") {
                input.value = item.title;
                const author = scope.querySelector("[data-isbn-author]");
                const isbn = scope.querySelector("[data-isbn-url]");
                if (author && !author.value) author.value = item.author;
                if (isbn && !isbn.value && item.isbn) isbn.value = item.isbn;
            } else input.value = item.author;
            close();
        };
        input.addEventListener("input", (e) => {
            if (!e.isTrusted) return;          // پر شدن خودکار (شابک/پیش‌نویس) منوی پیشنهاد رو باز نکنه
            clearTimeout(timer);
            const q = input.value.trim();
            if (q.length < 2) return close();
            timer = setTimeout(async () => {
                const mine = ++seq;
                try {
                    const r = await fetch(`${url}?kind=${kind}&q=${encodeURIComponent(q)}`, {credentials: "same-origin"});
                    if (!r.ok || mine !== seq) return;
                    const {items} = await r.json();
                    list.replaceChildren(...items.map((item) => {
                        const li = document.createElement("li");
                        li.setAttribute("role", "option");
                        li.textContent = kind === "title" ? `${item.title} — ${item.author}${item.publisher ? " · " + item.publisher : ""}${item.year ? " (" + String(item.year).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]) + ")" : ""}` : `${item.author}${item.count ? " · " + String(item.count).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]) + " کتاب" : ""}`;
                        li.addEventListener("mousedown", (e) => { e.preventDefault(); pick(item); });
                        return li;
                    }));
                    list.hidden = !items.length;
                    input.setAttribute("aria-expanded", String(!list.hidden));
                } catch (_) { /* پیشنهاد اختیاریه */ }
            }, 250);
        });
        input.addEventListener("blur", () => setTimeout(close, 150));
        input.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    }
    const init = () => document.querySelectorAll("input[data-suggest]").forEach(attach);
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
