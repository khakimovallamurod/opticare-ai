"""
Scan model for OptiCare.
"""

import os
from django.db import models
from django.contrib.auth.models import User


def scan_upload_path(instance, filename):
    """Upload images under media/scans/<user_id>/<YYYY-MM>/<filename>."""
    from django.utils import timezone
    now = timezone.now()
    return f"scans/{instance.user_id}/{now.strftime('%Y-%m')}/{filename}"


class Scan(models.Model):
    """Represents a single eye screening record."""

    STATUS_OK = "ok"
    STATUS_INVALID = "invalid"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_OK, "Muvaffaqiyatli"),
        (STATUS_INVALID, "Noto'g'ri rasm"),
        (STATUS_ERROR, "Xatolik"),
    ]

    CLASS_NORMAL = "normal"
    CLASS_ATTENTION = "attention"
    CLASS_CONSULT = "consult"
    CLASS_CHOICES = [
        (CLASS_NORMAL, "Yaxshi holat"),
        (CLASS_ATTENTION, "Kuzatuv talab etadi"),
        (CLASS_CONSULT, "Shifokorga murojaat qiling"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="scans")
    image = models.ImageField(upload_to=scan_upload_path)
    child_name = models.CharField(max_length=120, blank=True)
    child_age = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OK)
    result_class = models.CharField(
        max_length=10, choices=CLASS_CHOICES, null=True, blank=True
    )
    confidence = models.FloatField(null=True, blank=True)
    summary = models.TextField(blank=True)
    observations = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    raw_response = models.JSONField(default=dict)
    invalid_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]
        verbose_name = "Tekshiruv"
        verbose_name_plural = "Tekshiruvlar"

    def __str__(self):
        return f"Scan #{self.pk} – {self.get_result_class_display()} ({self.created_at:%Y-%m-%d})"

    def delete(self, *args, **kwargs):
        """Delete image file from disk when record is removed."""
        if self.image:
            try:
                path = self.image.path
                super().delete(*args, **kwargs)
                if os.path.exists(path):
                    os.remove(path)
                return
            except Exception:
                pass
        super().delete(*args, **kwargs)

    @property
    def class_color(self):
        """Return Tailwind color name for the result class."""
        return {
            self.CLASS_NORMAL: "emerald",
            self.CLASS_ATTENTION: "amber",
            self.CLASS_CONSULT: "rose",
        }.get(self.result_class, "slate")

    @property
    def class_label_uz(self):
        return {
            self.CLASS_NORMAL: "Yaxshi holat",
            self.CLASS_ATTENTION: "Kuzatuv talab etadi",
            self.CLASS_CONSULT: "Shifokorga murojaat qiling",
        }.get(self.result_class, "Noma'lum")

    URGENCY_META = {
        "past": {"level": 1, "label": "Past", "color": "emerald",
                 "doctor_visit": "Rejali profilaktik ko'rik — yiliga 1 marta"},
        "orta": {"level": 2, "label": "O'rta", "color": "amber",
                 "doctor_visit": "Holatni 3–7 kun kuzating; yaxshilanmasa 1–2 hafta ichida oftalmologga boring"},
        "yuqori": {"level": 3, "label": "Yuqori", "color": "orange",
                   "doctor_visit": "2–3 kun ichida bolalar oftalmologiga uchrashing"},
        "shoshilinch": {"level": 4, "label": "Shoshilinch", "color": "rose",
                        "doctor_visit": "Bugunoq (24 soat ichida) shifokorga murojaat qiling"},
    }
    CLASS_DEFAULT_URGENCY = {CLASS_NORMAL: "past", CLASS_ATTENTION: "orta", CLASS_CONSULT: "yuqori"}
    PRIORITY_LABELS = {"muhim": "Muhim", "tavsiya": "Tavsiya etiladi", "qoshimcha": "Qo'shimcha"}

    @property
    def urgency(self):
        """Recommendation level info: key, level (1-4), label, color, doctor_visit, reason."""
        raw = self.raw_response if isinstance(self.raw_response, dict) else {}
        key = raw.get("urgency")
        if key not in self.URGENCY_META:
            key = self.CLASS_DEFAULT_URGENCY.get(self.result_class)
        if key is None:
            return None
        meta = self.URGENCY_META[key]
        return {
            "key": key,
            **meta,
            "doctor_visit": raw.get("doctor_visit") or meta["doctor_visit"],
            "reason": raw.get("urgency_reason", ""),
            "steps": range(1, 5),
        }

    @property
    def recommendation_items(self):
        """Recommendations as [{text, priority, priority_label}]; legacy plain strings supported."""
        items = []
        for rec in self.recommendations or []:
            if isinstance(rec, dict):
                text, priority = rec.get("text", ""), rec.get("priority", "tavsiya")
            else:
                text, priority = str(rec), None
            if text:
                items.append({
                    "text": text,
                    "priority": priority,
                    "priority_label": self.PRIORITY_LABELS.get(priority, ""),
                })
        return items

    @property
    def confidence_percent(self):
        """Return confidence as percentage (0-100), safely handling both 0-1 and 0-100 values."""
        if self.confidence is None:
            return None
        if self.confidence <= 1.0:
            return round(self.confidence * 100)
        return round(self.confidence)
