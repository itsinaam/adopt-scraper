from django.contrib import admin
from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "account_email",
        "status",
        "current_step",
        "progress",
        "started_at",
        "completed_at",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("account_email", "message", "error")
    readonly_fields = ("created_at", "updated_at")