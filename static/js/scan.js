// دوربین داخل صفحه: (۱) اسکن بارکد شابک، (۲) عکس جلد/آلبوم.
// چرا دوربین داخل صفحه؟ <input capture> برنامه‌ی دوربین گوشی رو باز می‌کنه و اندروید برای آزاد کردن حافظه تب مرورگر رو
// می‌بنده («Unable to complete previous operation due to low memory») و فرم از دست می‌ره. این‌جا همه‌چیز تو همین صفحه‌ست.
//
// اسکن: BarcodeDetector (کروم اندروید و …) و در غیابش zxing محلی (سافاری iOS). فقط ناحیه‌ی کادر با رزولوشن کامل دوربین
// خونده می‌شه (دقیق‌تر از کل تصویرِ کوچک‌شده). وضعیت و راهنمایی زنده نشون داده می‌شه؛ با خوندن بارکد، تأیید سبز،
// بستن خودکار، پر شدن شابک و جستجوی خودکار. حالت پیوسته (ثبت دسته‌ای): دوربین باز می‌مونه و هر بارکد یه ردیف پر می‌کنه.
(() => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;      // دوربین نیست: دکمه‌ها مخفی می‌مونن
    document.querySelectorAll("[data-scan], [data-scan-continuous], [data-camera-photo]").forEach((b) => { b.hidden = false; });

    const ZXING_URL = document.currentScript ? document.currentScript.dataset.zxing : "";
    const fa = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
    const TICK = 220;
    let dialog, video, statusEl, counterEl, zoomEl, torchEl, shotEl, galleryEl, frameEl, tipEl, stop = null, handler = null, track = null, mode = "scan";

    function build() {
        if (dialog) return;
        dialog = document.createElement("dialog");
        dialog.className = "scan-dialog";
        dialog.innerHTML = '<div class="scan-head"><strong class="scan-title"></strong><button type="button" class="sd-close" data-scan-close aria-label="بستن">✕</button></div>' +
            '<div class="scan-view"><video playsinline muted></video><i class="scan-frame" aria-hidden="true"><b class="scan-line"></b></i></div>' +
            '<div class="scan-tools"><label class="scan-zoom" hidden><span>زوم</span><input type="range" min="1" max="1" step="0.1" value="1" aria-label="زوم دوربین"></label>' +
            '<button type="button" class="btn btn-secondary btn-sm" data-scan-torch hidden aria-pressed="false">چراغ</button>' +
            '<button type="button" class="btn btn-sm" data-scan-shot>عکس بگیر</button>' +
            '<label class="link small scan-gallery">از گالری<input type="file" accept="image/*" hidden></label></div>' +
            '<p class="scan-status" role="status" aria-live="polite"></p><p class="scan-tip small muted"></p><p class="scan-count" hidden></p>';
        document.body.append(dialog);
        video = dialog.querySelector("video");
        statusEl = dialog.querySelector(".scan-status");
        tipEl = dialog.querySelector(".scan-tip");
        counterEl = dialog.querySelector(".scan-count");
        zoomEl = dialog.querySelector(".scan-zoom");
        torchEl = dialog.querySelector("[data-scan-torch]");
        shotEl = dialog.querySelector("[data-scan-shot]");
        galleryEl = dialog.querySelector(".scan-gallery input");
        frameEl = dialog.querySelector(".scan-frame");
        galleryEl.addEventListener("change", () => {
            const f = galleryEl.files[0];
            galleryEl.value = "";
            if (!f) return;
            if (mode === "photo") { const done = photoResolve; photoResolve = null; dialog.close(); if (done) done(f); }   // عکس جلد از گالری
            else fromImage(f);                                                                                               // بارکد از عکس گالری
        });
        shotEl.addEventListener("click", () => shoot());
        dialog.addEventListener("click", (e) => { if (e.target.closest("[data-scan-close]") || e.target === dialog) dialog.close(); });
        dialog.addEventListener("close", () => { if (stop) { stop(); stop = null; } track = null; if (photoResolve) { photoResolve(null); photoResolve = null; } });
    }
    const say = (text, tone) => { statusEl.textContent = text; statusEl.dataset.tone = tone || ""; };

    function loadZxing() {
        if (window.ZXing) return Promise.resolve();
        return new Promise((ok, fail) => {
            const s = document.createElement("script");
            s.src = ZXING_URL;
            s.onload = ok;
            s.onerror = () => fail(new Error("zxing"));
            document.head.append(s);
        });
    }

    // ---- رمزگشایی ----
    let detector = null;
    async function getDetector() {
        if (detector !== null) return detector;
        detector = false;
        if ("BarcodeDetector" in window) {
            try {
                const formats = await BarcodeDetector.getSupportedFormats();
                if (formats.includes("ean_13")) detector = new BarcodeDetector({formats: ["ean_13"]});
            } catch (_) { /* پشتیبانی نشده */ }
        }
        if (!detector) await loadZxing().catch(() => {});
        return detector;
    }
    let zx = null;
    function zxDecode(canvas) {
        if (!window.ZXing) return null;
        if (!zx) {
            zx = new ZXing.MultiFormatReader();
            zx.setHints(new Map([[ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13]], [ZXing.DecodeHintType.TRY_HARDER, true]]));
        }
        try { return zx.decode(new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(new ZXing.HTMLCanvasElementLuminanceSource(canvas)))).getText(); } catch (_) { return null; }
    }
    async function decode(canvas) {
        const det = await getDetector();
        if (det) { try { const c = await det.detect(canvas); if (c.length) return c[0].rawValue; } catch (_) { /* فریم خراب */ } }
        return zxDecode(canvas);
    }

    // ناحیه‌ی کادر روی تصویر واقعی دوربین (object-fit: cover رو حساب می‌کنه)
    const work = document.createElement("canvas");
    const wctx = work.getContext("2d", {willReadFrequently: true});
    function grab(full) {
        const vw = video.videoWidth, vh = video.videoHeight;
        if (!vw || !vh) return null;
        let sx = 0, sy = 0, sw = vw, sh = vh;
        if (!full) {
            const box = video.getBoundingClientRect(), fr = frameEl.getBoundingClientRect();
            const k = Math.max(box.width / vw, box.height / vh);
            const ox = (box.width - vw * k) / 2, oy = (box.height - vh * k) / 2;
            sx = Math.max(0, (fr.left - box.left - ox) / k); sy = Math.max(0, (fr.top - box.top - oy) / k);
            sw = Math.min(vw - sx, fr.width / k); sh = Math.min(vh - sy, fr.height / k);
        }
        const scale = Math.min(1, 1400 / sw);
        work.width = Math.round(sw * scale); work.height = Math.round(sh * scale);
        wctx.drawImage(video, sx, sy, sw, sh, 0, 0, work.width, work.height);
        return work;
    }

    // ---- دوربین ----
    async function camera() {
        const base = {facingMode: {ideal: "environment"}, width: {ideal: 1920}, height: {ideal: 1080}};
        let stream;
        try { stream = await navigator.mediaDevices.getUserMedia({video: {...base, advanced: [{focusMode: "continuous"}]}, audio: false}); }
        catch (e) { if (e && e.name === "NotAllowedError") throw e; stream = await navigator.mediaDevices.getUserMedia({video: base, audio: false}); }
        video.srcObject = stream;
        await video.play();
        track = stream.getVideoTracks()[0];
        setupTrack(track);
        return () => { stream.getTracks().forEach((t) => t.stop()); video.srcObject = null; };
    }

    // فوکوس پیوسته، زوم دستی (پیش‌فرض بدون زوم دیجیتال؛ کیفیت رو پایین میاره) و چراغ، اگه دوربین پشتیبانی کنه
    function setupTrack(t) {
        zoomEl.hidden = torchEl.hidden = true;
        if (!t || !t.getCapabilities) return;
        const caps = t.getCapabilities();
        if (caps.focusMode && caps.focusMode.includes("continuous")) t.applyConstraints({advanced: [{focusMode: "continuous"}]}).catch(() => {});
        if (caps.zoom && caps.zoom.max > (caps.zoom.min || 1)) {
            const r = zoomEl.querySelector("input");
            Object.assign(r, {min: caps.zoom.min || 1, max: Math.min(caps.zoom.max, 5), step: caps.zoom.step || 0.1, value: caps.zoom.min || 1});
            r.oninput = () => t.applyConstraints({advanced: [{zoom: +r.value}]}).catch(() => {});
            zoomEl.hidden = false;
        }
        if (caps.torch) {
            torchEl.hidden = false;
            torchEl.onclick = () => {
                const on = torchEl.getAttribute("aria-pressed") !== "true";
                t.applyConstraints({advanced: [{torch: on}]}).then(() => torchEl.setAttribute("aria-pressed", String(on))).catch(() => {});
            };
        }
        video.onclick = () => {       // لمس تصویر: فوکوس دوباره
            if (caps.focusMode && caps.focusMode.includes("single-shot")) {
                t.applyConstraints({advanced: [{focusMode: "single-shot"}]}).then(() => t.applyConstraints({advanced: [{focusMode: "continuous"}]})).catch(() => {});
            }
        };
    }

    // عکس با کیفیت کامل از همین دوربین (بدون باز کردن برنامه‌ی دوربین گوشی)
    async function still() {
        if (track && "ImageCapture" in window) {
            try { return await new ImageCapture(track).takePhoto(); } catch (_) { /* بعضی گوشی‌ها؛ فریم ویدیو */ }
        }
        const c = document.createElement("canvas");
        c.width = video.videoWidth; c.height = video.videoHeight;
        c.getContext("2d").drawImage(video, 0, 0);
        return await new Promise((r) => c.toBlob(r, "image/jpeg", 0.92));
    }

    // ---- اسکن ----
    const HINTS = [
        [0, "بارکد پشت کتاب رو صاف داخل کادر بگیر."],
        [5000, "خونده نشد؟ گوشی رو کمی عقب‌تر ببر (۱۵ تا ۲۵ سانت) تا فوکوس کنه، بعد آروم نزدیک کن."],
        [10000, "نور کمه یا براقه؟ «چراغ» رو روشن کن، یا کتاب رو کمی کج بگیر تا انعکاس نیفته. «عکس بگیر» هم کمک می‌کنه."],
        [18000, "باز هم نشد؟ شابک رو دستی بنویس؛ زیر یا بالای بارکد چاپ شده (۱۳ رقم، با ۹۷۸ شروع می‌شه)."],
    ];
    async function loop(isAlive, onRaw) {
        let n = 0;
        const started = Date.now();
        while (isAlive()) {
            const t = Date.now() - started;
            const hint = HINTS.filter(([at]) => t >= at).pop();
            if (hint && tipEl.textContent !== hint[1] && !dialog.classList.contains("hit")) tipEl.textContent = hint[1];
            const c = grab(n % 4 === 3);               // بیشتر وقت‌ها فقط کادر، هر چهارمی کل تصویر
            if (c) { const raw = await decode(c); if (raw && isAlive()) onRaw(raw); }
            n += 1;
            await new Promise((r) => setTimeout(r, TICK));
        }
    }

    async function fromImage(blob) {
        say("در حال خوندن بارکد از عکس…");
        try {
            const bmp = await createImageBitmap(blob);
            const c = document.createElement("canvas");
            const k = Math.min(1, 1800 / Math.max(bmp.width, bmp.height));
            c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
            c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
            bmp.close && bmp.close();
            let raw = await decode(c);
            if (!raw) {     // وسط عکس با بزرگ‌نمایی (بارکد کوچیک تو عکس دور)
                const m = document.createElement("canvas");
                m.width = Math.round(c.width * 0.6); m.height = Math.round(c.height * 0.5);
                m.getContext("2d").drawImage(c, c.width * 0.2, c.height * 0.25, m.width, m.height, 0, 0, m.width, m.height);
                raw = await decode(m);
            }
            if (raw && handler) handler(raw);
            else say("تو این عکس بارکدی پیدا نشد؛ از نزدیک‌تر، صاف و بدون انعکاس بگیر یا شابک رو دستی بنویس.", "warn");
        } catch (_) { say("عکس خونده نشد؛ شابک رو دستی بنویس.", "warn"); }
    }
    async function shoot() {
        if (mode === "photo") return takePhoto();
        if (!track) { galleryEl.click(); return; }
        shotEl.disabled = true; shotEl.classList.add("is-loading");
        try { const b = await still(); if (b) await fromImage(b); } finally { shotEl.disabled = false; shotEl.classList.remove("is-loading"); }
    }

    async function open({continuous, onCode}) {
        build();
        mode = "scan";
        dialog.classList.remove("photo-mode", "hit");
        dialog.querySelector(".scan-title").textContent = "اسکن بارکد پشت کتاب";
        dialog.setAttribute("aria-label", "اسکن بارکد شابک");
        shotEl.textContent = "عکس بگیر";
        say("در حال باز کردن دوربین…");
        tipEl.textContent = "";
        counterEl.hidden = !continuous;
        let count = 0, last = "", lastAt = 0;
        const seen = new Set();
        dialog.showModal();
        handler = (raw) => {
            const code = window.HVIsbn && window.HVIsbn.normalize(raw);
            const now = Date.now();
            if (!code || !/^97[89]/.test(code)) {
                if (now - lastAt > 2500) { lastAt = now; say("این بارکد شابک نیست؛ بارکدی که کنار «ISBN» یا «شابک» نوشته شده رو بگیر.", "warn"); }
                return;
            }
            if (code === last && now - lastAt < 4000) return;      // همون بارکد پشت‌سرهم
            if (continuous && seen.has(code)) { last = code; lastAt = now; say("این کتاب رو قبلاً اسکن کردی.", "warn"); return; }
            last = code; lastAt = now;
            const ok = onCode(code);
            if (ok === false) { say("جایی برای کتاب بعدی نیست؛ اول همین‌ها رو ثبت کن.", "warn"); return; }
            seen.add(code);
            count += 1;
            if (navigator.vibrate) navigator.vibrate(80);
            dialog.classList.add("hit");
            say("✓ خونده شد: " + fa(code), "ok");
            if (continuous) {
                setTimeout(() => dialog.classList.remove("hit"), 500);
                counterEl.textContent = fa(count) + " کتاب اسکن شد؛ بعدی رو جلوی دوربین بگیر.";
            } else {
                setTimeout(() => { dialog.close(); dialog.classList.remove("hit"); }, 650);
            }
        };
        try {
            stop = await camera();
            let alive = true;
            const end = stop;
            stop = () => { alive = false; end(); };
            say("در حال جستجوی بارکد…");
            loop(() => alive && dialog.open, (raw) => handler && handler(raw));
        } catch (err) {
            say(err && err.name === "NotAllowedError" ? "اجازه‌ی دوربین داده نشد؛ از «از گالری» عکس بارکد رو انتخاب کن یا شابک رو دستی بنویس."
                : "دوربین باز نشد؛ از «از گالری» عکس بارکد رو انتخاب کن یا شابک رو دستی بنویس.", "warn");
        }
    }

    // ---- عکس جلد/آلبوم با دوربین داخل صفحه ----
    let photoResolve = null;
    async function takePhoto() {
        shotEl.disabled = true; shotEl.classList.add("is-loading");
        try {
            const blob = await still();
            if (!blob) { say("عکس گرفته نشد؛ دوباره بزن.", "warn"); return; }
            const file = new File([blob], "camera-" + Date.now() + ".jpg", {type: blob.type || "image/jpeg", lastModified: Date.now()});
            if (navigator.vibrate) navigator.vibrate(60);
            const done = photoResolve; photoResolve = null;
            dialog.close();
            if (done) done(file);
        } finally { shotEl.disabled = false; shotEl.classList.remove("is-loading"); }
    }
    function photo() {
        build();
        mode = "photo";
        dialog.classList.add("photo-mode");
        dialog.classList.remove("hit");
        dialog.querySelector(".scan-title").textContent = "عکس کتاب";
        dialog.setAttribute("aria-label", "گرفتن عکس با دوربین");
        shotEl.textContent = "گرفتن عکس";
        counterEl.hidden = true;
        say("در حال باز کردن دوربین…");
        tipEl.textContent = "کتاب رو تو نور روشن و روی زمینه‌ی ساده بگیر.";
        handler = null;
        dialog.showModal();
        return new Promise(async (resolve) => {
            photoResolve = resolve;
            try { stop = await camera(); say("کتاب رو کامل تو تصویر بیار و «گرفتن عکس» رو بزن."); }
            catch (err) { say(err && err.name === "NotAllowedError" ? "اجازه‌ی دوربین داده نشد؛ از «از گالری» انتخاب کن." : "دوربین باز نشد؛ از «از گالری» انتخاب کن.", "warn"); }
        });
    }
    window.HVCamera = {photo, scan: open};

    function addFiles(input, files) {
        const dt = new DataTransfer();
        if (input.multiple) [...(input.files || [])].forEach((f) => dt.items.add(f));
        files.forEach((f) => dt.items.add(f));
        input.files = dt.files;
        input.dispatchEvent(new Event("change", {bubbles: true}));
    }

    document.addEventListener("click", async (e) => {
        const single = e.target.closest("[data-scan]");
        if (single) {
            e.preventDefault();
            const target = document.getElementById(single.dataset.scanTarget) || single.closest("form").querySelector("[data-isbn-url]");
            open({continuous: false, onCode: (code) => {
                target.value = code;
                delete target.dataset.looked;
                target.dispatchEvent(new Event("input", {bubbles: true}));
                target.dispatchEvent(new Event("change", {bubbles: true}));     // isbn.js خودش جستجو می‌کنه و فیلدها رو پر می‌کنه
                setTimeout(() => target.closest(".field").scrollIntoView({block: "center", behavior: "smooth"}), 700);
            }});
            return;
        }
        const multi = e.target.closest("[data-scan-continuous]");
        if (multi) {
            e.preventDefault();
            const form = multi.closest("form");
            open({continuous: true, onCode: (code) => {
                const row = [...form.querySelectorAll("[data-isbn-scope]")].find((r) => { const i = r.querySelector("[data-isbn-url]"); return i && !i.value.trim(); });
                if (!row) return false;
                const input = row.querySelector("[data-isbn-url]");
                input.value = code;
                input.dispatchEvent(new Event("change", {bubbles: true}));
                row.scrollIntoView({block: "nearest", behavior: "smooth"});
                return true;
            }});
            return;
        }
        const cam = e.target.closest("[data-camera-photo]");
        if (cam) {
            e.preventDefault();
            const input = document.getElementById(cam.dataset.cameraPhoto);
            if (!input) return;
            const file = await photo();
            if (file) addFiles(input, [file]);
        }
    });
})();
