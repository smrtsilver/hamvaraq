from django import forms

EMPTY_LABEL = "انتخاب کنید"
DEFAULT_EMPTY = ("", "---------", "- Select an option -", "انتخاب کنید")


class PersianFormMixin:
    """
    گزینه‌ی خالیِ لیست‌های کشویی رو فارسی می‌کنه (پیش‌فرض جنگو انگلیسیه) و برای همه‌ی فیلدها
    یه autocomplete معقول می‌ذاره مگه اینکه خود فرم گذاشته باشه.
    """

    autocomplete_by_name = {"username": "username", "email": "email", "password": "current-password"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            # فقط برچسب پیش‌فرض (انگلیسی/خط‌چین) عوض می‌شه؛ برچسب‌هایی که خود فرم گذاشته («همه‌ی شهرها») دست‌نخورده می‌مونن
            if isinstance(field, forms.ModelChoiceField) and field.empty_label in DEFAULT_EMPTY:
                field.empty_label = EMPTY_LABEL
            elif isinstance(field, forms.ChoiceField) and not isinstance(field.widget, forms.RadioSelect):
                choices = list(field.choices)
                if choices and choices[0][0] == "" and str(choices[0][1]) in DEFAULT_EMPTY:
                    field.choices = [("", EMPTY_LABEL), *choices[1:]]
            if "autocomplete" not in field.widget.attrs and name in self.autocomplete_by_name:
                field.widget.attrs["autocomplete"] = self.autocomplete_by_name[name]
