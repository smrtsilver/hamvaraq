from django.db import migrations

OLD = {
    "tagline": "بخوان، بسپار، دوباره بخوان",
    "hero_title": "کتاب‌ها برای خوانده‌شدن‌اند، نه ماندن روی قفسه",
    "hero_subtitle": "هم‌ورق جاییه که کتاب‌خوان‌ها کتاب‌هاشون رو رایگان دست‌به‌دست می‌کنن. کتابی که خوندی رو بسپار، کتاب بعدیت رو بگیر؛ بدون پول، فقط با امتیاز.",
    "cta_text": "ثبت‌نام رایگانه و ۱ امتیاز هدیه داره؛ همین الان اولین کتابت رو بگیر.",
    "footer_text": "هم‌ورق؛ مبادله‌ی رایگان کتاب بین کتاب‌خوان‌ها."
}
NEW = {
    "tagline": "هر کتاب، یه سفر تازه",
    "hero_title": "کتابی که خوندی، منتظر خواننده‌ی بعدیشه",
    "hero_subtitle": "هم‌ورق خونه‌ی کتاب‌خوان‌هاست: کتابی که تموم کردی رو بسپار، کتاب بعدیت رو از قفسه‌ی یه هم‌شهری بردار و ردّ سفرش رو از شهری به شهری دنبال کن.",
    "cta_text": "با ثبت‌نام اولین امتیاز رو هدیه می‌گیری؛ شاید کتاب بعدیت همین الان تو قفسه‌ی یه هم‌شهری منتظرت باشه.",
    "footer_text": "هم‌ورق؛ جایی که کتاب‌ها از دستی به دستی سفر می‌کنن."
}


def forward(apps, schema_editor):
    """شعارهای پیش‌فرض قدیمی (با واژه‌های مالی) رو فقط اگه مدیر دست نزده، با نسخه‌ی تازه عوض می‌کنه."""
    SiteSetting = apps.get_model("common", "SiteSetting")
    for s in SiteSetting.objects.all():
        changed = [k for k in OLD if getattr(s, k) == OLD[k]]
        for k in changed:
            setattr(s, k, NEW[k])
        if changed:
            s.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("common", "0007_panel_support")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
