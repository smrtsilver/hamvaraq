from django.contrib import admin

from .models import City, MeetingPoint, Province, SiteSetting

def _persian_boolean_icons():
    """آیکون بله/خیر ادمین alt انگلیسی (True/False) داره؛ فارسی‌اش می‌کنیم."""
    from django.contrib.admin.templatetags import admin_list

    original = admin_list._boolean_icon

    def patched(field_val):
        html = str(original(field_val))
        for old, new in (('alt="True"', 'alt="بله"'), ('alt="False"', 'alt="خیر"'), ('alt="None"', 'alt="نامشخص"')):
            html = html.replace(old, new)
        from django.utils.safestring import mark_safe
        return mark_safe(html)

    admin_list._boolean_icon = patched


_persian_boolean_icons()

admin.site.site_header = "مدیریت هم‌ورق"
admin.site.site_title = "مدیریت هم‌ورق"
admin.site.index_title = "مدیریت وب‌گاه"


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "province")
    list_filter = ("province",)
    search_fields = ["name", "province__name"]


@admin.register(MeetingPoint)
class MeetingPointAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "city", "is_active")
    list_filter = ("city", "kind", "is_active")
    search_fields = ("name", "address")


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


from .models import AuditLog  # noqa: E402


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target", "note")
    list_filter = ("action",)
    search_fields = ("target", "note", "actor__username")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
