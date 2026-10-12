"""
ترجمه‌ی متن‌هایی از جنگو که تو نسخه‌ی فعلی هنوز فارسی نشدن (ادمین، اعتبارسنجی فرم‌ها…).
منبع حقیقت: همین فایل ← locale/fa/LC_MESSAGES/django.po و django.mo ساخته می‌شه.
اجرا:  python scripts/build_locale.py   (نیاز به polib: pip install -r requirements-dev.txt)
"""

import polib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "locale" / "fa" / "LC_MESSAGES"

# msgid: متن فارسی  |  یا (مفرد، جمع) برای msgid های دوشکلی
T = {
    "Select this object for an action - {}": "انتخاب این مورد برای اجرای عملیات - {}",
    'The app "%s" could not be found.': "برنامه‌ی «%s» پیدا نشد.",
    "%(count)s %(name)s was changed successfully.": ("%(count)s %(name)s با موفقیت تغییر کرد.", "%(count)s %(name)s با موفقیت تغییر کردند."),
    "%(total_count)s selected": ("%(total_count)s مورد انتخاب شد", "همه‌ی %(total_count)s مورد انتخاب شد"),
    "%(class_name)s %(instance)s": "%(class_name)s %(instance)s",
    ", ": "، ",
    "…and %(count)d more object.": ("…و %(count)d مورد دیگر.", "…و %(count)d مورد دیگر."),
    "Run": "اجرا",
    "Breadcrumbs": "مسیر صفحه",
    "Hold down “Control”, or “Command” on a Mac, to select more than one.": "برای انتخاب چند مورد، کلید کنترل را نگه دارید و روی موارد کلیک کنید.",
    "Model name": "نام مدل",
    "Please correct the error below.": ("لطفاً خطای زیر را اصلاح کنید.", "لطفاً خطاهای زیر را اصلاح کنید."),
    "This action will <strong>enable</strong> password-based authentication for this user.":
        "این کار ورود با رمز را برای این کاربر <strong>فعال</strong> می‌کند.",
    "Filter by %(field_name)s": "فیلتر بر اساس %(field_name)s",
    "Pagination %(name)s entries": "صفحه‌بندی %(name)s",
    "Pagination %(name)s": "صفحه‌بندی %(name)s",
    "entry": ("مورد", "مورد"),
    "Search %(name)s": "جستجو در %(name)s",
    "%(counter)s result": ("%(counter)s نتیجه", "%(counter)s نتیجه"),
    "Logout": "خروج",
    "In case you’ve forgotten, you are:": "اگر فراموش کرده‌اید، شما این کاربر هستید:",
    'Choose %s by selecting them and then select the "Choose" arrow button.': "%s را انتخاب کنید و با دکمه‌ی فلش «انتخاب» به لیست انتخاب‌شده‌ها ببرید.",
    "Choose all %s": "انتخاب همه‌ی %s",
    "Choose selected %s": "انتخاب %s برگزیده",
    "Remove selected %s": "حذف %s برگزیده",
    'Remove %s by selecting them and then select the "Remove" arrow button.': "%s را انتخاب کنید و با دکمه‌ی فلش «حذف» از لیست بردارید.",
    "Type into this box to filter down the list of selected %s.": "برای فیلتر کردن لیست %s، در این کادر بنویسید.",
    "(click to clear)": "(برای پاک کردن کلیک کنید)",
    "Remove all %s": "حذف همه‌ی %s",
    "%s selected option not visible": ("%s گزینه‌ی انتخاب‌شده دیده نمی‌شود", "%s گزینه‌ی انتخاب‌شده دیده نمی‌شوند"),
    "%(sel)s of %(cnt)s selected": ("%(sel)s از %(cnt)s انتخاب شد", "%(sel)s از %(cnt)s انتخاب شد"),
    "You have selected an action, and you haven’t made any changes on individual fields. You’re probably looking for the Run button rather than the Save button.":
        "یک عملیات انتخاب کرده‌اید ولی تغییری در فیلدها نداده‌اید. احتمالاً دکمه‌ی «اجرا» را می‌خواهید، نه «ذخیره».",
    "server": "سرور",
    "Today (%(date)s)": "امروز (%(date)s)",
    "Yesterday (%(date)s)": "دیروز (%(date)s)",
    "Tomorrow (%(date)s)": "فردا (%(date)s)",
    "Previous (%(month)s %(year)s)": "قبلی (%(month)s %(year)s)",
    "Next (%(month)s %(year)s)": "بعدی (%(month)s %(year)s)",
    "Sunday": "یکشنبه", "Monday": "دوشنبه", "Tuesday": "سه‌شنبه", "Wednesday": "چهارشنبه", "Thursday": "پنجشنبه",
    "Friday": "جمعه", "Saturday": "شنبه",
    "Sun": "یک", "Mon": "دو", "Tue": "سه", "Wed": "چهار", "Thur": "پنج", "Fri": "جمعه", "Sat": "شنبه",
    "%(month)s %(day)s, %(year)s": "%(day)s %(month)s %(year)s",
    "%s (today, current selection)": "%s (امروز، انتخاب فعلی)",
    "%s (today)": "%s (امروز)",
    "%s (current selection)": "%s (انتخاب فعلی)",
    "Conflicting form data submitted. Please try again.": "داده‌های ارسالی با هم تداخل دارند. دوباره امتحان کنید.",
    "Password-based authentication was disabled.": "ورود با رمز غیرفعال شد.",
    "Set password: %s": "تعیین رمز: %s",
    "Reset password": "بازنشانی رمز",
    "Set password": "تعیین رمز",
    "Whether the user will be able to authenticate using a password or not. If disabled, they may still be able to authenticate using other backends, such as Single Sign-On or LDAP.":
        "آیا کاربر می‌تواند با رمز وارد شود یا نه. اگر غیرفعال باشد شاید از راه‌های دیگر بتواند وارد شود.",
    "Password-based authentication": "ورود با رمز",
    "Enabled": "فعال",
    "Disabled": "غیرفعال",
    "Raw passwords are not stored, so there is no way to see the user’s password.": "رمزها به‌صورت خام ذخیره نمی‌شوند و راهی برای دیدن رمز کاربر نیست.",
    "Enable password-based authentication for this user by setting a password.": "با تعیین رمز، ورود با رمز را برای این کاربر فعال کنید.",
    "salt": "نمک", "hash": "هش",
    "This password is too short. It must contain at least %d character.": ("این رمز خیلی کوتاه است؛ حداقل %d نویسه لازم است.", "این رمز خیلی کوتاه است؛ حداقل %d نویسه لازم است."),
    "Your password must contain at least %(min_length)d character.": ("رمز باید حداقل %(min_length)d نویسه باشد.", "رمز باید حداقل %(min_length)d نویسه باشد."),
    "Enter a valid username. This value may contain only unaccented lowercase a-z and uppercase A-Z letters, numbers, and @/./+/-/_ characters.":
        "نام کاربری معتبر وارد کنید؛ فقط حرف، عدد و @ . + - _ مجازند.",
    "Enter a valid domain name.": "نام دامنه‌ی معتبر وارد کنید.",
    "Enter a valid %(protocol)s address.": "نشانی %(protocol)s معتبر وارد کنید.",
    "Ensure this value is a multiple of step size %(limit_value)s.": "این مقدار باید مضرب %(limit_value)s باشد.",
    "Ensure this value has at least %(limit_value)d character (it has %(show_value)d).":
        ("این مقدار باید حداقل %(limit_value)d نویسه باشد (الان %(show_value)d نویسه دارد).", "این مقدار باید حداقل %(limit_value)d نویسه باشد (الان %(show_value)d نویسه دارد)."),
    "Ensure this value has at most %(limit_value)d character (it has %(show_value)d).":
        ("این مقدار باید حداکثر %(limit_value)d نویسه باشد (الان %(show_value)d نویسه دارد).", "این مقدار باید حداکثر %(limit_value)d نویسه باشد (الان %(show_value)d نویسه دارد)."),
    "Ensure that there are no more than %(max)s digit in total.": ("در مجموع حداکثر %(max)s رقم مجاز است.", "در مجموع حداکثر %(max)s رقم مجاز است."),
    "Ensure that there are no more than %(max)s decimal place.": ("حداکثر %(max)s رقم اعشار مجاز است.", "حداکثر %(max)s رقم اعشار مجاز است."),
    "Ensure that there are no more than %(max)s digit before the decimal point.": ("حداکثر %(max)s رقم قبل از ممیز مجاز است.", "حداکثر %(max)s رقم قبل از ممیز مجاز است."),
    "Constraint “%(name)s” is violated.": "محدودیت «%(name)s» رعایت نشده است.",
    "- Select an option -": "انتخاب کنید",
    "%(model)s instance with %(field)s %(value)r is not a valid choice.": "%(model)s با %(field)s %(value)r گزینه‌ی معتبری نیست.",
    "Please submit at most %(num)d form.": ("حداکثر %(num)d فرم ارسال کنید.", "حداکثر %(num)d فرم ارسال کنید."),
    "Please submit at least %(num)d form.": ("حداقل %(num)d فرم ارسال کنید.", "حداقل %(num)d فرم ارسال کنید."),
    "No %s matches the given query.": "هیچ %s با این جستجو یافت نشد.",
    "Ready": "آماده", "Running": "در حال اجرا", "Failed": "ناموفق", "Successful": "موفق",
    "%(size)d byte": ("%(size)d بایت", "%(size)d بایت"),
    "%s KB": "%s کیلوبایت", "%s MB": "%s مگابایت", "%s GB": "%s گیگابایت", "%s TB": "%s ترابایت", "%s PB": "%s پتابایت",
    "an hour ago": ("یک ساعت پیش", "%(count)s ساعت پیش"),
    "a minute ago": ("یک دقیقه پیش", "%(count)s دقیقه پیش"),
    "%(num)d year": ("%(num)d سال", "%(num)d سال"), "%(num)d month": ("%(num)d ماه", "%(num)d ماه"),
    "%(num)d week": ("%(num)d هفته", "%(num)d هفته"), "%(num)d day": ("%(num)d روز", "%(num)d روز"),
    "%(num)d hour": ("%(num)d ساعت", "%(num)d ساعت"), "%(num)d minute": ("%(num)d دقیقه", "%(num)d دقیقه"),
    "…": "…",
    "%(truncated_text)s…": "%(truncated_text)s…",
    ":": ":",
}
PLURAL_IDS = {
    "%(count)s %(name)s was changed successfully.": "%(count)s %(name)s were changed successfully.",
    "%(total_count)s selected": "All %(total_count)s selected",
    "…and %(count)d more object.": "…and %(count)d more objects.",
    "Please correct the error below.": "Please correct the errors below.",
    "entry": "entries", "%(counter)s result": "%(counter)s results",
    "%s selected option not visible": "%s selected options not visible",
    "%(sel)s of %(cnt)s selected": "%(sel)s of %(cnt)s selected",
    "This password is too short. It must contain at least %d character.": "This password is too short. It must contain at least %d characters.",
    "Your password must contain at least %(min_length)d character.": "Your password must contain at least %(min_length)d characters.",
    "Ensure this value has at least %(limit_value)d character (it has %(show_value)d).": "Ensure this value has at least %(limit_value)d characters (it has %(show_value)d).",
    "Ensure this value has at most %(limit_value)d character (it has %(show_value)d).": "Ensure this value has at most %(limit_value)d characters (it has %(show_value)d).",
    "Ensure that there are no more than %(max)s digit in total.": "Ensure that there are no more than %(max)s digits in total.",
    "Ensure that there are no more than %(max)s decimal place.": "Ensure that there are no more than %(max)s decimal places.",
    "Ensure that there are no more than %(max)s digit before the decimal point.": "Ensure that there are no more than %(max)s digits before the decimal point.",
    "Please submit at most %(num)d form.": "Please submit at most %(num)d forms.",
    "Please submit at least %(num)d form.": "Please submit at least %(num)d forms.",
    "%(size)d byte": "%(size)d bytes",
    "an hour ago": "%(count)s\xa0hours ago", "a minute ago": "%(count)s\xa0minutes ago",
    "%(num)d year": "%(num)d years", "%(num)d month": "%(num)d months", "%(num)d week": "%(num)d weeks",
    "%(num)d day": "%(num)d days", "%(num)d hour": "%(num)d hours", "%(num)d minute": "%(num)d minutes",
}

if __name__ == "__main__":
    po = polib.POFile()
    po.metadata = {
        "Project-Id-Version": "hamvaraq", "Language": "fa", "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8", "Content-Transfer-Encoding": "8bit",
        "Plural-Forms": "nplurals=2; plural=(n > 1);",
    }
    for msgid, tr in T.items():
        if isinstance(tr, tuple):
            po.append(polib.POEntry(msgid=msgid, msgid_plural=PLURAL_IDS[msgid], msgstr_plural={0: tr[0], 1: tr[1]}))
        else:
            po.append(polib.POEntry(msgid=msgid, msgstr=tr))
    OUT.mkdir(parents=True, exist_ok=True)
    po.save(str(OUT / "django.po"))
    po.save_as_mofile(str(OUT / "django.mo"))
    print(f"{len(po)} متن ترجمه شد ← {OUT}")
