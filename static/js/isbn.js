// با خروج از فیلد شابک، عنوان و نویسنده (اگه خالی باشن) از سرور پر می‌شه.
document.addEventListener("change", async (e) => {
    const input = e.target;
    if (!input.matches("[data-isbn-url]") || !input.value.trim()) return;
    const scope = input.closest("[data-isbn-scope]") || input.form;
    const title = scope.querySelector("[data-isbn-title]");
    const author = scope.querySelector("[data-isbn-author]");
    try {
        const r = await fetch(input.dataset.isbnUrl + "?isbn=" + encodeURIComponent(input.value), {credentials: "same-origin"});
        if (!r.ok) return;
        const d = await r.json();
        if (title && !title.value) title.value = d.title;
        if (author && !author.value) author.value = d.author;
    } catch (_) { /* پر کردن دستی هنوز ممکنه */ }
});
