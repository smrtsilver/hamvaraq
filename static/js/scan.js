// اسکن بارکد شابک با دوربین: BarcodeDetector (کروم اندروید و ...) و در غیاب اون zxing محلی (سافاری iOS و ...).
// حالت تکی: شابک فیلد رو پر می‌کنه و می‌بنده. حالت پیوسته (ثبت دسته‌ای): دوربین باز می‌مونه و هر بارکد یه ردیف پر می‌کنه.
(() => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;      // دوربین نیست: دکمه‌ها مخفی می‌مونن
    document.querySelectorAll("[data-scan], [data-scan-continuous]").forEach((b) => { b.hidden = false; });

    const ZXING_URL = document.currentScript ? document.currentScript.dataset.zxing : "";
    const fa = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
    let dialog, video, statusEl, counterEl, zoomEl, torchEl, photoEl, stop = null, handler = null;

    function build() {
        if (dialog) return;
        dialog = document.createElement("dialog");
        dialog.className = "scan-dialog";
        dialog.setAttribute("aria-label", "اسکن بارکد شابک");
        dialog.innerHTML = '<div class="scan-head"><strong>اسکن بارکد پشت کتاب</strong><button type="button" class="sd-close" data-scan-close aria-label="بستن">✕</button></div>' +
            '<div class="scan-view"><video playsinline muted></video><i class="scan-frame" aria-hidden="true"></i></div>' +
            '<div class="scan-tools"><label class="scan-zoom" hidden><span>زوم</span><input type="range" min="1" max="1" step="0.1" value="1" aria-label="زوم دوربین"></label>' +
            '<button type="button" class="btn btn-secondary btn-sm" data-scan-torch hidden aria-pressed="false">چراغ</button>' +
            '<label class="btn btn-secondary btn-sm scan-photo">عکس بگیر<input type="file" accept="image/*" capture="environment" hidden></label></div>' +
            '<p class="scan-status" role="status" aria-live="polite"></p><p class="scan-tip small muted">تار بود؟ گوشی رو کمی دورتر (۲۰ تا ۳۰ سانت) بگیر و زوم کن، یا «عکس بگیر» رو بزن.</p><p class="scan-count" hidden></p>';
        document.body.append(dialog);
        video = dialog.querySelector("video");
        statusEl = dialog.querySelector(".scan-status");
        counterEl = dialog.querySelector(".scan-count");
        zoomEl = dialog.querySelector(".scan-zoom");
        torchEl = dialog.querySelector("[data-scan-torch]");
        photoEl = dialog.querySelector(".scan-photo input");
        photoEl.addEventListener("change", () => { const f = photoEl.files[0]; photoEl.value = ""; if (f) fromPhoto(f); });
        dialog.addEventListener("click", (e) => { if (e.target.closest("[data-scan-close]") || e.target === dialog) dialog.close(); });
        dialog.addEventListener("close", () => { if (stop) { stop(); stop = null; } });
    }

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

    async function engine(onRaw) {
        const stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: {ideal: "environment"}, width: {ideal: 1920}, height: {ideal: 1080}}, audio: false});
        video.srcObject = stream;
        await video.play();
        setupTrack(stream.getVideoTracks()[0]);
        let alive = true;
        const end = () => { alive = false; stream.getTracks().forEach((t) => t.stop()); video.srcObject = null; };
        if ("BarcodeDetector" in window) {
            const det = new BarcodeDetector({formats: ["ean_13"]});
            (async function loop() {
                while (alive) {
                    try { const codes = await det.detect(video); codes.forEach((c) => onRaw(c.rawValue)); } catch (_) { /* فریم خراب */ }
                    await new Promise((r) => setTimeout(r, 200));
                }
            })();
            return end;
        }
        await loadZxing();
        // هسته‌ی zxing مستقیم: هر ~۲۰۰ms یه فریم از ویدیو روی canvas و رمزگشایی (مستقل از لایه‌ی مرورگرِ کتابخونه)
        const hints = new Map([[ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13]], [ZXing.DecodeHintType.TRY_HARDER, true]]);
        const decoder = new ZXing.MultiFormatReader();
        decoder.setHints(hints);
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d", {willReadFrequently: true});
        (async function loop() {
            while (alive) {
                const w = video.videoWidth, h = video.videoHeight;
                if (w && h) {
                    const k = Math.min(1, 960 / w);
                    canvas.width = Math.round(w * k);
                    canvas.height = Math.round(h * k);
                    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                    try {
                        const bitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(new ZXing.HTMLCanvasElementLuminanceSource(canvas)));
                        onRaw(decoder.decode(bitmap).getText());
                    } catch (_) { /* بارکدی تو این فریم نیست */ }
                }
                await new Promise((r) => setTimeout(r, 200));
            }
        })();
        return end;
    }

    // فوکوس پیوسته، زوم (از دور واضح‌تره تا از نزدیک) و چراغ، اگه دوربین پشتیبانی کنه
    function setupTrack(track) {
        zoomEl.hidden = torchEl.hidden = true;
        if (!track || !track.getCapabilities) return;
        const caps = track.getCapabilities();
        const adv = [];
        if (caps.focusMode && caps.focusMode.includes("continuous")) adv.push({focusMode: "continuous"});
        if (caps.zoom && caps.zoom.max > 1) {
            const z = Math.min(caps.zoom.max, 2);
            adv.push({zoom: z});
            const r = zoomEl.querySelector("input");
            Object.assign(r, {min: caps.zoom.min || 1, max: Math.min(caps.zoom.max, 6), step: caps.zoom.step || 0.1, value: z});
            r.oninput = () => track.applyConstraints({advanced: [{zoom: +r.value}]}).catch(() => {});
            zoomEl.hidden = false;
        }
        if (adv.length) track.applyConstraints({advanced: adv}).catch(() => {});
        if (caps.torch) {
            torchEl.hidden = false;
            torchEl.onclick = () => {
                const on = torchEl.getAttribute("aria-pressed") !== "true";
                track.applyConstraints({advanced: [{torch: on}]}).then(() => torchEl.setAttribute("aria-pressed", String(on))).catch(() => {});
            };
        }
        // لمس تصویر: فوکوس دوباره
        video.onclick = () => {
            if (caps.focusMode && caps.focusMode.includes("single-shot")) {
                track.applyConstraints({advanced: [{focusMode: "single-shot"}]}).then(() => track.applyConstraints({advanced: [{focusMode: "continuous"}]})).catch(() => {});
            }
        };
    }

    // عکس با دوربین خود گوشی (فوکوس خودکار دقیق‌تر) و خوندن بارکد از عکس
    async function fromPhoto(file) {
        statusEl.textContent = "در حال خوندن بارکد از عکس…";
        try {
            const bmp = await createImageBitmap(file);
            let raw = null;
            if ("BarcodeDetector" in window) {
                const codes = await new BarcodeDetector({formats: ["ean_13"]}).detect(bmp).catch(() => []);
                raw = codes.length ? codes[0].rawValue : null;
            }
            if (!raw) {
                await loadZxing();
                const hints = new Map([[ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13]], [ZXing.DecodeHintType.TRY_HARDER, true]]);
                const dec = new ZXing.MultiFormatReader(); dec.setHints(hints);
                const c = document.createElement("canvas"), k = Math.min(1, 1600 / bmp.width);
                c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
                c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
                try { raw = dec.decode(new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(new ZXing.HTMLCanvasElementLuminanceSource(c)))).getText(); } catch (_) { raw = null; }
            }
            const code = raw && window.HVIsbn && window.HVIsbn.normalize(raw);
            if (code && /^97[89]/.test(code) && handler) handler(raw);
            else statusEl.textContent = "تو این عکس بارکدی پیدا نشد؛ از نزدیک‌تر و صاف‌تر بگیر یا شابک رو دستی بنویس.";
        } catch (_) { statusEl.textContent = "عکس خونده نشد؛ شابک رو دستی بنویس."; }
    }

    async function open({continuous, onCode}) {
        build();
        statusEl.textContent = "در حال باز کردن دوربین…";
        counterEl.hidden = !continuous;
        let count = 0, last = "", lastAt = 0;
        const seen = new Set();
        dialog.showModal();
        handler = (raw) => {
            const code = window.HVIsbn && window.HVIsbn.normalize(raw);
            if (!code || !/^97[89]/.test(code)) return;
            const now = Date.now();
            if (code === last && now - lastAt < 4000) return;      // همون بارکد پشت‌سرهم
            if (continuous && seen.has(code)) { last = code; lastAt = now; statusEl.textContent = "این کتاب رو قبلاً اسکن کردی."; return; }
            last = code; lastAt = now;
            const ok = onCode(code);
            if (ok === false) { statusEl.textContent = "جایی برای کتاب بعدی نیست؛ اول همین‌ها رو ثبت کن."; return; }
            seen.add(code);
            count += 1;
            if (navigator.vibrate) navigator.vibrate(60);
            dialog.classList.add("hit");
            setTimeout(() => dialog.classList.remove("hit"), 300);
            if (continuous) { counterEl.textContent = fa(count) + " کتاب اسکن شد؛ بعدی رو جلوی دوربین بگیر."; statusEl.textContent = "آخرین: " + code; }
            else dialog.close();
        };
        try {
            stop = await engine(handler);
            statusEl.textContent = "بارکد پشت کتاب (شابک) رو داخل کادر بگیر.";
        } catch (err) {
            statusEl.textContent = err && err.name === "NotAllowedError" ? "اجازه‌ی دوربین داده نشد؛ «عکس بگیر» رو بزن یا شابک رو دستی بنویس." : "دوربین زنده باز نشد؛ «عکس بگیر» رو بزن یا شابک رو دستی بنویس.";
        }
    }

    document.addEventListener("click", (e) => {
        const single = e.target.closest("[data-scan]");
        if (single) {
            e.preventDefault();
            const target = document.getElementById(single.dataset.scanTarget) || single.closest("form").querySelector("[data-isbn-url]");
            open({continuous: false, onCode: (code) => { target.value = code; target.dispatchEvent(new Event("change", {bubbles: true})); }});
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
        }
    });
})();
