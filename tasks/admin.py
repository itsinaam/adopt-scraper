from django.contrib import admin
from .models import CSVProcessTask, Task


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


@admin.register(CSVProcessTask)
class CSVProcessTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "file_name",
        "task_name",
        "status",
        "total_rows",
        "valid_emails_count",
        "personal_emails_removed_count",
        "missing_emails_count",
        "combinations_generated_count",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("file_name", "task_name", "error")
    readonly_fields = ("created_at", "updated_at")