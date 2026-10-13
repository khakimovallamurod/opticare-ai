from django.urls import path
from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("statistics/", views.StatisticsView.as_view(), name="statistics"),
]
