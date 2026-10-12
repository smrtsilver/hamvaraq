from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.utils.decorators import method_decorator

from common.throttle import throttle

from . import views


class ThrottledLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"

    @method_decorator(throttle("login", 20, 600, by="ip"))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class ThrottledPasswordResetView(auth_views.PasswordResetView):
    @method_decorator(throttle("pwreset", 5, 3600, by="ip"))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", ThrottledLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("settings/", views.settings_view, name="settings"),
    path("u/<str:username>/", views.profile, name="profile"),
    # بازیابی رمز با ایمیل (اختیاری)
    path("password-reset/", ThrottledPasswordResetView.as_view(
        template_name="accounts/password_reset.html",
        email_template_name="accounts/password_reset_email.txt",
        success_url=reverse_lazy("accounts:password_reset_done"),
    ), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="accounts/password_reset_confirm.html",
        success_url=reverse_lazy("accounts:password_reset_complete"),
    ), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),
]
