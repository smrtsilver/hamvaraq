// شمارش بازدید واقعی: بعد از چند ثانیه حضور در تب دیده‌شده و حداقل یک تعامل، توکن صفحه رو برمی‌گردونه.
(() => {
    const meta = document.querySelector('meta[name="hv-view"]');
    if (!meta || !meta.content || navigator.doNotTrack === "1") return;
    const NEED = 4000; // میلی‌ثانیه‌ی حضور دیده‌شده
    let visible = document.visibilityState === "visible" ? performance.now() : null;
    let total = 0, touched = false, sent = false;
    const events = ["scroll", "pointermove", "touchstart", "keydown", "click"];

    function tick() {
        if (sent) return;
        const now = visible === null ? total : total + (performance.now() - visible);
        if (touched && now >= NEED) {
            sent = true;
            events.forEach((e) => removeEventListener(e, onTouch));
            const body = new URLSearchParams({t: meta.content});
            try { fetch(meta.dataset.url, {method: "POST", body, keepalive: true, credentials: "same-origin"}); } catch (_) { /* آمار اختیاریه */ }
        }
    }
    function onTouch() { touched = true; tick(); }
    events.forEach((e) => addEventListener(e, onTouch, {passive: true}));
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") visible = performance.now();
        else if (visible !== null) { total += performance.now() - visible; visible = null; }
    });
    setInterval(tick, 1000);
})();
