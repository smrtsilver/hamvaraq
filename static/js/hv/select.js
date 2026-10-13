// لیست کشویی با ظاهر سایت به‌جای انتخابگر خام سیستم‌عامل (به‌خصوص اندروید).
// خود <select> سر جاش می‌مونه (مقدار فرم، اعتبارسنجی، رویداد change)؛ فقط دیده نمی‌شه.
// بدون JS همون select ساده کار می‌کنه. data-native = دست نزن.
(() => {
    let uid = 0, openOne = null;

    function label(sel) {
        const o = sel.options[sel.selectedIndex];
        return o ? o.textContent.trim() : "";
    }

    function enhance(sel) {
        if (sel.dataset.hvsel || sel.multiple || sel.hasAttribute("data-native") || sel.hasAttribute("data-combobox") || sel.size > 1) return;
        sel.dataset.hvsel = "1";
        const id = `hvsel-${++uid}`;
        const wrap = document.createElement("div");
        wrap.className = "hvsel";
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "hvsel-btn";
        btn.setAttribute("aria-haspopup", "listbox");
        btn.setAttribute("aria-expanded", "false");
        btn.setAttribute("aria-controls", id);
        const lab = sel.labels && sel.labels[0];
        if (lab) { lab.id = lab.id || `${id}-l`; btn.setAttribute("aria-labelledby", `${lab.id} ${id}-v`); lab.addEventListener("click", (e) => { e.preventDefault(); btn.focus(); }); }
        else if (sel.getAttribute("aria-label")) btn.setAttribute("aria-label", sel.getAttribute("aria-label"));
        const val = document.createElement("span"); val.className = "hvsel-val"; val.id = `${id}-v`;
        const chev = document.createElement("span"); chev.className = "hvsel-chev"; chev.setAttribute("aria-hidden", "true");
        btn.append(val, chev);
        const list = document.createElement("ul");
        list.className = "hvsel-list"; list.id = id; list.setAttribute("role", "listbox"); list.hidden = true; list.tabIndex = -1;
        sel.before(wrap);
        wrap.append(sel, btn, list);
        sel.classList.add("hvsel-native");
        sel.tabIndex = -1;
        sel.setAttribute("aria-hidden", "true");

        const sync = () => {
            val.textContent = label(sel);
            btn.classList.toggle("is-empty", !sel.value);
            btn.disabled = sel.disabled;
            wrap.classList.toggle("has-error", sel.getAttribute("aria-invalid") === "true");
        };
        const items = () => [...list.querySelectorAll("li:not([aria-disabled])")];
        const build = () => {
            list.replaceChildren(...[...sel.options].map((o, i) => {
                const li = document.createElement("li");
                li.id = `${id}-o${i}`; li.setAttribute("role", "option"); li.dataset.i = i;
                li.textContent = o.textContent.trim();
                li.setAttribute("aria-selected", String(i === sel.selectedIndex));
                if (o.disabled) li.setAttribute("aria-disabled", "true");
                if (!o.value) li.classList.add("is-placeholder");
                return li;
            }));
        };
        const activate = (li) => {
            list.querySelectorAll(".is-active").forEach((x) => x.classList.remove("is-active"));
            if (!li) return;
            li.classList.add("is-active");
            list.setAttribute("aria-activedescendant", li.id);
            li.scrollIntoView({block: "nearest"});
        };
        const close = (focus = true) => {
            if (list.hidden) return;
            list.hidden = true; wrap.classList.remove("is-open", "drop-up");
            btn.setAttribute("aria-expanded", "false");
            if (openOne === close) openOne = null;
            if (focus) btn.focus();
        };
        const open = () => {
            if (btn.disabled) return;
            if (openOne) openOne(false);
            build();
            list.hidden = false; wrap.classList.add("is-open");
            const r = btn.getBoundingClientRect();
            wrap.classList.toggle("drop-up", window.innerHeight - r.bottom < Math.min(300, list.scrollHeight + 16) && r.top > window.innerHeight - r.bottom);
            btn.setAttribute("aria-expanded", "true");
            openOne = close;
            list.focus({preventScroll: true});
            activate(list.querySelector('[aria-selected="true"]') || items()[0]);
        };
        const choose = (li) => {
            if (!li || li.hasAttribute("aria-disabled")) return;
            const i = +li.dataset.i;
            const changed = sel.selectedIndex !== i;
            sel.selectedIndex = i;
            sync(); close();
            if (changed) { sel.dispatchEvent(new Event("input", {bubbles: true})); sel.dispatchEvent(new Event("change", {bubbles: true})); }
        };

        btn.addEventListener("click", () => (list.hidden ? open() : close()));
        btn.addEventListener("keydown", (e) => {
            if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); open(); }
        });
        list.addEventListener("click", (e) => choose(e.target.closest("li")));
        list.addEventListener("keydown", (e) => {
            const all = items(), cur = list.querySelector(".is-active"), i = all.indexOf(cur);
            if (e.key === "ArrowDown") { e.preventDefault(); activate(all[Math.min(all.length - 1, i + 1)]); }
            else if (e.key === "ArrowUp") { e.preventDefault(); activate(all[Math.max(0, i - 1)]); }
            else if (e.key === "Home") { e.preventDefault(); activate(all[0]); }
            else if (e.key === "End") { e.preventDefault(); activate(all[all.length - 1]); }
            else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(cur); }
            else if (e.key === "Escape" || e.key === "Tab") { e.preventDefault(); close(); }
            else if (e.key.length === 1) { const hit = all.find((li) => li.textContent.trim().startsWith(e.key)); if (hit) activate(hit); }
        });
        sel.addEventListener("change", sync);
        new MutationObserver(sync).observe(sel, {childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "aria-invalid"]});
        sel.form && sel.form.addEventListener("reset", () => setTimeout(sync));
        sync();
    }

    document.addEventListener("click", (e) => { if (openOne && !e.target.closest(".hvsel.is-open")) openOne(false); });
    window.addEventListener("resize", () => openOne && openOne(false));

    const run = (root = document) => root.querySelectorAll("select").forEach(enhance);
    window.HV = window.HV || {};
    window.HV.enhanceSelects = run;
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => run()); else run();
})();
