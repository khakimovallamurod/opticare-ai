"""
Selector functions for statistics and dashboard queries.
"""

from django.db.models import Count, Avg
from django.utils import timezone
from datetime import timedelta


def get_user_stats(user):
    """Return aggregated statistics dict for a user's scans."""
    from scans.models import Scan

    qs = Scan.objects.filter(user=user, status=Scan.STATUS_OK)
    total = qs.count()
    consult_count = qs.filter(result_class=Scan.CLASS_CONSULT).count()
    avg_confidence = qs.aggregate(avg=Avg("confidence"))["avg"] or 0.0

    # This month
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month = qs.filter(created_at__gte=month_start).count()

    # Latest scan
    latest = qs.first()

    # Class distribution
    class_counts = {
        Scan.CLASS_NORMAL: qs.filter(result_class=Scan.CLASS_NORMAL).count(),
        Scan.CLASS_ATTENTION: qs.filter(result_class=Scan.CLASS_ATTENTION).count(),
        Scan.CLASS_CONSULT: qs.filter(result_class=Scan.CLASS_CONSULT).count(),
    }

    # Monthly scans for last 6 months
    monthly = []
    for i in range(5, -1, -1):
        month_dt = now - timedelta(days=i * 30)
        label = month_dt.strftime("%b %Y")
        start = month_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if i > 0:
            next_month = start + timedelta(days=32)
            end = next_month.replace(day=1)
        else:
            end = now
        count = qs.filter(created_at__gte=start, created_at__lt=end).count()
        monthly.append({"label": label, "count": count})

    return {
        "total": total,
        "consult_count": consult_count,
        "avg_confidence": round(avg_confidence * 100, 1),
        "this_month": this_month,
        "latest": latest,
        "class_counts": class_counts,
        "monthly": monthly,
    }
