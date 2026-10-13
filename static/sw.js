// سرویس‌ورکر هم‌ورق. شماره‌ی نسخه از سرور جایگزین می‌شه تا با هر تغییر فایل‌ها، کش تازه بشه.
const VERSION = "__VERSION__";
const STATIC = `hv-static-${VERSION}`;
const IMAGES = "hv-images-v1";
const PRECACHE = [
    "/offline/", "/static/css/app.css", "/static/js/app.js", "/static/favicon.svg", "/static/brand/mark.svg",
    "/static/fonts/vazirmatn/Vazirmatn-Regular.woff2", "/static/fonts/vazirmatn/Vazirmatn-Bold.woff2",
];
const MAX_IMAGES = 80;

self.addEventListener("install", (e) => {
    // نسخه‌ی تازه بلافاصله فعال می‌شه (کش‌های قبلی تو activate پاک می‌شن)؛ صفحه‌ها خودشون تصمیم می‌گیرن کی ریلود کنن
    e.waitUntil(caches.open(STATIC).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
    e.waitUntil(
        caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith("hv-static-") && k !== STATIC).map((k) => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("message", (e) => { if (e.data === "SKIP_WAITING") self.skipWaiting(); });

async function trim(cacheName, max) {
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();
    if (keys.length > max) await Promise.all(keys.slice(0, keys.length - max).map((k) => cache.delete(k)));
}

self.addEventListener("fetch", (e) => {
    const req = e.request;
    if (req.method !== "GET") return;
    const url = new URL(req.url);
    if (url.origin !== location.origin) return;

    // فایل‌های استاتیک: اول کش، پشت‌صحنه تازه‌سازی
    if (url.pathname.startsWith("/static/")) {
        e.respondWith(caches.open(STATIC).then(async (cache) => {
            const hit = await cache.match(req);
            const fresh = fetch(req).then((res) => { if (res.ok) cache.put(req, res.clone()); return res; }).catch(() => hit);
            return hit || fresh;
        }));
        return;
    }
    // عکس کتاب‌ها: اول کش (با سقف تعداد)
    if (url.pathname.startsWith("/media/") && /\.(jpe?g|png|webp)$/i.test(url.pathname)) {
        e.respondWith(caches.open(IMAGES).then(async (cache) => {
            const hit = await cache.match(req);
            if (hit) return hit;
            const res = await fetch(req);
            if (res.ok) { cache.put(req, res.clone()); trim(IMAGES, MAX_IMAGES); }
            return res;
        }));
        return;
    }
    // صفحه‌ها: همیشه از شبکه (محتوا شخصیه و هیچ‌وقت کش نمی‌شه)؛ آفلاین ← صفحه‌ی آفلاین
    if (req.mode === "navigate") {
        e.respondWith(fetch(req).catch(() => caches.match("/offline/")));
    }
});

// ---- Web Push ----
self.addEventListener("push", (e) => {
    let d = {};
    try { d = e.data ? e.data.json() : {}; } catch (_) { d = {body: e.data ? e.data.text() : ""}; }
    e.waitUntil(self.registration.showNotification(d.title || "هم‌ورق", {
        body: d.body || "", icon: d.icon || "/static/brand/icon-192.png", badge: d.badge || "/static/brand/favicon-48.png",
        tag: d.tag, renotify: !!d.tag, dir: "rtl", lang: "fa", data: {url: d.url || "/"},
    }));
});

self.addEventListener("notificationclick", (e) => {
    e.notification.close();
    const target = new URL((e.notification.data && e.notification.data.url) || "/", location.origin).href;
    e.waitUntil(clients.matchAll({type: "window", includeUncontrolled: true}).then((list) => {
        for (const c of list) if (c.url === target && "focus" in c) return c.focus();
        for (const c of list) if ("navigate" in c) return c.focus().then(() => c.navigate(target));
        return clients.openWindow(target);
    }));
});
