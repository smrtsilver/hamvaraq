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
            // ریلود فقط وقتی کاربر خودش «به‌روزرسانی» رو زده؛ فعال‌شدن اولین سرویس‌ورکر نباید صفحه (و فرمِ نیمه‌پرشده) رو بپرونه
            let userRequestedUpdate = false;
            const announce = (worker) => {
                const el = bar('<span>نسخه‌ی تازه‌ی هم‌ورق آماده‌ست.</span><span><button type="button" class="btn btn-sm" data-update>به‌روزرسانی</button></span>', "update");
                el.querySelector("[data-update]").addEventListener("click", () => { userRequestedUpdate = true; worker.postMessage("SKIP_WAITING"); });
            };
            if (reg.waiting && navigator.serviceWorker.controller) announce(reg.waiting);
            reg.addEventListener("updatefound", () => {
                const w = reg.installing;
                w && w.addEventListener("statechange", () => { if (w.state === "installed" && navigator.serviceWorker.controller) announce(w); });
            });
            let reloaded = false;
            navigator.serviceWorker.addEventListener("controllerchange", () => {
                if (userRequestedUpdate && !reloaded) { reloaded = true; location.reload(); }
            });
        });
    }

    // ---- پیشنهاد نصب ----
    if (standalone()) return;
    const DISMISS = "hv-install-dismissed-until";
    const snoozed = () => Number(store.get(DISMISS) || 0) > Date.now();
    const snooze = (days) => store.set(DISMISS, String(Date.now() + days * 864e5));
    const visits = Number(sessionStorage.getItem("hv-pages") || 0) + 1;
    try { sessionStorage.setItem("hv-pages", String(visits)); } catch (_) { /* بسته */ }
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
            if (choice.outcome !== "accepted") snooze(7);
            deferred = null;
        });
        shown.querySelector("[data-later]").addEventListener("click", () => { snooze(3); shown.remove(); });
    });
    window.addEventListener("appinstalled", () => { if (shown) shown.remove(); });

    // آیفون: نصب خودکار نداریم؛ راهنمای دستی
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
    const safari = /safari/i.test(navigator.userAgent) && !/crios|fxios|edgios/i.test(navigator.userAgent);
    if (ios && safari && !snoozed() && ready()) {
        const el = bar('<span><strong>هم‌ورق رو به صفحه‌ی اصلی اضافه کن</strong><br><small>دکمه‌ی اشتراک‌گذاری <span aria-hidden="true">⬆️</span> رو بزن و «افزودن به صفحه‌ی اصلی» رو انتخاب کن.</small></span><span><button type="button" class="btn btn-sm btn-ghost" data-later>باشه</button></span>', "install");
        el.querySelector("[data-later]").addEventListener("click", () => { snooze(14); el.remove(); });
    }
})();
