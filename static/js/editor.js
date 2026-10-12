// ویرایشگر معرفی کتاب: دکمه‌های قالب (markdown ساده) و پیش‌نمایش زنده از سرور (همون رندر امن صفحه‌ی نوشته).
(() => {
    const root = document.querySelector("[data-editor-root]");
    if (!root) return;
    const ta = root.querySelector("textarea");
    const preview = root.querySelector("[data-preview]");
    const toggle = root.querySelector("[data-preview-toggle]");
    const csrf = () => (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";

    function wrap(before, after, placeholder) {
        const {selectionStart: s, selectionEnd: e, value} = ta;
        const chosen = value.slice(s, e) || placeholder;
        ta.value = value.slice(0, s) + before + chosen + after + value.slice(e);
        ta.focus();
        ta.setSelectionRange(s + before.length, s + before.length + chosen.length);
    }
    function linePrefix(prefix) {
        const {selectionStart: s, value} = ta;
        const start = value.lastIndexOf("\n", s - 1) + 1;
        ta.value = value.slice(0, start) + prefix + value.slice(start);
        ta.focus();
        ta.setSelectionRange(s + prefix.length, s + prefix.length);
    }
    const actions = {
        bold: () => wrap("**", "**", "متن پررنگ"), italic: () => wrap("*", "*", "متن مورب"),
        heading: () => linePrefix("## "), quote: () => linePrefix("> "), list: () => linePrefix("- "),
        link: () => { const url = prompt("آدرس لینک (با https://):", "https://"); if (url && /^https?:\/\//.test(url)) wrap("[", `](${url})`, "متن لینک"); },
    };
    root.querySelectorAll("[data-md]").forEach((b) => b.addEventListener("click", () => actions[b.dataset.md]()));

    toggle.addEventListener("click", async () => {
        const on = toggle.getAttribute("aria-pressed") !== "true";
        toggle.setAttribute("aria-pressed", String(on));
        toggle.textContent = on ? "ویرایش" : "پیش‌نمایش";
        ta.hidden = on;
        preview.hidden = !on;
        if (!on) return;
        preview.textContent = "در حال ساخت پیش‌نمایش…";
        const body = new FormData();
        body.append("body", ta.value);
        try {
            const r = await fetch(root.dataset.previewUrl, {method: "POST", body, credentials: "same-origin", headers: {"X-CSRFToken": csrf()}});
            if (!r.ok) throw new Error();
            preview.innerHTML = (await r.json()).html || "<p class='muted'>چیزی ننوشتی.</p>";   // خروجی سرور escape‌شده‌ی امنه
        } catch (_) { preview.textContent = "پیش‌نمایش ساخته نشد."; }
    });
})();
