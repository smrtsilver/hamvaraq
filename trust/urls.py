from django.urls import path

from . import views

app_name = "trust"

urlpatterns = [
    path("vote/<int:exchange_id>/", views.vote, name="vote"),
    path("report/<str:kind>/<int:pk>/", views.report, name="report"),
]
