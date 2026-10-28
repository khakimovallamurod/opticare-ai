from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
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


class LoginView(auth_views.LoginView):
    """Username/password login page."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.get_user()
        messages.success(self.request, f"Xush kelibsiz, {user.first_name or user.username}!")
        return response


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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from scans.models import Scan

        user = self.request.user
        ctx["total_scans"] = Scan.objects.filter(user=user).count()
        ctx["page_title"] = "Profil"
        return ctx
