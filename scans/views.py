"""
Scans app views.
"""

import logging
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.views.generic import TemplateView, DetailView
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.files.base import ContentFile
from django.http import JsonResponse

from .models import Scan
from .forms import NewScanForm
from .services.gemini import analyze_eye_image
from .services.image_utils import process_image

logger = logging.getLogger(__name__)


class NewScanView(LoginRequiredMixin, View):
    """Multi-step single-page new scan view."""

    template_name = "scans/new_scan.html"

    def get(self, request):
        form = NewScanForm()
        return self._render(request, form)

    def post(self, request):
        form = NewScanForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._render(request, form)

        image_file = form.cleaned_data["image"]
        child_name = form.cleaned_data.get("child_name", "")
        child_age = form.cleaned_data.get("child_age")
        notes = form.cleaned_data.get("notes", "")

        # Read raw bytes
        image_bytes = image_file.read()
        original_name = image_file.name or "scan.jpg"

        # Server-side image processing (resize, strip GPS EXIF, validate)
        try:
            processed_bytes, mime_type = process_image(image_bytes, original_name)
        except ValueError as exc:
            messages.error(request, str(exc))
            return self._render(request, form)

        # Create Scan record
        scan = Scan(
            user=request.user,
            child_name=child_name,
            child_age=child_age,
            notes=notes,
            status=Scan.STATUS_OK,
        )
        scan.image.save("scan.jpg", ContentFile(processed_bytes), save=False)
        scan.save()

        # Call Gemini
        try:
            result = analyze_eye_image(processed_bytes, mime_type, age=child_age)
        except Exception as exc:
            logger.exception("Gemini kutilmagan xato: %s", exc)
            result = {
                "valid": False,
                "error": True,
                "error_message": "AI tahlili amalga oshmadi. Qayta urinib ko'ring.",
            }

        if result.get("error"):
            scan.status = Scan.STATUS_ERROR
            scan.raw_response = result
            scan.save(update_fields=["status", "raw_response"])
            messages.error(request, result.get("error_message", "AI xizmatida xatolik."))
            return redirect("new_scan")

        if not result.get("valid", True):
            scan.status = Scan.STATUS_INVALID
            scan.invalid_reason = result.get("invalid_reason", "Rasm yaroqsiz.")
            scan.raw_response = result
            scan.save(update_fields=["status", "invalid_reason", "raw_response"])
            messages.warning(request, "Rasm tahlil uchun yaroqsiz. Sababi natija sahifasida ko'rsatilgan.")
            return redirect("scan_detail", pk=scan.pk)

        # Save analysis results
        scan.status = Scan.STATUS_OK
        scan.result_class = result.get("class", Scan.CLASS_ATTENTION)
        scan.confidence = result.get("confidence", 0.0)
        scan.summary = result.get("summary", "")
        scan.observations = result.get("observations", [])
        scan.recommendations = result.get("recommendations", [])
        scan.raw_response = result
        scan.save(
            update_fields=[
                "status", "result_class", "confidence", "summary",
                "observations", "recommendations", "raw_response",
            ]
        )

        messages.success(request, "Tahlil muvaffaqiyatli bajarildi!")
        return redirect("scan_detail", pk=scan.pk)

    def _render(self, request, form):
        from django.shortcuts import render
        return render(request, self.template_name, {
            "form": form,
            "page_title": "Yangi tekshiruv",
        })


class ScanDetailView(LoginRequiredMixin, View):
    """Result page for a single scan."""

    template_name = "scans/scan_detail.html"

    def get(self, request, pk):
        from django.shortcuts import render
        scan = get_object_or_404(Scan, pk=pk, user=request.user)
        return render(request, self.template_name, {
            "scan": scan,
            "page_title": "Tekshiruv natijasi",
        })


class ScanHistoryView(LoginRequiredMixin, View):
    """Paginated scan history with class filter."""

    template_name = "scans/history.html"

    def get(self, request):
        from django.shortcuts import render
        qs = Scan.objects.filter(user=request.user, status=Scan.STATUS_OK)

        class_filter = request.GET.get("class", "")
        if class_filter in (Scan.CLASS_NORMAL, Scan.CLASS_ATTENTION, Scan.CLASS_CONSULT):
            qs = qs.filter(result_class=class_filter)

        paginator = Paginator(qs, 10)
        page_number = request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)

        return render(request, self.template_name, {
            "page_obj": page_obj,
            "class_filter": class_filter,
            "page_title": "Tekshiruv tarixi",
        })


class ScanDeleteView(LoginRequiredMixin, View):
    """Delete a scan record and its image file."""


    def post(self, request, pk):
        scan = get_object_or_404(Scan, pk=pk, user=request.user)
        scan.delete()
        messages.success(request, "Tekshiruv o'chirildi.")
        return redirect("scan_history")
