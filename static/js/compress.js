// فشرده‌سازی عکس سمت کلاینت پیش از آپلود: حداکثر ۱۶۰۰ پیکسل، WebP (یا JPEG) با کیفیت ۸۲ (اینترنت ضعیف و حجم آپلود کمتر).
// فایل‌هایی که مرورگر نمی‌تونه باز کنه (مثل HEIC) یا کوچک‌ترن همون‌طور می‌مونن؛ سرور خودش هم دوباره پردازش می‌کنه.
(() => {
    const MAX = 1600, QUALITY = 0.82, SKIP_BELOW = 300 * 1024;
    const fa = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
    const size = (b) => (b >= 1048576 ? fa((b / 1048576).toFixed(1)) + " مگابایت" : fa(Math.round(b / 1024)) + " کیلوبایت");

    async function shrink(file) {
        if (!/^image\/(jpeg|png|webp)$/.test(file.type) || file.size < SKIP_BELOW) return file;
        let bmp;
        try { bmp = await createImageBitmap(file); } catch (_) { return file; }
        const k = Math.min(1, MAX / Math.max(bmp.width, bmp.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(bmp.width * k);
        canvas.height = Math.round(bmp.height * k);
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
        bmp.close && bmp.close();
        // اول WebP (کوچک‌تر)؛ اگه مرورگر پشتیبانی نکرد (type برنمی‌گرده webp) JPEG
        let blob = await new Promise((r) => canvas.toBlob(r, "image/webp", QUALITY));
        let ext = "webp";
        if (!blob || blob.type !== "image/webp") {
            blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", QUALITY));
            ext = "jpg";
        }
        if (!blob || blob.size >= file.size) return file;
        return new File([blob], file.name.replace(/\.\w+$/, "") + "." + ext, {type: blob.type, lastModified: Date.now()});
    }

    document.addEventListener("change", async (e) => {
        const input = e.target;
        if (!input.matches('input[type="file"][accept*="image"], input[type="file"][data-compress]') || !input.files || !input.files.length || input.dataset.compressing) return;
        input.dataset.compressing = "1";
        try {
            const before = [...input.files].reduce((s, f) => s + f.size, 0);
            const out = await Promise.all([...input.files].map(shrink));
            const after = out.reduce((s, f) => s + f.size, 0);
            if (after < before) {
                const dt = new DataTransfer();
                out.forEach((f) => dt.items.add(f));
                input.files = dt.files;
                let note = input.closest(".field").querySelector(".compress-note");
                if (!note) { note = document.createElement("p"); note.className = "hint compress-note"; note.setAttribute("role", "status"); input.closest(".field").append(note); }
                note.textContent = `عکس فشرده شد: ${size(before)} ← ${size(after)}`;
            }
        } finally { delete input.dataset.compressing; }
    });
})();
