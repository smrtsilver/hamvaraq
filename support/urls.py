from django.urls import path

from . import views

app_name = "support"
urlpatterns = [
    path("", views.ticket_new, name="new"),
    path("mine/", views.my_tickets, name="mine"),
    path("<int:pk>/", views.ticket_detail, name="detail"),
]
