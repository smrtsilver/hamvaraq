from django.urls import path

from . import views

app_name = "challenges"

urlpatterns = [path("", views.challenge_list, name="list")]
