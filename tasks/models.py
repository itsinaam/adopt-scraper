from django.conf import settings
from django.db import models


class Task(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tasks",
        help_text="User who initiated the scraping task",
    )
    task_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Custom name or label for the scraping task",
    )
    account_email = models.EmailField(
        help_text="Target Adapt.io account email",
    )
    filters = models.JSONField(
        default=dict,
        help_text="Search filters applied on Adapt.io",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )

    current_step = models.CharField(
        max_length=100,
        blank=True,
    )

    progress = models.PositiveSmallIntegerField(
        default=0,
    )

    message = models.TextField(
        blank=True,
    )

    total_scraped_leads = models.PositiveIntegerField(
        default=0,
        help_text="Total raw prospect leads scraped from Adapt.io",
    )

    total_candidates_generated = models.PositiveIntegerField(
        default=0,
        help_text="Total email permutation candidate pairs generated",
    )

    total_verified_emails = models.PositiveIntegerField(
        default=0,
        help_text="Total deliverable verified emails confirmed by MailTester",
    )

    verified_leads = models.JSONField(
        default=list,
        blank=True,
        help_text="Structured list of verified lead contacts with valid emails",
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    result_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Local file path or Supabase Storage key",
    )

    result_url = models.URLField(
        max_length=1000,
        blank=True,
        help_text="Supabase storage direct / signed download URL",
    )

    error = models.TextField(
        blank=True,
    )

    logs = models.JSONField(
        default=list,
        blank=True,
        help_text="Chronological event logs with timestamps",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def add_log(self, message: str, step: str | None = None) -> None:
        """Appends a new timestamped log entry to the task logs array."""
        from django.utils import timezone
        entry = {
            "timestamp": timezone.now().isoformat(),
            "message": message,
            "step": step or self.current_step,
        }
        if not isinstance(self.logs, list):
            self.logs = []
        self.logs.append(entry)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Scraping Task"
        verbose_name_plural = "Scraping Tasks"

    def __str__(self):
        label = self.task_name or self.account_email
        return f"Task {self.pk} [{label}] - {self.status}"