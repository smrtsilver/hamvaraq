/* استوری‌ساز: رسم روی canvas ۱۰۸۰×۱۹۲۰؛ پیش‌نمایش همون canvasیه که دانلود می‌شه (بدون کتابخانه‌ی خارجی).
   متن فارسی با direction=rtl خود مرورگر شکل می‌گیره و فونت Vazirmatn از قبل روی صفحه بارگذاری شده. */
(function () {
  var root = document.querySelector("[data-story]");
  if (!root) return;
  var data = JSON.parse(document.getElementById("hv-story").textContent);
  var canvas = root.querySelector(".story-canvas"), ctx = canvas.getContext("2d");
  var form = root.querySelector("[data-story-form]"), status = root.querySelector("[data-story-status]");
  var W = 1080, H = 1920, FONT = "Vazirmatn, Tahoma, sans-serif";
  var cover = null;
  var THEMES = {
    paper: { bg: ["#F4EBD5", "#EADBB8"], ink: "#2B2116", sub: "#6B5A45", accent: "#8A5A16", card: "rgba(90,60,20,.08)" },
    night: { bg: ["#0E1713", "#1F3D30"], ink: "#F6EEDC", sub: "#B9CBBF", accent: "#E0A43A", card: "rgba(255,255,255,.07)" },
    saffron: { bg: ["#F4C46A", "#C8742B"], ink: "#2A1D00", sub: "#5A3B10", accent: "#7A2E0E", card: "rgba(255,255,255,.22)" },
    cover: { bg: ["#1b1b1b", "#0b0b0b"], ink: "#FFFFFF", sub: "#E7DED0", accent: "#E0A43A", card: "rgba(255,255,255,.12)" }
  };
  var LABEL = { quote: "نقل‌قول", review: "نقد", book: "معرفی کتاب" };

  function opts() {
    var f = new FormData(form);
    return { tpl: f.get("tpl") || "paper", text: (f.get("text") || "").trim(), title: (f.get("title") || "").trim(),
      author: (f.get("author") || "").trim(), align: f.get("align") || "center", showCover: !!f.get("showcover") };
  }
  function font(w, s) { return w + " " + s + "px " + FONT; }
  function rr(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function wrap(text, max) {
    var out = [];
    text.split(/\n+/).forEach(function (para) {
      var line = "";
      para.split(/\s+/).forEach(function (w) {
        var t = line ? line + " " + w : w;
        if (line && ctx.measureText(t).width > max) { out.push(line); line = w; } else line = t;
      });
      if (line) out.push(line);
    });
    return out;
  }
  function seeded(n) { var s = n; return function () { s = (s * 16807) % 2147483647; return s / 2147483647; }; }

  function background(t, o) {
    var g = ctx.createLinearGradient(0, 0, W * 0.4, H);
    g.addColorStop(0, t.bg[0]); g.addColorStop(1, t.bg[1]);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    if (o.tpl === "cover" && cover) {
      var k = Math.max(W / cover.width, H / cover.height), w = cover.width * k, h = cover.height * k;
      ctx.save(); if ("filter" in ctx) ctx.filter = "blur(28px) saturate(1.2)";
      ctx.drawImage(cover, (W - w) / 2, (H - h) / 2, w, h); ctx.restore();
      ctx.fillStyle = "rgba(8,8,8,.58)"; ctx.fillRect(0, 0, W, H);
    }
    if (o.tpl === "paper") {
      var rnd = seeded(7);
      for (var i = 0; i < 2600; i++) { ctx.fillStyle = "rgba(90,60,20," + (rnd() * 0.07).toFixed(3) + ")"; ctx.fillRect(rnd() * W, rnd() * H, 2, 2); }
      var v = ctx.createRadialGradient(W / 2, H / 2, H * 0.3, W / 2, H / 2, H * 0.75);
      v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, "rgba(90,55,15,.28)");
      ctx.fillStyle = v; ctx.fillRect(0, 0, W, H);
      ctx.strokeStyle = "rgba(138,90,22,.55)"; ctx.lineWidth = 3; ctx.strokeRect(54, 54, W - 108, H - 108);
      ctx.lineWidth = 1.5; ctx.strokeRect(70, 70, W - 140, H - 140);
    }
    if (o.tpl === "night") {
      var rnd2 = seeded(11);
      for (var j = 0; j < 90; j++) { ctx.fillStyle = "rgba(224,164,58," + (rnd2() * 0.5).toFixed(2) + ")"; ctx.beginPath(); ctx.arc(rnd2() * W, rnd2() * H * 0.35, rnd2() * 2.4, 0, 7); ctx.fill(); }
    }
    if (o.tpl === "saffron") {
      ctx.fillStyle = "rgba(255,255,255,.12)"; ctx.beginPath(); ctx.arc(W * 0.9, H * 0.12, 360, 0, 7); ctx.fill();
      ctx.beginPath(); ctx.arc(W * 0.05, H * 0.9, 300, 0, 7); ctx.fill();
    }
  }

  function draw() {
    var o = opts(), t = THEMES[o.tpl] || THEMES.paper;
    if (o.tpl === "cover" && !cover) t = THEMES.night;
    ctx.save(); ctx.clearRect(0, 0, W, H); ctx.direction = "rtl";
    background(t, o);
    // سربرگ
    ctx.textAlign = "center"; ctx.fillStyle = t.ink; ctx.font = font(800, 60); ctx.fillText("هم‌ورق", W / 2, 190);
    var lab = LABEL[data.mode] || "", lw;
    ctx.font = font(700, 34); lw = ctx.measureText(lab).width + 64;
    rr((W - lw) / 2, 236, lw, 64, 32); ctx.fillStyle = t.card; ctx.fill();
    ctx.fillStyle = t.accent; ctx.fillText(lab, W / 2, 280);

    // متن اصلی با اندازه‌ی خودکار
    var hasFooter = !!(o.title || o.author), top = 380, bottom = hasFooter ? 1330 : 1600;
    var maxW = W - 220, size = 70, lines, lh;
    var text = o.text || (data.mode === "quote" ? "جمله‌ای که دوستش داشتی رو اینجا بنویس…" : "…");
    do { ctx.font = font(data.mode === "quote" ? 700 : 500, size); lines = wrap(text, maxW); lh = size * 1.75; size -= 2; } while (lines.length * lh > bottom - top - 140 && size > 30);
    var blockH = lines.length * lh, y0 = top + 60 + (bottom - top - blockH) / 2 + lh * 0.7;
    var x = o.align === "right" ? W - 110 : W / 2;
    ctx.textAlign = o.align === "right" ? "right" : "center";
    ctx.fillStyle = t.accent; ctx.globalAlpha = 0.4; ctx.font = font(800, 170);
    ctx.fillText("»", o.align === "right" ? W - 100 : W / 2, y0 - lh * 1.05); ctx.globalAlpha = 1;   // در متن راست‌به‌چپ قرینه می‌شه و «باز» دیده می‌شه
    ctx.fillStyle = t.ink; ctx.font = font(data.mode === "quote" ? 700 : 500, size + 2);
    lines.forEach(function (l, i) { ctx.fillText(l, x, y0 + i * lh); });
    var after = y0 + blockH;
    if (data.stars) {
      ctx.textAlign = "center"; ctx.font = font(400, 54); ctx.fillStyle = t.accent;
      ctx.fillText("★★★★★".slice(0, data.stars) + "☆☆☆☆☆".slice(0, 5 - data.stars), W / 2, Math.min(after + 40, bottom + 30));
    }

    // کارت مرجع کتاب
    if (hasFooter) {
      var cy = 1420, ch = 300, cx = 110, cw = W - 220, useCover = o.showCover && cover;
      rr(cx, cy, cw, ch, 36); ctx.fillStyle = t.card; ctx.fill();
      var tx = W - cx - 40, tw = cw - 80;
      if (useCover) {
        var iw = 160, ih = 240, ix = W - cx - 30 - iw, iy = cy + 30;
        ctx.save(); ctx.shadowColor = "rgba(0,0,0,.35)"; ctx.shadowBlur = 24; ctx.shadowOffsetY = 10;
        rr(ix, iy, iw, ih, 10); ctx.fillStyle = "#000"; ctx.fill(); ctx.restore();
        ctx.save(); rr(ix, iy, iw, ih, 10); ctx.clip();
        var k = Math.max(iw / cover.width, ih / cover.height); ctx.drawImage(cover, ix + (iw - cover.width * k) / 2, iy + (ih - cover.height * k) / 2, cover.width * k, cover.height * k); ctx.restore();
        tx = ix - 36; tw = tx - cx - 30;
      }
      ctx.textAlign = "right"; ctx.fillStyle = t.ink; ctx.font = font(800, 50);
      var tl = wrap(o.title || "", tw).slice(0, 2);
      tl.forEach(function (l, i) { ctx.fillText(l, tx, cy + 100 + i * 66); });
      ctx.fillStyle = t.sub; ctx.font = font(500, 38);
      if (o.author) ctx.fillText(o.author, tx, cy + 110 + tl.length * 66);
    }
    // پانویس
    ctx.textAlign = "center"; ctx.fillStyle = t.sub; ctx.font = font(500, 34);
    ctx.fillText((data.user ? "@" + data.user + " · " : "") + "hamvaraq.ir", W / 2, H - 120);
    ctx.restore();
  }

  var queued = false;
  function schedule() { if (queued) return; queued = true; requestAnimationFrame(function () { queued = false; draw(); count(); }); }
  function count() { var n = form.elements.text.value.length; root.querySelector("[data-story-count]").textContent = HV.formatFaNumber(n); syncPublish(); }
  function syncPublish() {
    var a = root.querySelector("[data-story-publish]"); if (!a) return;
    var o = opts(), q = new URLSearchParams({ quote: o.text, book_title: o.title, book_author: o.author });
    a.href = a.href.split("?")[0] + "?" + q.toString();
  }
  form.addEventListener("input", schedule); form.addEventListener("change", schedule);

  function blob() { return new Promise(function (res) { draw(); canvas.toBlob(res, "image/png"); }); }
  function fname() { return "hamvaraq-" + (data.mode || "story") + "-" + (data.slug || "story") + ".png"; }
  root.querySelector("[data-story-download]").addEventListener("click", function () {
    blob().then(function (b) {
      var a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = fname();
      document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
      HV.announce("تصویر استوری ذخیره شد.");
    });
  });
  var share = root.querySelector("[data-story-share]");
  if (navigator.canShare && navigator.canShare({ files: [new File([""], "x.png", { type: "image/png" })] })) {
    share.hidden = false;
    share.addEventListener("click", function () {
      blob().then(function (b) { return navigator.share({ files: [new File([b], fname(), { type: "image/png" })], title: opts().title }); }).catch(function () {});
    });
  }

  var fontsReady = document.fonts ? Promise.all([document.fonts.load(font(800, 40)), document.fonts.load(font(500, 40)), document.fonts.load(font(700, 40))]) : Promise.resolve();
  var coverReady = data.cover ? new Promise(function (res) {
    var im = new Image(); im.onload = function () { cover = im; res(); }; im.onerror = function () { res(); }; im.src = data.cover;
  }) : Promise.resolve();
  if (!data.cover) { var c = form.querySelector(".tpl-cover"); if (c) c.hidden = true; }
  Promise.all([fontsReady, coverReady]).then(function () { draw(); count(); status.hidden = true; root.classList.add("is-ready"); });
})();
