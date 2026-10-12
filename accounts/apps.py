from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"
    verbose_name = "حساب‌ها"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .ip import ip_key

        def remember_ip(sender, request, user, **kwargs):
            """آخرین شبکه‌ی ورود رو نگه می‌داره (برای تشخیص حساب‌های هم‌شبکه)."""
            key = ip_key(request) if request is not None else ""
            if key and key != user.last_ip_hash:
                type(user).objects.filter(pk=user.pk).update(last_ip_hash=key)
                user.last_ip_hash = key

        user_logged_in.connect(remember_ip, dispatch_uid="hv_remember_ip")
