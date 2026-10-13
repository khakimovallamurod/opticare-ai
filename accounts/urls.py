from django.urls import path
from . import views

urlpatterns = [
    path("", views.LandingView.as_view(), name="landing"),
    path("demo-login/", views.DemoLoginView.as_view(), name="demo_login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
]
