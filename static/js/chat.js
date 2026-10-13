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

    // فاصله‌ی پرسش: ۵ ثانیه؛ بعد از ۳ پاسخ خالی ۱۵ و بعد از ۶ تا ۳۰ ثانیه؛ با پیام تازه یا ارسال برمی‌گرده
    let empties = 0, timer = null;
    const delay = () => (empties >= 6 ? 30000 : empties >= 3 ? 15000 : 5000);
    const schedule = () => { clearTimeout(timer); timer = setTimeout(poll, delay()); };

    async function poll() {
        if (busy || document.hidden) { schedule(); return; }
        busy = true;
        try {
            const r = await fetch(`${box.dataset.pollUrl}?after=${lastId}`, {credentials: "same-origin"});
            if (r.ok) {
                const d = await r.json();
                d.messages.forEach(addMessage);
                if (d.messages.length) { empties = 0; toBottom(); } else empties += 1;
            }
        } catch (_) { empties += 1; }
        busy = false;
        schedule();
    }

    function pending(text) {
        const div = document.createElement("div");
        div.className = "msg mine msg-sending";
        const t = document.createElement("span");
        t.className = "msg-text";
        t.textContent = text;
        const st = document.createElement("small");
        st.textContent = "در حال ارسال…";
        div.append(t, st);
        box.append(div);
        toBottom();
        return {div, st};
    }

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = form.elements.text;
        const text = input.value.trim();
        if (!text) return;
        const data = new FormData(form);
        const p = pending(text);
        input.value = "";
        try {
            const r = await fetch(box.dataset.sendUrl, {
                method: "POST", body: data, credentials: "same-origin",
                headers: {"X-Requested-With": "XMLHttpRequest"},
            });
            if (r.status === 429) throw new Error("rate");
            if (!r.ok) throw new Error("fail");
            empties = 0;
            await poll();
            p.div.remove();
        } catch (err) {
            p.div.classList.add("msg-failed");
            p.st.textContent = err.message === "rate" ? "زیاد بود؛ چند دقیقه صبر کن" : "نرفت؛ دوباره بفرست";
            input.value = text;
            if (err.message === "rate") window.HV.announce("پیام‌هات زیاد بود؛ چند دقیقه صبر کن.", "error");
        }
    });

    schedule();
    document.addEventListener("visibilitychange", () => { if (!document.hidden) { empties = 0; poll(); } });
})();
