// فرم‌ها: انتخاب فایل فارسی (متن پیش‌فرض مرورگر انگلیسیه) و نمایش دلیل فقط برای دیسلایک.
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("input[type=file]").forEach((input) => {
        const wrap = document.createElement("span");
        wrap.className = "file-pick";
        const button = document.createElement("span");
        button.className = "btn btn-sm btn-secondary";
        button.textContent = input.multiple ? "انتخاب عکس‌ها" : "انتخاب عکس";
        const label = document.createElement("span");
        label.className = "file-name";
        label.textContent = "هنوز فایلی انتخاب نشده";
        input.before(wrap);
        wrap.append(button, label, input);
        input.addEventListener("change", () => {
            const n = input.files.length;
            label.textContent = n === 0 ? "هنوز فایلی انتخاب نشده"
                : n === 1 ? input.files[0].name : n.toLocaleString("fa-IR") + " فایل انتخاب شد";
        });
    });

    document.querySelectorAll("form").forEach((form) => {
        const radios = form.querySelectorAll("input[type=radio][name=like]");
        const reason = form.querySelector("[name=reason]");
        const comment = form.querySelector("[name=comment]");
        if (!radios.length || !reason) return;
        const rows = [reason, comment].filter(Boolean).map((el) => el.closest(".field") || el.closest("div"));
        const sync = () => {
            const dislike = [...radios].some((r) => r.checked && r.value === "0");
            rows.forEach((row) => (row.hidden = !dislike));
        };
        radios.forEach((r) => r.addEventListener("change", sync));
        sync();
    });
});
