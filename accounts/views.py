from django.contrib.auth.models import User
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.views.generic import TemplateView
from django.shortcuts import redirect
from django.contrib import messages


class LandingView(View):
    """Landing page for unauthenticated users. Redirect logged-in users to dashboard."""

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return TemplateView.as_view(template_name="accounts/landing.html")(request)


class DemoLoginView(View):
    """Auto-login as the demo user (POST only, CSRF protected)."""

    def post(self, request):
        try:
            demo_user = User.objects.get(username="demo")
        except User.DoesNotExist:
            messages.error(
                request,
                "Demo foydalanuvchi topilmadi. Iltimos, 'python manage.py seed_demo' buyrug'ini ishga tushiring.",
            )
            return redirect("landing")

        login(request, demo_user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Xush kelibsiz, {demo_user.first_name}!")
        return redirect("dashboard")

    def get(self, request):
        return redirect("landing")


class LogoutView(View):
    """Log out and redirect to landing."""

    def post(self, request):
        logout(request)
        messages.info(request, "Tizimdan muvaffaqiyatli chiqdingiz.")
        return redirect("landing")

    def get(self, request):
        # Also allow GET logout for simplicity
        logout(request)
        return redirect("landing")


class ProfileView(LoginRequiredMixin, TemplateView):
    """User profile page."""

    template_name = "accounts/profile.html"
    login_url = "/"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from scans.models import Scan

        user = self.request.user
        ctx["total_scans"] = Scan.objects.filter(user=user).count()
        ctx["page_title"] = "Profil"
        return ctx
