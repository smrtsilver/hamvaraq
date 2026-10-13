// فرم ثبت کتاب روی موبایل: سه قدم (کدوم کتاب ← کجاست ← عکس و توضیح) با «بعدی/قبلی»؛ بدون جاوااسکریپت همه‌ی بخش‌ها دیده می‌شن.
(() => {
    const form = document.querySelector("form[data-stepper]");
    const mq = window.matchMedia("(max-width: 700px)");
    if (!form) return;
    const sections = [...form.querySelectorAll(".form-section")];
    if (sections.length < 2) return;
    const actions = form.querySelector(".form-actions");
    let step = 0, bar, prev, next, label;

    function build() {
        bar = document.createElement("div");
        bar.className = "step-nav";
        bar.innerHTML = '<button type="button" class="btn btn-ghost" data-step-prev>قبلی</button><span class="step-label" aria-live="polite"></span><button type="button" class="btn" data-step-next>بعدی</button>';
        actions.before(bar);
        prev = bar.querySelector("[data-step-prev]");
        next = bar.querySelector("[data-step-next]");
        label = bar.querySelector(".step-label");
        prev.addEventListener("click", () => go(step - 1));
        next.addEventListener("click", () => { if (valid(sections[step])) go(step + 1); });
    }

    function valid(section) {
        let ok = true;
        section.querySelectorAll("[required]").forEach((f) => {
            const empty = !String(f.value || "").trim();
            const field = f.closest(".field");
            let err = field && field.querySelector(".err.local");
            if (empty) {
                ok = false;
                if (field && !err) { err = document.createElement("p"); err.className = "err local"; err.setAttribute("role", "alert"); err.textContent = "این فیلد لازمه."; field.append(err); }
            } else if (err) err.remove();
        });
        if (!ok) { const first = section.querySelector("[required]:invalid, [required]"); const bad = [...section.querySelectorAll("[required]")].find((f) => !String(f.value || "").trim()); (bad || first).focus(); }
        return ok;
    }

    function go(n) {
        step = Math.max(0, Math.min(sections.length - 1, n));
        sections.forEach((s, i) => { s.hidden = i !== step; });
        prev.hidden = step === 0;
        next.hidden = step === sections.length - 1;
        actions.hidden = step !== sections.length - 1;
        label.textContent = `قدم ${String(step + 1).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d])} از ${String(sections.length).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d])}`;
        window.scrollTo({top: 0, behavior: "smooth"});
    }

    function apply() {
        if (mq.matches) {
            if (!bar) build();
            bar.hidden = false;
            go(step);
        } else {
            if (bar) bar.hidden = true;
            sections.forEach((s) => { s.hidden = false; });
            actions.hidden = false;
        }
    }
    mq.addEventListener("change", apply);
    apply();
})();
