from django.contrib import admin
from .models import Scan


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = [
        "id", "user", "child_name", "child_age",
        "status", "result_class", "confidence", "created_at",
    ]
    list_filter = ["status", "result_class", "created_at"]
    search_fields = ["user__username", "child_name"]
    readonly_fields = ["created_at", "raw_response"]
    ordering = ["-created_at"]
