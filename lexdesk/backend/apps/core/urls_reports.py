from django.urls import path

from .reports import ReportsView

urlpatterns = [path("", ReportsView.as_view(), name="reports")]
