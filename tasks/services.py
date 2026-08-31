import csv
import logging
import threading
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from scraper.adapt_io.session import scrape_with_playwright
from scraper.adapt_io.worker import run_in_thread

from .email_candidates import add_email_candidates
from .mailtester import verify_candidates
from .models import Task
from .storage import supabase_storage

logger = logging.getLogger(__name__)


def run_task(task_id: int, password: str):
    task = Task.objects.get(pk=task_id)

    try:
        task.current_step = "OPENING_ADAPT"
        task.progress = 5
        task.message = "Opening Adapt.io..."
        task.save(
            update_fields=[
                "current_step",
                "progress",
                "message",
            ]
        )

        task.current_step = "RUNNING_PLAYWRIGHT"
        task.progress = 10
        task.message = "Logging in and opening Prospect Search..."
        task.save(
            update_fields=[
                "current_step",
                "progress",
                "message",
            ]
        )

        rows = run_in_thread(
            scrape_with_playwright,
            email=task.account_email,
            password=password,
            filters=task.filters,
        )

        task.current_step = "VERIFYING_EMAILS"
        task.progress = 80
        task.message = "Generating email candidates..."
        task.save(
            update_fields=[
                "current_step",
                "progress",
                "message",
                "updated_at",
            ]
        )

        raw_row_count = len(rows)
        enriched_rows = add_email_candidates(rows)
        candidates = [
            candidate
            for row in enriched_rows
            for candidate in row["email_candidates"]
        ]
        rows_with_candidates = sum(
            bool(row["email_candidates"])
            for row in enriched_rows
        )
        if raw_row_count and not candidates:
            raise RuntimeError(
                f"Could not generate email candidates for {raw_row_count} scraped leads"
            )

        task.message = (
            f"Running MailTester for {len(candidates)} email candidates..."
        )
        task.save(
            update_fields=[
                "message",
                "updated_at",
            ]
        )
        valid_emails = run_in_thread(verify_candidates, candidates)
        task.progress = 90
        task.message = (
            f"MailTester finished: {len(valid_emails)} valid emails found "
            f"from {len(candidates)} candidates."
        )
        task.save(
            update_fields=[
                "progress",
                "message",
                "updated_at",
            ]
        )
        rows = [
            {
                **{
                    key: value
                    for key, value in row.items()
                    if key != "email_candidates"
                },
                "email": next(
                    (
                        candidate
                        for candidate in row["email_candidates"]
                        if candidate in valid_emails
                    ),
                    "",
                ),
            }
            for row in enriched_rows
            if any(candidate in valid_emails for candidate in row["email_candidates"])
        ]

        result_directory = Path(settings.BASE_DIR) / "results"
        result_directory.mkdir(exist_ok=True)
        result_filename = f"task_{task.pk}.csv"
        result_path = result_directory / result_filename

        fieldnames = [
            "First Name",
            "Last Name",
            "Job Title",
            "Company Name",
            "Company Domain",
            "Employee Count",
            "Location",
            "LinkedIn Profile URL",
            "Email",
        ]
        with result_path.open("w", newline="", encoding="utf-8") as result_file:
            writer = csv.DictWriter(result_file, fieldnames=fieldnames)
            if fieldnames:
                writer.writeheader()
                writer.writerows(
                    {
                        "First Name": row.get("first_name", ""),
                        "Last Name": row.get("last_name", ""),
                        "Job Title": row.get("job_title", ""),
                        "Company Name": row.get("company_name", ""),
                        "Company Domain": row.get("company_domain", ""),
                        "Employee Count": row.get("employee_count", ""),
                        "Location": row.get("location", ""),
                        "LinkedIn Profile URL": row.get(
                            "linkedin_profile_url",
                            "",
                        ),
                        "Email": row.get("email", ""),
                    }
                    for row in rows
                )

        # Upload CSV to Supabase Storage bucket if configured
        storage_url = ""
        storage_path = str(result_path)
        if supabase_storage.is_configured:
            try:
                storage_result = supabase_storage.upload_file(
                    file_path=result_path,
                    destination_name=result_filename,
                    content_type="text/csv",
                )
                if storage_result:
                    storage_path = storage_result.get("storage_path", storage_path)
                    storage_url = storage_result.get("url", "")
            except Exception as upload_err:
                logger.warning("Supabase storage upload error (will fallback to local): %s", upload_err)

        task.status = Task.Status.COMPLETED
        task.current_step = "COMPLETED"
        task.progress = 100
        task.total_scraped_leads = raw_row_count
        task.total_candidates_generated = len(candidates)
        task.total_verified_emails = len(valid_emails)
        task.verified_leads = rows
        task.message = (
            f"Completed. Scraped {len(rows)} prospects with valid emails "
            f"from {raw_row_count} leads; generated candidates for "
            f"{rows_with_candidates} leads."
        )
        task.result_path = storage_path
        task.result_url = storage_url
        task.completed_at = timezone.now()
        task.save(
            update_fields=[
                "status",
                "current_step",
                "progress",
                "total_scraped_leads",
                "total_candidates_generated",
                "total_verified_emails",
                "verified_leads",
                "message",
                "result_path",
                "result_url",
                "completed_at",
                "updated_at",
            ]
        )

    except Exception as exc:
        logger.exception("Error executing task %s", task_id)
        task.status = Task.Status.FAILED
        task.current_step = "FAILED"
        task.message = "Adapt.io scraping failed."
        task.error = f"{type(exc).__name__}: {str(exc)[:900]}"
        task.completed_at = timezone.now()

        task.save(
            update_fields=[
                "status",
                "current_step",
                "message",
                "error",
                "completed_at",
                "updated_at",
            ]
        )


def start_task(task_id: int, password: str) -> None:
    thread = threading.Thread(
        target=run_task,
        args=(task_id, password),
        daemon=True,
    )
    thread.start()