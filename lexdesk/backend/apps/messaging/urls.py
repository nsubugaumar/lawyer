from django.urls import path

from . import views

urlpatterns = [
    path("", views.MessagesView.as_view(), name="messages"),
    path("threads/", views.ThreadsView.as_view(), name="message-threads"),
    path("read/", views.MarkReadView.as_view(), name="message-read"),
]
