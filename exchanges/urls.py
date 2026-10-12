from django.urls import path

from . import views

app_name = "exchanges"

urlpatterns = [
    path("", views.exchange_list, name="list"),
    path("request/<int:book_id>/", views.request_book, name="request"),
    path("<int:pk>/", views.exchange_detail, name="detail"),
    path("<int:pk>/accept/", views.accept, name="accept"),
    path("<int:pk>/reject/", views.reject, name="reject"),
    path("<int:pk>/cancel/", views.cancel, name="cancel"),
    path("<int:pk>/confirm/", views.confirm, name="confirm"),
    path("<int:pk>/meeting/", views.propose_meeting, name="meeting"),
    path("<int:pk>/meeting/agree/", views.agree_meeting, name="meeting_agree"),
    path("<int:pk>/message/", views.send_message, name="message"),
    path("<int:pk>/messages/", views.poll_messages, name="poll"),
    path("<int:pk>/note/", views.add_note, name="note"),
]
