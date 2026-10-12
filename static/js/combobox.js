// لیست‌های کشویی جستجویی (combobox) + آبشاری استان ← شهر. بدون این فایل، <select> های ساده کار می‌کنن.
(() => {
    const DIGITS = {"۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9"};
    // همون نرمال‌سازی سمت سرور (common/text.py): ی و ک عربی، رقم، نیم‌فاصله، اعراب
    const norm = (t) => (t || "").replace(/[۰-۹٠-٩]/g, (d) => DIGITS[d]).replace(/[يىئ]/g, "ی").replace(/ك/g, "ک")
        .replace(/ة/g, "ه").replace(/[ً-ٰٟـ‌‍]/g, "").toLowerCase().replace(/\s+/g, " ").trim();

    let uid = 0;

    class Combo {
        constructor(select) {
            this.select = select;
            this.id = `combo-${++uid}`;
            this.group = select.closest("[data-location-group], form") || document;
            this.build();
            this.syncFromSelect();
        }

        build() {
            const s = this.select;
            this.wrap = document.createElement("div");
            this.wrap.className = "combo";
            this.input = document.createElement("input");
            this.input.type = "text";
            this.input.className = "combo-input";
            this.input.setAttribute("role", "combobox");
            this.input.setAttribute("aria-autocomplete", "list");
            this.input.setAttribute("aria-expanded", "false");
            this.input.setAttribute("aria-controls", this.id);
            this.input.autocomplete = "off";
            this.input.placeholder = s.dataset.placeholder || "جستجو…";
            this.input.setAttribute("autocapitalize", "off");
            this.input.enterKeyHint = "search";
            const label = document.querySelector(`label[for="${s.id}"]`);
            if (label) { this.input.id = `${s.id}-combo`; label.htmlFor = this.input.id; }
            this.list = document.createElement("ul");
            this.list.className = "combo-list";
            this.list.id = this.id;
            this.list.setAttribute("role", "listbox");
            this.list.hidden = true;
            this.clear = document.createElement("button");
            this.clear.type = "button";
            this.clear.className = "combo-clear";
            this.clear.setAttribute("aria-label", "پاک کردن انتخاب");
            this.clear.textContent = "×";
            this.clear.hidden = true;
            s.before(this.wrap);
            this.wrap.append(this.input, this.clear, this.list, s);
            s.classList.add("combo-native");
            s.tabIndex = -1;
            s.setAttribute("aria-hidden", "true");

            this.input.addEventListener("focus", () => { this.input.select(); this.open(); });
            this.input.addEventListener("input", () => this.open());
            this.input.addEventListener("keydown", (e) => this.key(e));
            this.input.addEventListener("blur", () => setTimeout(() => this.close(true), 150));
            this.list.addEventListener("mousedown", (e) => e.preventDefault());
            this.list.addEventListener("click", (e) => {
                const li = e.target.closest("li[data-value]");
                if (li) this.choose(li.dataset.value);
            });
            this.clear.addEventListener("click", () => { this.choose(""); this.input.focus(); });
            s.addEventListener("change", () => this.syncFromSelect());
        }

        provinceId() {
            if (this.select.dataset.location !== "city") return "";
            const p = this.group.querySelector('select[data-location="province"]');
            return p ? p.value : "";
        }

        options(everywhere) {
            const province = everywhere ? "" : this.provinceId();
            return [...this.select.options].filter((o) => o.value && (!province || !o.dataset.province || o.dataset.province === province))
                .map((o) => ({value: o.value, label: province && o.dataset.name ? o.dataset.name : o.text, search: norm(o.text), province: o.dataset.province}));
        }

        syncFromSelect() {
            const o = this.select.selectedOptions[0];
            const province = this.provinceId();
            this.input.value = o && o.value ? (province && o.dataset.name ? o.dataset.name : o.text) : "";
            this.clear.hidden = !this.input.value || this.select.required;
        }

        open() {
            const q = norm(this.input.value === (this.select.selectedOptions[0] || {}).text ? "" : this.input.value);
            let items = this.options().filter((o) => !q || o.search.includes(q)).slice(0, 80);
            // تو استان انتخاب‌شده پیدا نشد؟ تو همه‌ی استان‌ها بگرد (با نام استان کنار هر شهر)
            if (!items.length && q && this.provinceId()) items = this.options(true).filter((o) => o.search.includes(q)).slice(0, 80);
            this.list.replaceChildren();
            this.active = -1;
            items.forEach((o, i) => {
                const li = document.createElement("li");
                li.setAttribute("role", "option");
                li.dataset.value = o.value;
                li.id = `${this.id}-${i}`;
                li.textContent = o.label;
                if (o.value === this.select.value) li.setAttribute("aria-selected", "true");
                this.list.append(li);
            });
            if (!items.length) {
                const li = document.createElement("li");
                li.className = "combo-empty";
                li.textContent = this.provinceId() || this.select.dataset.location !== "city" ? "موردی پیدا نشد" : "اول استان رو انتخاب کن یا اسم شهر رو بنویس";
                this.list.append(li);
            }
            this.list.hidden = false;
            this.input.setAttribute("aria-expanded", "true");
        }

        close(restore) {
            this.list.hidden = true;
            this.input.setAttribute("aria-expanded", "false");
            this.input.removeAttribute("aria-activedescendant");
            if (restore) this.syncFromSelect();
        }

        move(delta) {
            const items = [...this.list.querySelectorAll("li[data-value]")];
            if (!items.length) return;
            this.active = (this.active + delta + items.length) % items.length;
            items.forEach((li, i) => li.classList.toggle("is-active", i === this.active));
            items[this.active].scrollIntoView({block: "nearest"});
            this.input.setAttribute("aria-activedescendant", items[this.active].id);
        }

        key(e) {
            if (e.key === "ArrowDown") { e.preventDefault(); this.list.hidden ? this.open() : this.move(1); }
            else if (e.key === "ArrowUp") { e.preventDefault(); this.move(-1); }
            else if (e.key === "Enter") {
                const li = this.list.querySelector("li.is-active") || (this.list.querySelectorAll("li[data-value]").length === 1 ? this.list.querySelector("li[data-value]") : null);
                if (li && !this.list.hidden) { e.preventDefault(); this.choose(li.dataset.value); }
            } else if (e.key === "Escape") this.close(true);
        }

        choose(value) {
            this.select.value = value;
            this.select.dispatchEvent(new Event("change", {bubbles: true}));
            this.close(false);
            this.syncFromSelect();
        }
    }

    function init() {
        const combos = new Map();
        document.querySelectorAll(".filterbar select:not([data-combobox])").forEach((s) => {
            const empty = s.querySelector('option[value=""]');
            if (!empty) return; // لیست بی‌گزینه‌ی خالی (مثل مرتب‌سازی) همون select ساده می‌مونه
            s.dataset.combobox = ""; s.dataset.placeholder = empty.textContent;
        });
        document.querySelectorAll("select[data-combobox]").forEach((s) => combos.set(s, new Combo(s)));
        // آبشاری: عوض شدن استان ← شهر نامربوط پاک می‌شه و لیست شهرها فیلتر می‌شه
        document.querySelectorAll('select[data-location="province"]').forEach((p) => {
            p.addEventListener("change", () => {
                const scope = p.closest("[data-location-group], form") || document;
                const city = scope.querySelector('select[data-location="city"]');
                if (!city) return;
                const o = city.selectedOptions[0];
                if (o && o.value && p.value && o.dataset.province !== p.value) city.value = "";
                city.dispatchEvent(new Event("change", {bubbles: true}));
            });
        });
        // انتخاب شهر، استان رو خودکار پر می‌کنه (وقتی کاربر اول شهر رو جستجو کرده)
        document.querySelectorAll('select[data-location="city"]').forEach((c) => {
            c.addEventListener("change", () => {
                const o = c.selectedOptions[0];
                const scope = c.closest("[data-location-group], form") || document;
                const p = scope.querySelector('select[data-location="province"]');
                if (o && o.value && p && p.value !== o.dataset.province) {
                    p.value = o.dataset.province;
                    p.dispatchEvent(new Event("change", {bubbles: true}));
                    c.value = o.value;
                    combos.get(c) && combos.get(c).syncFromSelect();
                }
            });
        });
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
