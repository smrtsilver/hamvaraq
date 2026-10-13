// مودال دسترس‌پذیر (جایگزین confirm/alert/prompt مرورگر): HV.modal.confirm / info / prompt → Promise.
// <dialog> بومی: role=dialog و aria-modal ضمنی، تله‌ی فوکوس و Escape از مرورگر، بازگرداندن فوکوس دستی.
// no-JS fallback: فرم‌های دارای data-confirm بدون مودال مستقیم ارسال می‌شن (اقدام سمت سرور همچنان معتبره).
(() => {
    const HV = (window.HV = window.HV || {});
    let seq = 0;

    function open({title, message, confirmLabel = "تأیید", cancelLabel = "لغو", danger = false, input = null, info = false}) {
        return new Promise((resolve) => {
            const opener = document.activeElement;
            const id = `hv-modal-${++seq}`;
            const dlg = document.createElement("dialog");
            dlg.className = "hv-modal" + (danger ? " hv-modal--danger" : "");
            dlg.setAttribute("aria-labelledby", `${id}-t`);
            dlg.setAttribute("aria-describedby", `${id}-d`);
            const box = document.createElement("div");
            box.className = "hv-modal-box";
            const h = document.createElement("h2"); h.id = `${id}-t`; h.className = "hv-modal-title"; h.textContent = title || (danger ? "مطمئنی؟" : "تأیید");
            const p = document.createElement("p"); p.id = `${id}-d`; p.className = "hv-modal-msg"; p.textContent = message || "";
            box.append(h, p);
            let field = null;
            if (input) {
                const wrap = document.createElement("div"); wrap.className = "field";
                const label = document.createElement("label"); label.htmlFor = `${id}-i`; label.textContent = input.label || "";
                field = document.createElement("input"); field.id = `${id}-i`; field.type = "text"; field.value = input.value || ""; field.autocomplete = "off";
                if (input.placeholder) field.placeholder = input.placeholder;
                if (input.maxLength) field.maxLength = input.maxLength;
                wrap.append(label, field); box.append(wrap);
            }
            const actions = document.createElement("div"); actions.className = "hv-modal-actions";
            const ok = document.createElement("button"); ok.type = "button"; ok.className = "btn" + (danger ? " btn-danger" : ""); ok.textContent = confirmLabel;
            const cancel = document.createElement("button"); cancel.type = "button"; cancel.className = "btn btn-ghost"; cancel.textContent = cancelLabel;
            if (info) actions.append(ok); else actions.append(ok, cancel);
            box.append(actions); dlg.append(box); document.body.append(dlg);

            let result = info ? true : (input ? null : false);
            const done = (v) => { result = v; dlg.close(); };
            ok.addEventListener("click", () => {
                if (input && input.required && !field.value.trim()) { field.setAttribute("aria-invalid", "true"); field.focus(); return; }
                done(input ? field.value.trim() : true);
            });
            cancel.addEventListener("click", () => done(input ? null : false));
            dlg.addEventListener("click", (e) => { if (e.target === dlg) done(info ? true : (input ? null : false)); });
            if (field) field.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); ok.click(); } });
            dlg.addEventListener("close", () => {
                dlg.remove();
                if (opener && opener.focus && document.contains(opener)) opener.focus();
                resolve(result);
            });
            dlg.showModal();
            (field || (danger ? cancel : ok)).focus();      // اقدام خطرناک: پیش‌فرض فوکوس روی «لغو»
        });
    }

    HV.modal = {
        confirm: (o) => open({...o}),
        info: (o) => open({...o, info: true, confirmLabel: (o && o.confirmLabel) || "باشه"}),
        prompt: (o) => open({...o, input: {label: o.label, value: o.value, placeholder: o.placeholder, required: o.required, maxLength: o.maxLength}}),
    };

    // ---- اتصال به data-confirm روی فرم، دکمه و لینک ----
    const opts = (el) => {
        const msg = el.dataset.confirm;
        const danger = el.dataset.confirmTone === "danger" || /danger/.test(el.className) || /حذف|لغو|مسدود/.test(msg);
        return {
            message: msg, danger,
            confirmLabel: el.dataset.confirmLabel || (/حذف/.test(msg) ? "حذف" : "تأیید"),
            cancelLabel: el.dataset.cancelLabel || "لغو",
        };
    };
    document.addEventListener("click", async (e) => {
        const el = e.target.closest("button[data-confirm], a[data-confirm]");
        if (!el || el.dataset.confirmed) return;
        e.preventDefault(); e.stopPropagation();
        if (await HV.modal.confirm(opts(el))) { el.dataset.confirmed = "1"; el.click(); }
    }, true);
    document.addEventListener("submit", async (e) => {
        const f = e.target;
        if (!f.dataset || !f.dataset.confirm || f.dataset.confirmed) return;
        e.preventDefault();
        if (await HV.modal.confirm(opts(f))) { f.dataset.confirmed = "1"; f.requestSubmit(e.submitter || undefined); }
    });
})();
