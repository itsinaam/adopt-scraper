from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .constants import EMPLOYEE_COUNT_OPTIONS, FILTER_FIELDS
from .models import CSVProcessTask, Task



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
    locations = serializers.JSONField(
        required=False,
        help_text="Target locations: list of countries ['United States'], or object {'country': ['Canada'], 'city': ['Kitchener-Waterloo (ON)']}",
    )
    cities = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of target cities (e.g. ['Kitchener-Waterloo (ON)', 'Halifax (NS)'])",
    )
    countries = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of target countries (e.g. ['United States', 'Canada'])",
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
    industry = serializers.CharField(required=False, allow_blank=True, default="", help_text="Industry of company/lead")
    linkedin_profile_url = serializers.CharField(allow_blank=True, help_text="LinkedIn profile URL")
    email = serializers.EmailField(help_text="Verified deliverable email address")


class TaskSerializer(serializers.ModelSerializer):
    """
    Serializer for Task instances, handling execution creation, progress tracking, and lead results.
    """
    task_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
        help_text="Custom name or label for the scraping task.",
    )
    user = serializers.ReadOnlyField(
        source="user.username",
        default=None,
        help_text="Username of task owner.",
    )
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
            "task_name",
            "user",
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
            "logs",
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
            "logs",
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
            if field not in value:
                continue

            if field == "locations":
                locs = value["locations"]
                if isinstance(locs, list):
                    for item in locs:
                        if isinstance(item, dict):
                            for sub_k, sub_v in item.items():
                                if not isinstance(sub_v, list) or not all(isinstance(x, str) for x in sub_v):
                                    raise serializers.ValidationError(
                                        f"In 'locations', '{sub_k}' must be a list of strings."
                                    )
                        elif not isinstance(item, str):
                            raise serializers.ValidationError(
                                "Items in 'locations' must be strings (countries) or objects (e.g. {'city': ['...']})."
                            )
                elif isinstance(locs, dict):
                    for sub_k, sub_v in locs.items():
                        if isinstance(sub_v, list):
                            if not all(isinstance(x, str) for x in sub_v):
                                raise serializers.ValidationError(
                                    f"In 'locations', all items in '{sub_k}' must be strings."
                                )
                        elif not isinstance(sub_v, str):
                            raise serializers.ValidationError(
                                f"In 'locations', '{sub_k}' must be a list of strings or a string."
                            )
                else:
                    raise serializers.ValidationError(
                        "'locations' must be a list (e.g. ['Canada']) or an object (e.g. {'city': ['Halifax (NS)'], 'country': ['Canada']})."
                    )
            else:
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
    task_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
        help_text="Custom name or label for the scraping task",
    )
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


class TaskLogItemSerializer(serializers.Serializer):
    timestamp = serializers.CharField(help_text="ISO 8601 timestamp of log entry")
    message = serializers.CharField(help_text="Detailed log message")
    step = serializers.CharField(required=False, allow_blank=True, help_text="Execution step name")


class TaskLogsResponseSerializer(serializers.Serializer):
    task_id = serializers.IntegerField(help_text="Task ID")
    status = serializers.CharField(help_text="Current task status")
    current_step = serializers.CharField(help_text="Current execution step")
    progress = serializers.IntegerField(help_text="Progress percentage 0-100")
    message = serializers.CharField(help_text="Latest task status message")
    logs = TaskLogItemSerializer(many=True, help_text="Chronological list of task log events")


class TaskResultsResponseSerializer(serializers.Serializer):
    """
    Structured results response designed for Frontend UI dashboards.
    """
    task_id = serializers.IntegerField()
    task_name = serializers.CharField(required=False, default="", allow_blank=True)
    status = serializers.CharField()
    account_email = serializers.EmailField()
    filters = serializers.DictField()
    total_scraped_leads = serializers.IntegerField(help_text="Total raw leads scraped from Adapt.io")
    total_candidates_generated = serializers.IntegerField(help_text="Total permutation candidate pairs created")
    total_verified_emails = serializers.IntegerField(help_text="Total verified valid emails found")
    download_url = serializers.CharField(allow_blank=True, help_text="CSV file download link")
    completed_at = serializers.DateTimeField(allow_null=True)
    logs = TaskLogItemSerializer(many=True, default=list, help_text="Chronological task log events")
    verified_leads = LeadContactSerializer(many=True, help_text="List of all verified leads")


class CompletedTaskSerializer(serializers.ModelSerializer):
    """
    Lightweight listing serializer for completed scraping tasks.
    Returns only essential metadata and file download URL without heavy lead arrays.
    """
    task_id = serializers.IntegerField(source="id", read_only=True)
    task_name = serializers.CharField(read_only=True)
    user = serializers.ReadOnlyField(source="user.username", default=None)
    filters = serializers.SerializerMethodField(help_text="Search filters applied for scraping")
    total_leads_scraped = serializers.IntegerField(source="total_scraped_leads", read_only=True)
    total_combinations = serializers.IntegerField(source="total_candidates_generated", read_only=True)
    total_verified_emails = serializers.IntegerField(read_only=True)
    task_started_at = serializers.DateTimeField(source="started_at", read_only=True)
    task_completed_at = serializers.DateTimeField(source="completed_at", read_only=True)
    url_of_file = serializers.SerializerMethodField(help_text="Direct or signed download URL for the CSV file")

    class Meta:
        model = Task
        fields = [
            "task_id",
            "task_name",
            "user",
            "filters",
            "total_leads_scraped",
            "total_combinations",
            "total_verified_emails",
            "task_started_at",
            "task_completed_at",
            "url_of_file",
        ]

    @extend_schema_field(serializers.DictField)
    def get_filters(self, obj: Task):
        import json
        if isinstance(obj.filters, dict):
            return obj.filters
        if isinstance(obj.filters, str):
            try:
                return json.loads(obj.filters)
            except Exception:
                return obj.filters
        return {}

    @extend_schema_field(serializers.CharField)
    def get_url_of_file(self, obj: Task) -> str:
        from .storage import supabase_storage
        if obj.result_path and obj.result_path.startswith("tasks/"):
            try:
                signed = supabase_storage.create_signed_url(obj.result_path, expires_in=7 * 24 * 3600)
                if signed:
                    return signed
            except Exception:
                pass

        if obj.result_url:
            return obj.result_url

        request = self.context.get("request")
        path = f"/api/tasks/{obj.pk}/download/"
        if request:
            return request.build_absolute_uri(path)
        return path


class CSVProcessTaskUploadSerializer(serializers.Serializer):
    file = serializers.FileField(
        help_text="Uploaded CSV file containing prospect leads to clean and process",
    )
    task_name = serializers.CharField(
        required=False,
        default="",
        allow_blank=True,
        help_text="Optional custom label or name for this CSV processing task",
    )

    def validate_file(self, value):
        if not value.name.lower().endswith(".csv"):
            raise serializers.ValidationError("Only .csv files are supported.")
        if value.size > 25 * 1024 * 1024:
            raise serializers.ValidationError("File size must not exceed 25MB.")
        return value


class CSVProcessTaskSerializer(serializers.ModelSerializer):
    task_id = serializers.IntegerField(source="id", read_only=True)
    user = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = CSVProcessTask
        fields = [
            "task_id",
            "task_name",
            "file_name",
            "user",
            "status",
            "total_rows",
            "valid_emails_count",
            "personal_emails_removed_count",
            "missing_emails_count",
            "combinations_generated_count",
            "duplicates_removed_count",
            "download_url",
            "started_at",
            "completed_at",

        ]

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_user(self, obj: CSVProcessTask):
        if obj.user:
            return {
                "id": obj.user.pk,
                "username": obj.user.username,
                "email": obj.user.email,
            }
        return None

    @extend_schema_field(serializers.CharField)
    def get_download_url(self, obj: CSVProcessTask) -> str:
        request = self.context.get("request")
        url = obj.result_url or f"/api/tasks/csv-tasks/{obj.pk}/download/"
        if request and url.startswith("/"):
            return request.build_absolute_uri(url)
        return url