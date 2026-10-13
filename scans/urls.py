from django.urls import path
from . import views

urlpatterns = [
    path("new/", views.NewScanView.as_view(), name="new_scan"),
    path("history/", views.ScanHistoryView.as_view(), name="scan_history"),
    path("<int:pk>/", views.ScanDetailView.as_view(), name="scan_detail"),
    path("<int:pk>/delete/", views.ScanDeleteView.as_view(), name="scan_delete"),
]
