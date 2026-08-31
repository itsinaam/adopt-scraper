from django.db import models


class Task(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

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

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Scraping Task"
        verbose_name_plural = "Scraping Tasks"

    def __str__(self):
        return f"Task {self.pk} [{self.account_email}] - {self.status}"