// پیش‌نمایش زنده‌ی کارت کتاب + امتیاز کیفیت آگهی تو فرم ثبت/ویرایش (وزن‌ها از سرور: books/quality.py).
(() => {
    const form = document.querySelector("form[data-preview]");
    if (!form) return;
    const W = JSON.parse(document.getElementById("hv-quality").textContent);
    const $ = (sel) => document.querySelector(sel);
    const el = {
        title: $('[data-lp="title"]'), author: $('[data-lp="author"]'), cond: $('[data-lp="condition"]'), city: $('[data-lp="city"]'),
        img: $(".lp-cover img"), ph: $(".lp-ph"), bar: $(".lp-quality .meter i"), score: $('[data-lp="score"]'), tips: $('[data-lp="tips"]'),
    };
    const f = (n) => form.elements[n];
    let isbnData = null, coverUrl = "";
    const fa = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
    const selText = (s) => (s && s.selectedIndex >= 0 && s.value ? s.options[s.selectedIndex].text : "");

    function update() {
        el.title.textContent = f("title").value.trim() || "عنوان کتاب";
        el.author.textContent = f("author").value.trim() || "نویسنده";
        el.cond.textContent = selText(f("condition")) || "";
        el.city.textContent = selText(f("city")) || "";
        const hasCover = !!coverUrl || form.dataset.existingCover === "1";
        if (coverUrl) { el.img.src = coverUrl; el.img.hidden = false; el.ph.hidden = true; }
        const hasPhotos = f("extra_photos") && f("extra_photos").files && f("extra_photos").files.length > 0;
        const validIsbn = window.HVIsbn && f("isbn") && window.HVIsbn.normalize(f("isbn").value);
        let score = W.base;
        const tips = [];
        if (hasCover) score += W.cover; else tips.push("عکس جلد اضافه کن؛ مهم‌ترین عامل.");
        if (f("description").value.trim().length >= 20) score += W.description; else tips.push("چند جمله درباره‌ی وضعیت کتاب بنویس.");
        if (f("category") && f("category").value) score += W.category; else tips.push("دسته‌ی کتاب رو انتخاب کن.");
        if (validIsbn && isbnData && isbnData.source !== "user") score += W.edition_backed;
        else if (validIsbn) { score += W.edition_user; tips.push("شابک از منبع معتبر تأیید نشد؛ دوباره چک کن."); }
        else tips.push("شابک رو بنویس یا اسکن کن.");
        if (hasPhotos) score += W.photos; else tips.push("یه عکس از پشت جلد یا داخل کتاب هم اضافه کن.");
        el.bar.style.width = score + "%";
        el.score.textContent = "کیفیت آگهی: " + fa(score) + "٪ · " + (score >= 85 ? "عالی" : score >= 65 ? "خوب" : "قابل بهبود");
        el.tips.replaceChildren(...tips.slice(0, 3).map((t) => { const li = document.createElement("li"); li.textContent = t; return li; }));
    }

    form.addEventListener("input", update);
    form.addEventListener("change", (e) => {
        if (e.target.name === "cover" && e.target.files && e.target.files[0]) {
            if (coverUrl) URL.revokeObjectURL(coverUrl);
            coverUrl = URL.createObjectURL(e.target.files[0]);
        }
        update();
    });
    document.addEventListener("hv:isbn", (e) => { if (e.detail.scope === form) { isbnData = e.detail.data; update(); } });
    update();
})();
