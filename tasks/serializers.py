from rest_framework import serializers

from .constants import EMPLOYEE_COUNT_OPTIONS, FILTER_FIELDS
from .models import Task


class TaskFiltersSerializer(serializers.Serializer):
    """
    Structured search filters applied during Adapt.io lead search.
    """
    job_titles = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of job titles (e.g. ['CEO', 'CTO', 'Founder'])",
    )
    industries = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of target industries (e.g. ['Software', 'Information Technology'])",
    )
    locations = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of target locations (e.g. ['United States', 'California', 'Lahore'])",
    )
    employee_counts = serializers.ListField(
        child=serializers.ChoiceField(choices=EMPLOYEE_COUNT_OPTIONS),
        required=False,
        help_text="Company size ranges: '0 - 25', '25 - 100', '100 - 250', '250 - 1000', '1K - 10K', '10K - 50K', '50K - 100K', '> 100K'",
    )


class LeadContactSerializer(serializers.Serializer):
    """
    Schema for a verified lead contact with confirmed email address.
    """
    first_name = serializers.CharField(allow_blank=True, help_text="First name of lead")
    last_name = serializers.CharField(allow_blank=True, help_text="Last name of lead")
    job_title = serializers.CharField(allow_blank=True, help_text="Job title of lead")
    company_name = serializers.CharField(allow_blank=True, help_text="Company name")
    company_domain = serializers.CharField(allow_blank=True, help_text="Domain name of company")
    employee_count = serializers.CharField(allow_blank=True, help_text="Company employee count range")
    location = serializers.CharField(allow_blank=True, help_text="Location / city / country")
    linkedin_profile_url = serializers.CharField(allow_blank=True, help_text="LinkedIn profile URL")
    email = serializers.EmailField(help_text="Verified deliverable email address")


class TaskSerializer(serializers.ModelSerializer):
    """
    Serializer for Task instances, handling execution creation, progress tracking, and lead results.
    """
    account_email = serializers.EmailField(
        required=False,
        help_text="Adapt.io account email for running the task.",
    )
    email = serializers.EmailField(
        write_only=True,
        required=False,
        help_text="Alias for account_email.",
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        help_text="Adapt.io account password (optional if ADAPT_PASSWORD is in .env).",
    )
    download_url = serializers.SerializerMethodField(
        help_text="Direct or signed download URL for the generated CSV result file."
    )

    class Meta:
        model = Task
        fields = [
            "id",
            "account_email",
            "email",
            "password",
            "filters",
            "status",
            "current_step",
            "progress",
            "message",
            "total_scraped_leads",
            "total_candidates_generated",
            "total_verified_emails",
            "verified_leads",
            "started_at",
            "completed_at",
            "result_path",
            "result_url",
            "download_url",
            "error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "current_step",
            "progress",
            "message",
            "total_scraped_leads",
            "total_candidates_generated",
            "total_verified_emails",
            "verified_leads",
            "started_at",
            "completed_at",
            "result_path",
            "result_url",
            "download_url",
            "error",
            "created_at",
            "updated_at",
        ]

    def to_internal_value(self, data):
        if isinstance(data, dict) and "filters" not in data:
            filters = {}
            for k in FILTER_FIELDS:
                if k in data:
                    filters[k] = data[k]
            if filters:
                data = {**data, "filters": filters}
        return super().to_internal_value(data)

    def get_download_url(self, obj: Task) -> str:
        if obj.status != Task.Status.COMPLETED:
            return ""
        if obj.result_url:
            return obj.result_url
        return f"/api/tasks/{obj.pk}/download/"

    def validate(self, attrs):
        import os
        email = (
            attrs.get("email")
            or attrs.get("account_email")
            or os.getenv("ADAPT_EMAIL", "").strip()
        )
        if not email:
            raise serializers.ValidationError(
                {"account_email": "An email for the target Adapt.io account is required (in payload or via ADAPT_EMAIL in .env)."}
            )

        password = (
            attrs.get("password")
            or os.getenv("ADAPT_PASSWORD", "").strip()
        )
        if not password:
            raise serializers.ValidationError(
                {"password": "An Adapt.io password is required (in payload or via ADAPT_PASSWORD in .env)."}
            )

        attrs["account_email"] = email
        attrs["password"] = password
        attrs.pop("email", None)
        return attrs

    def validate_filters(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Filters must be an object."
            )

        unknown_fields = set(value) - set(FILTER_FIELDS)
        if unknown_fields:
            raise serializers.ValidationError(
                f"Unknown filter fields: {', '.join(sorted(unknown_fields))}"
            )

        for field in FILTER_FIELDS:
            if field in value:
                if not isinstance(value[field], list):
                    raise serializers.ValidationError(
                        f"'{field}' must be a list."
                    )

                if not all(isinstance(item, str) for item in value[field]):
                    raise serializers.ValidationError(
                        f"All values in '{field}' must be strings."
                    )

        return value


class StartTaskRequestSerializer(serializers.Serializer):
    """
    Request payload schema for starting a new scraping task.
    """
    email = serializers.EmailField(
        required=False,
        help_text="Adapt.io account email (optional if ADAPT_EMAIL is configured in .env)",
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        help_text="Adapt.io account password (optional if ADAPT_PASSWORD is configured in .env)",
    )
    filters = TaskFiltersSerializer(
        required=False,
        default=dict,
        help_text="Search filters for scraping leads",
    )


class TaskResultsResponseSerializer(serializers.Serializer):
    """
    Structured results response designed for Frontend UI dashboards.
    """
    task_id = serializers.IntegerField()
    status = serializers.CharField()
    account_email = serializers.EmailField()
    filters = serializers.DictField()
    total_scraped_leads = serializers.IntegerField(help_text="Total raw leads scraped from Adapt.io")
    total_candidates_generated = serializers.IntegerField(help_text="Total permutation candidate pairs created")
    total_verified_emails = serializers.IntegerField(help_text="Total verified valid emails found")
    download_url = serializers.CharField(allow_blank=True, help_text="CSV file download link")
    completed_at = serializers.DateTimeField(allow_null=True)
    verified_leads = LeadContactSerializer(many=True, help_text="List of all verified leads")