from django.contrib import admin

from .models import City, MeetingPoint

admin.site.site_header = "مدیریت هم‌ورق"
admin.site.site_title = "مدیریت هم‌ورق"
admin.site.index_title = "مدیریت وب‌گاه"


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(MeetingPoint)
class MeetingPointAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "city", "is_active")
    list_filter = ("city", "kind", "is_active")
    search_fields = ("name", "address")
