// ثبت سرویس‌ورکر، اعلام نسخه‌ی تازه، و پیشنهاد نصب (اندروید/دسکتاپ) یا راهنمای نصب (آیفون).
(() => {
    const standalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
    const store = {
        get: (k) => { try { return localStorage.getItem(k); } catch (_) { return null; } },
        set: (k, v) => { try { localStorage.setItem(k, v); } catch (_) { /* بسته */ } },
    };

    function bar(html, cls) {
        const el = document.createElement("div");
        el.className = `pwa-bar ${cls || ""}`;
        el.setAttribute("role", "status");
        el.innerHTML = html;
        document.body.append(el);
        requestAnimationFrame(() => el.classList.add("show"));
        return el;
    }

    // ---- سرویس‌ورکر و به‌روزرسانی ----
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", async () => {
            let reg;
            try { reg = await navigator.serviceWorker.register("/sw.js"); } catch (_) { return; }
            // نسخه‌ی تازه خودش فعال می‌شه (sw.js: skipWaiting) و کش‌های قبلی همون لحظه پاک می‌شن؛ صفحه‌ی بعدی خودش نسخه‌ی تازه‌ست.
            // صفحه‌ی باز فقط وقتی ریلود می‌شه که کاربر از تب بیرون رفته (وسط اسکن/تایپ نمی‌پره) و فرم نیمه‌پری نداره.
            const hadController = !!navigator.serviceWorker.controller;
            if (reg.waiting) reg.waiting.postMessage("SKIP_WAITING");          // سرویس‌ورکرهای قدیمی که منتظر تأیید می‌موندن
            let pending = false, reloaded = false;
            const reloadIfSafe = () => {
                if (!pending || reloaded || !document.hidden || document.querySelector("form[data-dirty], dialog[open]")) return;
                reloaded = true;
                location.reload();
            };
            navigator.serviceWorker.addEventListener("controllerchange", () => {
                if (!hadController) return;                                    // اولین نصب: چیزی برای تازه کردن نیست
                pending = true;
                reloadIfSafe();
            });
            document.addEventListener("visibilitychange", reloadIfSafe);
            setInterval(() => reg.update().catch(() => {}), 30 * 60 * 1000);   // تب‌هایی که مدت‌ها بازن هم نسخه‌ی تازه رو بگیرن
        });
    }

    // ---- «به نسخه‌ی تازه به‌روز شد» (یک بار، بعد از عوض شدن نسخه) ----
    const ver = document.body.dataset.version;
    const seen = store.get("hv-version");
    if (ver && seen && seen !== ver) {
        const el = bar(`<span>هم‌ورق به نسخه‌ی <b dir="ltr">${ver}</b> به‌روز شد.</span><span><a class="btn btn-sm" href="/changelog/">چه چیزهایی عوض شد؟</a> <button type="button" class="btn btn-sm btn-ghost" data-ok>بستن</button></span>`, "update");
        el.querySelector("[data-ok]").addEventListener("click", () => el.remove());
    }
    if (ver) store.set("hv-version", ver);

    // ---- پیشنهاد نصب ----
    if (standalone()) return;
    const DISMISS = "hv-install-dismissed-until";
    const snoozed = () => Number(store.get(DISMISS) || 0) > Date.now();
    const snooze = (days) => store.set(DISMISS, String(Date.now() + days * 864e5));
    // شمارش بازدید پایدار (نه فقط همین نشست)؛ پیشنهاد از بازدید دوم به بعد
    const visits = Number(store.get("hv-visits") || 0) + 1;
    store.set("hv-visits", String(visits));
    const ready = () => visits >= 2;   // اولین بازدید مزاحم نمی‌شیم

    let deferred = null, shown = null;
    window.addEventListener("beforeinstallprompt", (e) => {
        e.preventDefault();
        deferred = e;
        if (snoozed() || !ready()) return;
        shown = bar('<span><strong>هم‌ورق رو نصب کن</strong><br><small>مثل یه اپ باز می‌شه و اعلان می‌گیری.</small></span><span><button type="button" class="btn btn-sm" data-install>نصب</button> <button type="button" class="btn btn-sm btn-ghost" data-later>بعداً</button></span>', "install");
        shown.querySelector("[data-install]").addEventListener("click", async () => {
            shown.remove();
            deferred.prompt();
            const choice = await deferred.userChoice;
            if (choice.outcome !== "accepted") snooze(30);
            deferred = null;
        });
        shown.querySelector("[data-later]").addEventListener("click", () => { snooze(30); shown.remove(); });
    });
    window.addEventListener("appinstalled", () => { if (shown) shown.remove(); });

    // آیفون: نصب خودکار نداریم؛ راهنمای دستی
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
    const safari = /safari/i.test(navigator.userAgent) && !/crios|fxios|edgios/i.test(navigator.userAgent);
    if (ios && safari && !snoozed() && ready()) {
        const el = bar('<span><strong>هم‌ورق رو به صفحه‌ی اصلی اضافه کن</strong><br><small>دکمه‌ی اشتراک‌گذاری <span aria-hidden="true">⬆️</span> رو بزن و «افزودن به صفحه‌ی اصلی» رو انتخاب کن.</small></span><span><button type="button" class="btn btn-sm btn-ghost" data-later>باشه</button></span>', "install");
        el.querySelector("[data-later]").addEventListener("click", () => { snooze(30); el.remove(); });
    }
})();
