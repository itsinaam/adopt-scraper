from django.test import TestCase
from rest_framework.test import APITestCase

from .models import Task
from .serializers import TaskSerializer


class TaskSerializerTests(TestCase):
    def test_password_is_write_only_and_filters_use_plural_keys(self):
        task = Task.objects.create(
            account_email="demo@example.com",
            filters={"job_titles": ["CTO"]},
            status=Task.Status.RUNNING,
        )
        serializer = TaskSerializer(instance=task)

        self.assertNotIn("password", serializer.data)
        self.assertEqual(serializer.data["account_email"], "demo@example.com")

        valid = TaskSerializer(
            data={
                "email": "demo@example.com",
                "password": "secret",
                "filters": {"job_titles": ["CTO"]},
            }
        )
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.validated_data["account_email"], "demo@example.com")

    def test_unknown_or_singular_filter_keys_are_rejected(self):
        serializer = TaskSerializer(
            data={
                "email": "demo@example.com",
                "password": "secret",
                "filters": {"job_title": ["CTO"]},
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("filters", serializer.errors)

    def test_only_filters_uses_env_credentials(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"ADAPT_EMAIL": "env_user@example.com", "ADAPT_PASSWORD": "env_password"}):
            serializer = TaskSerializer(
                data={
                    "filters": {"job_titles": ["CEO", "Founder"]},
                }
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertEqual(serializer.validated_data["account_email"], "env_user@example.com")
            self.assertEqual(serializer.validated_data["password"], "env_password")
            self.assertEqual(serializer.validated_data["filters"]["job_titles"], ["CEO", "Founder"])

    def test_flat_filters_automatically_nested(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"ADAPT_EMAIL": "env_user@example.com", "ADAPT_PASSWORD": "env_password"}):
            serializer = TaskSerializer(
                data={
                    "job_titles": ["CEO"],
                    "locations": ["United States"],
                }
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertEqual(serializer.validated_data["filters"]["job_titles"], ["CEO"])
            self.assertEqual(serializer.validated_data["filters"]["locations"], ["United States"])


class TaskAPITests(APITestCase):
    def test_health_check(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("status"), "ok")

    def test_current_task_empty(self):
        response = self.client.get("/api/tasks/current/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data.get("task"))

    def test_current_task_returns_latest(self):
        task = Task.objects.create(
            account_email="current@example.com",
            status=Task.Status.RUNNING,
            progress=25,
            message="Running step...",
        )
        response = self.client.get("/api/tasks/current/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data.get("task"))
        self.assertEqual(response.data["task"]["account_email"], "current@example.com")

    def test_running_task_cannot_be_downloaded(self):
        task = Task.objects.create(
            account_email="demo@example.com",
            status=Task.Status.RUNNING,
        )

        response = self.client.get(f"/api/tasks/{task.pk}/download/")
        self.assertEqual(response.status_code, 409)

    def test_missing_task_returns_not_found(self):
        response = self.client.get("/api/tasks/9999/download/")
        self.assertEqual(response.status_code, 404)

    def test_task_results_endpoint_completed(self):
        task = Task.objects.create(
            account_email="results@example.com",
            status=Task.Status.COMPLETED,
            filters={"job_titles": ["CEO"]},
            total_scraped_leads=10,
            total_candidates_generated=50,
            total_verified_emails=2,
            verified_leads=[
                {
                    "first_name": "John",
                    "last_name": "Doe",
                    "job_title": "CEO",
                    "company_name": "Tech Corp",
                    "company_domain": "techcorp.com",
                    "employee_count": "0 - 25",
                    "location": "Lahore",
                    "linkedin_profile_url": "https://linkedin.com/in/johndoe",
                    "email": "john.doe@techcorp.com",
                }
            ],
        )

        response = self.client.get(f"/api/tasks/{task.pk}/results/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["task_id"], task.pk)
        self.assertEqual(response.data["total_scraped_leads"], 10)
        self.assertEqual(response.data["total_candidates_generated"], 50)
        self.assertEqual(response.data["total_verified_emails"], 2)
        self.assertEqual(len(response.data["verified_leads"]), 1)
        self.assertEqual(response.data["verified_leads"][0]["email"], "john.doe@techcorp.com")

    def test_task_results_endpoint_running(self):
        task = Task.objects.create(
            account_email="running@example.com",
            status=Task.Status.RUNNING,
        )

        response = self.client.get(f"/api/tasks/{task.pk}/results/")
        self.assertEqual(response.status_code, 409)

    def test_swagger_schema_endpoint(self):
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)

    def test_swagger_ui_endpoint(self):
        response = self.client.get("/api/docs/")
        self.assertEqual(response.status_code, 200)
