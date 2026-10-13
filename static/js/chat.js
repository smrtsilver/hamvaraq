// چت مبادله: ارسال بدون reload و گرفتن پیام‌های تازه هر چند ثانیه (فقط وقتی تب بازه).
(() => {
    const box = document.getElementById("chat-box");
    if (!box) return;
    const form = document.getElementById("chat-form");
    const empty = document.getElementById("chat-empty");
    let lastId = parseInt(box.dataset.lastId || "0", 10);
    let busy = false;

    function addMessage(m) {
        const div = document.createElement("div");
        div.className = "msg" + (m.mine ? " mine" : "");
        const who = document.createElement("b");
        who.textContent = m.sender;
        const text = document.createElement("span");
        text.className = "msg-text";
        text.textContent = m.text;             // textContent: متن کاربر هیچ‌وقت HTML نمی‌شه
        const meta = document.createElement("small");
        if (m.report_url) {
            const a = document.createElement("a");
            a.href = m.report_url;
            a.textContent = "گزارش";
            meta.append(a);
        }
        const time = document.createElement("span");
        time.textContent = m.time;
        meta.append(time);
        div.append(who, text, meta);
        box.append(div);
        lastId = Math.max(lastId, m.id);
        if (empty) empty.hidden = true;
    }

    const toBottom = () => { box.scrollTop = box.scrollHeight; };
    toBottom();

    async function poll() {
        if (busy || document.hidden) return;
        busy = true;
        try {
            const r = await fetch(`${box.dataset.pollUrl}?after=${lastId}`, {credentials: "same-origin"});
            if (r.ok) {
                const d = await r.json();
                d.messages.forEach(addMessage);
                if (d.messages.length) toBottom();
            }
        } catch (_) { /* بعدی دوباره امتحان می‌کنه */ }
        busy = false;
    }

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = form.elements.text;
        if (!input.value.trim()) return;
        const data = new FormData(form);
        const r = await fetch(box.dataset.sendUrl, {
            method: "POST", body: data, credentials: "same-origin",
            headers: {"X-Requested-With": "XMLHttpRequest"},
        });
        if (r.status === 429) { window.HV.announce("پیام‌هات زیاد بود؛ چند دقیقه صبر کن.", "error"); return; }
        if (r.ok) { input.value = ""; poll(); }
    });

    setInterval(poll, 5000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
})();
