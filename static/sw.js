// سرویس‌ورکر ساده: فایل‌های استاتیک کش می‌شن، صفحه‌ها همیشه از شبکه (محتوا شخصیه) و
// وقتی آفلاینیم صفحه‌ی /offline/ نشون داده می‌شه. صفحه‌ی دیگه‌ای هیچ‌وقت کش نمی‌شه.
const VERSION = "hv-v1";
const PRECACHE = ["/offline/", "/static/css/app.css", "/static/js/app.js", "/static/favicon.svg"];

self.addEventListener("install", (e) => {
    e.waitUntil(caches.open(VERSION).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
    e.waitUntil(
        caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (e) => {
    const req = e.request;
    if (req.method !== "GET") return;
    const url = new URL(req.url);
    if (url.origin !== location.origin) return;

    if (url.pathname.startsWith("/static/")) {
        e.respondWith(
            caches.match(req).then((hit) => hit || fetch(req).then((res) => {
                const copy = res.clone();
                caches.open(VERSION).then((c) => c.put(req, copy));
                return res;
            }))
        );
    } else if (req.mode === "navigate") {
        e.respondWith(fetch(req).catch(() => caches.match("/offline/")));
    }
});
