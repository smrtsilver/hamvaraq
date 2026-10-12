// فعال/غیرفعال‌سازی Web Push روی این دستگاه (صفحه‌ی تنظیمات اعلان).
(() => {
    const root = document.querySelector("[data-push-root]");
    if (!root || root.dataset.enabled !== "1") return;
    const status = root.querySelector("[data-push-status]");
    const enableBtn = root.querySelector("[data-push-enable]");
    const disableBtn = root.querySelector("[data-push-disable]");
    const testBtn = root.querySelector("[data-push-test]");
    const csrf = () => (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
    const isiOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
    const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;

    const b64 = (s) => {
        const pad = "=".repeat((4 - (s.length % 4)) % 4);
        const raw = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
        return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
    };
    const post = (url, body) => fetch(url, {method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()}, body: JSON.stringify(body || {})});
    const show = (el, on) => { if (el) el.hidden = !on; };
    const say = (t) => { status.textContent = t; };

    async function refresh() {
        show(enableBtn, false); show(disableBtn, false); show(testBtn, false);
        if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
            say(isiOS && !standalone ? "برای دریافت اعلان روی آیفون، اول هم‌ورق رو به صفحه‌ی اصلی اضافه کن و از اون‌جا باز کن." : "مرورگرت از اعلان پشتیبانی نمی‌کنه.");
            return;
        }
        if (Notification.permission === "denied") { say("اعلان برای این سایت تو مرورگرت مسدوده؛ از تنظیمات مرورگر بازش کن."); return; }
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (sub) { say("اعلان روی این دستگاه فعاله ✅"); show(disableBtn, true); show(testBtn, true); }
        else { say("اعلان روی این دستگاه فعال نیست."); show(enableBtn, true); }
    }

    enableBtn.addEventListener("click", async () => {
        enableBtn.disabled = true;
        try {
            const perm = await Notification.requestPermission();
            if (perm !== "granted") { say("اجازه‌ی اعلان داده نشد."); return; }
            const reg = await navigator.serviceWorker.ready;
            const sub = await reg.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: b64(root.dataset.key)});
            const r = await post(root.dataset.subscribeUrl, sub.toJSON());
            if (!r.ok) { await sub.unsubscribe(); say("ثبت اعلان ناموفق بود؛ دوباره امتحان کن."); return; }
        } catch (_) { say("فعال‌سازی ناموفق بود."); }
        finally { enableBtn.disabled = false; refresh(); }
    });
    disableBtn.addEventListener("click", async () => {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (sub) { await post(root.dataset.unsubscribeUrl, {endpoint: sub.endpoint}); await sub.unsubscribe(); }
        refresh();
    });
    testBtn.addEventListener("click", async () => {
        testBtn.disabled = true;
        const r = await post(root.dataset.testUrl);
        say(r.ok ? "اعلان آزمایشی فرستاده شد؛ تا چند ثانیه‌ی دیگه می‌رسه." : "ارسال ناموفق بود.");
        testBtn.disabled = false;
    });
    refresh();
})();
