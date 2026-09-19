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

    def test_structured_locations_with_city_and_country(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"ADAPT_EMAIL": "env_user@example.com", "ADAPT_PASSWORD": "env_password"}):
            serializer = TaskSerializer(
                data={
                    "filters": {
                        "job_titles": ["CEO"],
                        "locations": {
                            "country": ["Canada", "United States"],
                            "city": ["Kitchener-Waterloo (ON)", "Halifax (NS)"],
                        },
                    }
                }
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            locs = serializer.validated_data["filters"]["locations"]
            self.assertEqual(locs["country"], ["Canada", "United States"])
            self.assertEqual(locs["city"], ["Kitchener-Waterloo (ON)", "Halifax (NS)"])

    def test_top_level_cities_and_countries(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"ADAPT_EMAIL": "env_user@example.com", "ADAPT_PASSWORD": "env_password"}):
            serializer = TaskSerializer(
                data={
                    "filters": {
                        "job_titles": ["CEO"],
                        "cities": ["Halifax (NS)"],
                        "countries": ["Canada"],
                    }
                }
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertEqual(serializer.validated_data["filters"]["cities"], ["Halifax (NS)"])
            self.assertEqual(serializer.validated_data["filters"]["countries"], ["Canada"])


class TaskAPITests(APITestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="testadmin",
            email="testadmin@example.com",
            password="password",
        )
        self.client.force_authenticate(user=self.user)

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
        self.assertEqual(response.data["running_count"], 1)
        self.assertEqual(len(response.data["tasks"]), 1)

    def test_current_task_returns_all_running_tasks(self):
        t1 = Task.objects.create(
            account_email="task1@example.com",
            status=Task.Status.RUNNING,
            progress=30,
            message="Task 1 running",
        )
        t2 = Task.objects.create(
            account_email="task2@example.com",
            status=Task.Status.RUNNING,
            progress=60,
            message="Task 2 running",
        )
        response = self.client.get("/api/tasks/current/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["running_count"], 2)
        self.assertEqual(len(response.data["tasks"]), 2)
        task_ids = [t["id"] for t in response.data["tasks"]]
        self.assertIn(t1.id, task_ids)
        self.assertIn(t2.id, task_ids)
        self.assertEqual(response.data["task"]["id"], t2.id)

    def test_task_list_defaults_to_running_only(self):
        Task.objects.create(account_email="a@example.com", status=Task.Status.RUNNING)
        Task.objects.create(account_email="b@example.com", status=Task.Status.FAILED)
        res_default = self.client.get("/api/tasks/")
        self.assertEqual(res_default.status_code, 200)
        self.assertEqual(res_default.data["total"], 1)
        self.assertEqual(res_default.data["tasks"][0]["status"], "RUNNING")

        res_all = self.client.get("/api/tasks/?status=all")
        self.assertEqual(res_all.status_code, 200)
        self.assertEqual(res_all.data["total"], 2)

    def test_current_task_ignores_failed_tasks(self):
        Task.objects.create(account_email="failed@example.com", status=Task.Status.FAILED)
        res = self.client.get("/api/tasks/current/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.data.get("task"))
        self.assertEqual(res.data.get("running_count"), 0)
        self.assertEqual(len(res.data.get("tasks")), 0)

        res_running = self.client.get("/api/tasks/running/")
        self.assertEqual(res_running.status_code, 200)
        self.assertEqual(len(res_running.data.get("tasks")), 0)

    def test_failed_task_can_be_retried(self):
        from unittest.mock import patch

        task = Task.objects.create(
            user=self.user,
            account_email="retry@example.com",
            filters={"job_titles": ["CEO"]},
            status=Task.Status.FAILED,
            error="Temporary timeout",
            progress=45,
        )
        with patch("tasks.views.start_task") as mock_start:
            response = self.client.post(
                f"/api/tasks/{task.id}/retry/",
                {"password": "secret"},
                format="json",
            )

        self.assertEqual(response.status_code, 202)
        mock_start.assert_called_once_with(task.id, "secret")
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.RUNNING)
        self.assertEqual(task.progress, 0)
        self.assertEqual(task.error, "")
        self.assertEqual(task.filters, {"job_titles": ["CEO"]})

    def test_retry_requires_failed_task(self):
        from unittest.mock import patch

        task = Task.objects.create(
            user=self.user,
            account_email="running@example.com",
            status=Task.Status.RUNNING,
        )
        with patch("tasks.views.start_task") as mock_start:
            response = self.client.post(f"/api/tasks/{task.id}/retry/", {}, format="json")

        self.assertEqual(response.status_code, 400)
        mock_start.assert_not_called()

    def test_retry_uses_environment_password(self):
        import os
        from unittest.mock import patch

        task = Task.objects.create(
            user=self.user,
            account_email="retry@example.com",
            status=Task.Status.FAILED,
        )
        with patch.dict(os.environ, {"ADAPT_PASSWORD": "env-secret"}), patch("tasks.views.start_task") as mock_start:
            response = self.client.post(f"/api/tasks/{task.id}/retry/", {}, format="json")

        self.assertEqual(response.status_code, 202)
        mock_start.assert_called_once_with(task.id, "env-secret")

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

    def test_stop_running_task(self):
        task = Task.objects.create(
            account_email="running@example.com",
            status=Task.Status.RUNNING,
        )
        response = self.client.post("/api/tasks/stop/")
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.FAILED)
        self.assertEqual(task.current_step, "STOPPED")

    def test_stop_task_by_id(self):
        task = Task.objects.create(
            account_email="running_id@example.com",
            status=Task.Status.RUNNING,
        )
        response = self.client.post(f"/api/tasks/{task.pk}/stop/")
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.FAILED)

    def test_stop_task_not_running(self):
        response = self.client.post("/api/tasks/stop/")
        self.assertEqual(response.status_code, 404)

    def test_task_add_log_and_serialization(self):
        task = Task.objects.create(
            account_email="logged@example.com",
            status=Task.Status.RUNNING,
            current_step="INITIALIZING",
        )
        task.add_log("Session loaded successfully.", step="SESSION_LOADED")
        task.add_log("Opening Prospect Search...", step="SEARCH")
        task.save()
        task.refresh_from_db()

        self.assertEqual(len(task.logs), 2)
        self.assertEqual(task.logs[0]["message"], "Session loaded successfully.")
        self.assertEqual(task.logs[0]["step"], "SESSION_LOADED")
        self.assertIn("timestamp", task.logs[0])

        serializer = TaskSerializer(task)
        self.assertIn("logs", serializer.data)
        self.assertEqual(len(serializer.data["logs"]), 2)

    def test_logs_endpoints_removed(self):
        task = Task.objects.create(
            account_email="logs_endpoint@example.com",
            status=Task.Status.RUNNING,
            current_step="SCRAPING",
            progress=50,
            message="Scraping in progress...",
        )
        res_by_id = self.client.get(f"/api/tasks/{task.pk}/logs/")
        self.assertEqual(res_by_id.status_code, 404)

        res_curr = self.client.get("/api/tasks/current/logs/")
        self.assertEqual(res_curr.status_code, 404)

    def test_start_task_no_conflict_when_running(self):
        from unittest.mock import patch
        Task.objects.create(
            account_email="running@example.com",
            status=Task.Status.RUNNING,
        )
        with patch("tasks.views.start_task") as mock_start:
            response = self.client.post(
                "/api/tasks/start/",
                {
                    "account_email": "new_task@example.com",
                    "password": "secret_pass",
                    "filters": {"job_titles": ["CEO"]},
                },
                format="json",
            )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.data["task"]["account_email"], "new_task@example.com")
            self.assertTrue(mock_start.called)

    def test_completed_tasks_list_endpoint(self):
        from django.utils import timezone
        now = timezone.now()
        t_completed = Task.objects.create(
            account_email="done@example.com",
            status=Task.Status.COMPLETED,
            filters={"job_titles": ["CEO"], "locations": {"city": ["Dubai"]}},
            total_scraped_leads=500,
            total_candidates_generated=4000,
            total_verified_emails=120,
            started_at=now,
            completed_at=now,
            result_url="https://example.com/results.csv",
        )
        t_running = Task.objects.create(
            account_email="active@example.com",
            status=Task.Status.RUNNING,
        )

        response = self.client.get("/api/tasks/completed/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 1)
        item = response.data["tasks"][0]
        self.assertEqual(item["task_id"], t_completed.pk)
        self.assertEqual(item["total_leads_scraped"], 500)
        self.assertEqual(item["total_combinations"], 4000)
        self.assertEqual(item["total_verified_emails"], 120)
        self.assertEqual(item["url_of_file"], "https://example.com/results.csv")
        self.assertEqual(item["filters"]["job_titles"], ["CEO"])
        self.assertIn("task_started_at", item)
        self.assertIn("task_completed_at", item)

    def test_completed_task_by_id_endpoint(self):
        from django.utils import timezone
        now = timezone.now()
        task = Task.objects.create(
            account_email="single@example.com",
            status=Task.Status.COMPLETED,
            filters={"industries": ["Software"]},
            total_scraped_leads=100,
            total_candidates_generated=800,
            started_at=now,
            completed_at=now,
            result_url="https://example.com/single.csv",
        )
        res = self.client.get(f"/api/tasks/{task.pk}/completed/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["task"]["task_id"], task.pk)
        self.assertEqual(res.data["task"]["total_leads_scraped"], 100)
        self.assertEqual(res.data["task"]["total_combinations"], 800)
        self.assertEqual(res.data["task"]["url_of_file"], "https://example.com/single.csv")

        # 404 for non-existent
        res_404 = self.client.get("/api/tasks/99999/completed/")
        self.assertEqual(res_404.status_code, 404)


class TaskUserIsolationAPITests(APITestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="test_admin",
            email="admin@test.com",
            password="pass",
        )
        self.user1 = User.objects.create_user(
            username="test_user1",
            email="user1@test.com",
            password="pass",
        )
        self.user2 = User.objects.create_user(
            username="test_user2",
            email="user2@test.com",
            password="pass",
        )

        self.task_user1 = Task.objects.create(
            user=self.user1,
            task_name="User1 Campaign",
            account_email="u1@adapt.com",
            status=Task.Status.RUNNING,
        )
        self.task_user2 = Task.objects.create(
            user=self.user2,
            task_name="User2 Campaign",
            account_email="u2@adapt.com",
            status=Task.Status.RUNNING,
        )

    def test_user_only_sees_own_tasks_in_list(self):
        self.client.force_authenticate(user=self.user1)
        res = self.client.get("/api/tasks/?status=all")
        self.assertEqual(res.status_code, 200)
        task_ids = [t["id"] for t in res.data["tasks"]]
        self.assertIn(self.task_user1.id, task_ids)
        self.assertNotIn(self.task_user2.id, task_ids)
        self.assertEqual(res.data["total"], 1)
        self.assertEqual(res.data["tasks"][0]["task_name"], "User1 Campaign")

    def test_admin_sees_all_tasks_across_users(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/tasks/?status=all")
        self.assertEqual(res.status_code, 200)
        task_ids = [t["id"] for t in res.data["tasks"]]
        self.assertIn(self.task_user1.id, task_ids)
        self.assertIn(self.task_user2.id, task_ids)
        self.assertEqual(res.data["total"], 2)

    def test_user_cannot_access_other_user_completed_task(self):
        t_completed_u1 = Task.objects.create(
            user=self.user1,
            task_name="Completed 1",
            account_email="u1@adapt.com",
            status=Task.Status.COMPLETED,
        )
        # user2 cannot access user1's completed task
        self.client.force_authenticate(user=self.user2)
        res = self.client.get(f"/api/tasks/{t_completed_u1.id}/completed/")
        self.assertEqual(res.status_code, 404)

        # user1 can access their own completed task
        self.client.force_authenticate(user=self.user1)
        res_owner = self.client.get(f"/api/tasks/{t_completed_u1.id}/completed/")
        self.assertEqual(res_owner.status_code, 200)
        self.assertEqual(res_owner.data["task"]["task_name"], "Completed 1")

        # admin can also access user1's completed task
        self.client.force_authenticate(user=self.admin)
        res_admin = self.client.get(f"/api/tasks/{t_completed_u1.id}/completed/")
        self.assertEqual(res_admin.status_code, 200)

    def test_user_cannot_stop_other_user_running_task(self):
        self.client.force_authenticate(user=self.user2)
        res = self.client.post(f"/api/tasks/{self.task_user1.id}/stop/")
        self.assertEqual(res.status_code, 404)
        self.task_user1.refresh_from_db()
        self.assertEqual(self.task_user1.status, Task.Status.RUNNING)

        # user1 can stop their own task
        self.client.force_authenticate(user=self.user1)
        res_stop = self.client.post(f"/api/tasks/{self.task_user1.id}/stop/")
        self.assertEqual(res_stop.status_code, 200)
        self.task_user1.refresh_from_db()
        self.assertEqual(self.task_user1.status, Task.Status.FAILED)

    def test_start_task_sets_task_name_and_owner(self):
        from unittest.mock import patch
        self.client.force_authenticate(user=self.user1)
        with patch("tasks.views.start_task"):
            res = self.client.post(
                "/api/tasks/start/",
                {
                    "task_name": "Q4 Prospecting",
                    "account_email": "u1@adapt.com",
                    "password": "secret",
                    "filters": {"job_titles": ["CTO"]},
                },
                format="json",
            )
            self.assertEqual(res.status_code, 202)
            task_data = res.data["task"]
            self.assertEqual(task_data["task_name"], "Q4 Prospecting")
            self.assertEqual(task_data["user"], self.user1.username)

    def test_user_can_delete_own_task(self):
        self.client.force_authenticate(user=self.user1)
        res = self.client.delete(f"/api/tasks/{self.task_user1.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Task.objects.filter(id=self.task_user1.id).exists())

    def test_user_cannot_delete_other_user_task(self):
        self.client.force_authenticate(user=self.user2)
        res = self.client.delete(f"/api/tasks/{self.task_user1.id}/")
        self.assertEqual(res.status_code, 404)
        self.assertTrue(Task.objects.filter(id=self.task_user1.id).exists())

    def test_admin_can_delete_any_task(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f"/api/tasks/{self.task_user2.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Task.objects.filter(id=self.task_user2.id).exists())

    def test_csv_export_uses_payload_industry_and_replaces_revenue(self):
        import csv
        from pathlib import Path
        from tasks.services import _process_scraping_results

        task = Task.objects.create(
            user=self.user1,
            task_name="Software Scraping",
            account_email="u1@adapt.com",
            filters={"industries": ["Software & Internet"]},
            status=Task.Status.RUNNING,
        )

        scraped_leads = [
            {
                "first_name": "Ahmed",
                "last_name": "Mahmoud",
                "job_title": "Founder",
                "company_name": "DXwand",
                "company_domain": "dxwand.com",
                "location": "Dubai",
                "industry": "$10 - 50M",  # Adapt revenue wrongly picked previously
                "linkedin_profile_url": "https://linkedin.com/in/ahmed",
            }
        ]

        from unittest.mock import patch
        with patch("tasks.services.supabase_storage.upload_file", return_value=""):
            _process_scraping_results(task, scraped_leads, verify_emails=False)

        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETED)
        self.assertEqual(task.verified_leads[0]["industry"], "Software & Internet")

        csv_file = Path(task.result_path)
        self.assertTrue(csv_file.exists())
        with csv_file.open("r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 1)
            self.assertEqual(reader[0]["Industry"], "Software & Internet")
            self.assertNotEqual(reader[0]["Industry"], "$10 - 50M")


class AuthenticationAPITests(APITestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username="authuser",
            email="authuser@example.com",
            password="CorrectPassword123!",
        )

    def test_unauthenticated_request_to_protected_endpoint_rejected(self):
        res = self.client.get("/api/tasks/")
        self.assertEqual(res.status_code, 401)

    def test_login_success(self):
        res = self.client.post(
            "/api/auth/login/",
            {"email": "authuser@example.com", "password": "CorrectPassword123!"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("token", res.data)
        self.assertEqual(res.data["username"], "authuser")
        self.assertEqual(res.data["email"], "authuser@example.com")

    def test_login_invalid_credentials(self):
        res = self.client.post(
            "/api/auth/login/",
            {"email": "authuser@example.com", "password": "WrongPassword"},
        )
        self.assertEqual(res.status_code, 401)

    def test_user_me_endpoint_with_token(self):
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        res = self.client.get("/api/auth/me/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["username"], "authuser")



