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
    import os
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

    from django.db import close_old_connections
    close_old_connections()
    task = Task.objects.get(pk=task_id)

    def log_step(message: str, step: str = None, progress: int = None):
        print(f"[TASK {task_id}] [{step or task.current_step}] {message}", flush=True)
        try:
            close_old_connections()
            task.message = message
            if step:
                task.current_step = step
            if progress is not None:
                task.progress = progress
            task.add_log(message, step=task.current_step)
            task.save(
                update_fields=[
                    "current_step",
                    "progress",
                    "message",
                    "logs",
                    "updated_at",
                ]
            )
        except Exception:
            pass

    try:
        log_step("Starting scraping task...", step="STARTING", progress=5)

        rows = run_in_thread(
            scrape_with_playwright,
            email=task.account_email,
            password=password,
            filters=task.filters,
            log_callback=log_step,
        )

        raw_row_count = len(rows)
        log_step(
            f"Adapt.io scraping finished: collected {raw_row_count} total prospect leads.",
            step="LEADS_SCRAPED",
            progress=75,
        )

        log_step(
            "Generating email candidate permutations...",
            step="GENERATING_CANDIDATES",
            progress=80,
        )
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

        log_step(
            f"Running MailTester verification for {len(candidates)} candidates...",
            step="VERIFYING_EMAILS",
            progress=85,
        )
        valid_emails = run_in_thread(verify_candidates, candidates)

        log_step(
            f"MailTester finished: {len(valid_emails)} valid emails found "
            f"from {len(candidates)} candidates.",
            step="EMAILS_VERIFIED",
            progress=92,
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
                    log_step("Exported CSV uploaded to cloud storage.", step="UPLOADED")
            except Exception as upload_err:
                logger.warning("Supabase storage upload error (will fallback to local): %s", upload_err)

        completion_msg = (
            f"Completed. Scraped {len(rows)} prospects with valid emails "
            f"from {raw_row_count} leads; generated candidates for "
            f"{rows_with_candidates} leads."
        )
        task.status = Task.Status.COMPLETED
        task.current_step = "COMPLETED"
        task.progress = 100
        task.total_scraped_leads = raw_row_count
        task.total_candidates_generated = len(candidates)
        task.total_verified_emails = len(valid_emails)
        task.verified_leads = rows
        task.message = completion_msg
        task.result_path = storage_path
        task.result_url = storage_url
        task.completed_at = timezone.now()
        task.add_log(completion_msg, step="COMPLETED")
        print(f"[TASK {task_id}] [COMPLETED] {completion_msg}", flush=True)
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
                "logs",
                "result_path",
                "result_url",
                "completed_at",
                "updated_at",
            ]
        )

    except Exception as exc:
        logger.exception("Error executing task %s", task_id)
        error_msg = f"{type(exc).__name__}: {str(exc)[:900]}"
        print(f"[TASK {task_id}] [FAILED] {error_msg}", flush=True)
        task.status = Task.Status.FAILED
        task.current_step = "FAILED"
        task.message = f"Adapt.io scraping failed: {type(exc).__name__}"
        task.error = error_msg
        task.completed_at = timezone.now()
        task.add_log(f"Scraping task failed: {error_msg}", step="FAILED")

        task.save(
            update_fields=[
                "status",
                "current_step",
                "message",
                "error",
                "logs",
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