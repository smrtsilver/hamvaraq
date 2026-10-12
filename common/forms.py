from django import forms

EMPTY_LABEL = "انتخاب کنید"


class PersianFormMixin:
    """
    گزینه‌ی خالیِ لیست‌های کشویی رو فارسی می‌کنه (پیش‌فرض جنگو انگلیسیه) و برای همه‌ی فیلدها
    یه autocomplete معقول می‌ذاره مگه اینکه خود فرم گذاشته باشه.
    """

    autocomplete_by_name = {"username": "username", "email": "email", "password": "current-password"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field, forms.ModelChoiceField) and field.empty_label is not None:
                field.empty_label = EMPTY_LABEL
            elif isinstance(field, forms.ChoiceField) and not isinstance(field.widget, forms.RadioSelect):
                choices = list(field.choices)
                if choices and choices[0][0] == "":
                    field.choices = [("", EMPTY_LABEL), *choices[1:]]
            if "autocomplete" not in field.widget.attrs and name in self.autocomplete_by_name:
                field.widget.attrs["autocomplete"] = self.autocomplete_by_name[name]
