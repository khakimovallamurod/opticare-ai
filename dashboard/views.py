"""
Dashboard views.
"""

import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from scans.models import Scan
from scans.selectors import get_user_stats


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard page."""

    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        stats = get_user_stats(user)

        # Recent 5 scans
        recent_scans = Scan.objects.filter(user=user, status=Scan.STATUS_OK).order_by("-created_at")[:5]

        ctx.update({
            "stats": stats,
            "recent_scans": recent_scans,
            "page_title": "Bosh sahifa",
            "chart_class_labels": json.dumps(["Yaxshi holat", "Kuzatuv", "Murojaat"]),
            "chart_class_data": json.dumps([
                stats["class_counts"][Scan.CLASS_NORMAL],
                stats["class_counts"][Scan.CLASS_ATTENTION],
                stats["class_counts"][Scan.CLASS_CONSULT],
            ]),
            "chart_monthly_labels": json.dumps([m["label"] for m in stats["monthly"]]),
            "chart_monthly_data": json.dumps([m["count"] for m in stats["monthly"]]),
        })
        return ctx


class StatisticsView(LoginRequiredMixin, TemplateView):
    """Detailed statistics page."""

    template_name = "dashboard/statistics.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        stats = get_user_stats(user)

        total = stats["total"] or 1  # avoid division by zero
        class_counts = stats["class_counts"]

        ctx.update({
            "stats": stats,
            "page_title": "Statistika",
            "normal_pct": round(class_counts[Scan.CLASS_NORMAL] / total * 100, 1),
            "attention_pct": round(class_counts[Scan.CLASS_ATTENTION] / total * 100, 1),
            "consult_pct": round(class_counts[Scan.CLASS_CONSULT] / total * 100, 1),
            "chart_class_labels": json.dumps(["Yaxshi holat", "Kuzatuv", "Murojaat"]),
            "chart_class_data": json.dumps([
                class_counts[Scan.CLASS_NORMAL],
                class_counts[Scan.CLASS_ATTENTION],
                class_counts[Scan.CLASS_CONSULT],
            ]),
            "chart_monthly_labels": json.dumps([m["label"] for m in stats["monthly"]]),
            "chart_monthly_data": json.dumps([m["count"] for m in stats["monthly"]]),
        })
        return ctx
