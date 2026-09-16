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


class CSVProcessTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="csv_tasks",
        help_text="User who uploaded the CSV file",
    )
    task_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Custom name or label for the CSV processing task",
    )
    file_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Original uploaded CSV filename",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    current_step = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Current processing step",
    )
    progress = models.PositiveSmallIntegerField(
        default=0,
        help_text="Progress percentage (0 - 100)",
    )
    message = models.TextField(
        blank=True,
        default="",
        help_text="Current status message",
    )
    total_rows = models.PositiveIntegerField(
        default=0,
        help_text="Total rows in the uploaded CSV",
    )

    valid_emails_count = models.PositiveIntegerField(
        default=0,
        help_text="Count of leads that had an existing valid business email",
    )
    personal_emails_removed_count = models.PositiveIntegerField(
        default=0,
        help_text="Count of personal/free emails removed",
    )
    missing_emails_count = models.PositiveIntegerField(
        default=0,
        help_text="Count of leads without a valid business email",
    )
    combinations_generated_count = models.PositiveIntegerField(
        default=0,
        help_text="Count of candidate combination rows generated",
    )
    duplicates_removed_count = models.PositiveIntegerField(
        default=0,
        help_text="Count of duplicate emails removed",
    )
    total_verified_emails = models.PositiveIntegerField(
        default=0,
        help_text="Count of verified deliverable emails after MailTester check",
    )
    uploaded_file_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Local path to uploaded CSV file",
    )
    verified_leads = models.JSONField(
        default=list,
        blank=True,
        help_text="Final list of verified prospect lead records",
    )


    result_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Local path or Supabase Storage key for the primary result CSV",
    )
    result_url = models.URLField(
        max_length=1000,
        blank=True,
        help_text="Download URL for primary result CSV",
    )
    combinations_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Local path or Supabase Storage key for combinations CSV",
    )
    combinations_url = models.URLField(
        max_length=1000,
        blank=True,
        help_text="Download URL for combinations CSV",
    )
    valid_leads_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Local path or Supabase Storage key for clean business leads CSV",
    )
    valid_leads_url = models.URLField(
        max_length=1000,
        blank=True,
        help_text="Download URL for clean business leads CSV",
    )

    preview_data = models.JSONField(
        default=list,
        blank=True,
        help_text="First few processed preview rows for UI rendering",
    )
    error = models.TextField(
        blank=True,
        help_text="Error message if processing failed",
    )
    logs = models.JSONField(
        default=list,
        blank=True,
        help_text="Chronological event logs",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def add_log(self, message: str) -> None:
        from django.utils import timezone
        entry = {
            "timestamp": timezone.now().isoformat(),
            "message": message,
        }
        if not isinstance(self.logs, list):
            self.logs = []
        self.logs.append(entry)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "CSV Process Task"
        verbose_name_plural = "CSV Process Tasks"

    def __str__(self):
        label = self.task_name or self.file_name or f"Task {self.pk}"
        return f"CSV Task {self.pk} [{label}] - {self.status}"