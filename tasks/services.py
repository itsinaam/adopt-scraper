import csv
import logging
import threading
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from scraper.adapt_io.session import scrape_with_playwright
from scraper.adapt_io.worker import run_in_thread

from .email_candidates import add_email_candidates
from .mailtester import verify_candidates, verify_leads_early_stop
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
            if not Task.objects.filter(pk=task_id).exists():
                print(f"[TASK {task_id}] Task record was deleted from DB! Aborting background execution.", flush=True)
                raise SystemExit(f"Task {task_id} was deleted from database")
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
        except SystemExit:
            raise
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

        enable_verification = (
            os.getenv("ENABLE_MAILTESTER_VERIFICATION", "true").strip().lower()
            in ("true", "1", "yes")
        )

        valid_emails = set()
        stats = {}
        if enable_verification:
            log_step(
                f"Starting Smart Early-Stop verification for {raw_row_count} leads (up to {len(candidates)} candidate combinations)...",
                step="VERIFYING_EMAILS",
                progress=82,
            )

            def _on_progress(completed: int, total: int, valids: int, checks: int, saved: int):
                pct = (completed / total) * 100 if total else 0
                step_progress = 82 + int((completed / total) * 11)  # 82% to 93%
                log_step(
                    f"Verifying leads: {completed}/{total} processed ({pct:.1f}%) | "
                    f"{valids} valid emails found ({checks} checks made, {saved} redundant calls saved)",
                    step="VERIFYING_EMAILS",
                    progress=step_progress,
                )

            verified_leads, valid_emails, stats = run_in_thread(
                verify_leads_early_stop,
                enriched_rows,
                progress_callback=_on_progress,
            )

            log_step(
                f"MailTester Early-Stop complete: {len(valid_emails)} valid emails found "
                f"from {raw_row_count} leads ({stats.get('checks_made', 0)} checks made, "
                f"{stats.get('checks_saved', 0)} redundant checks saved!).",
                step="EMAILS_VERIFIED",
                progress=93,
            )

            # Filter rows to only those with valid verified emails
            rows = [
                row for row in verified_leads
                if row.get("email")
            ]
        else:
            log_step(
                f"Email verification bypassed (ENABLE_MAILTESTER_VERIFICATION=false). "
                f"Exporting all {raw_row_count} leads and {len(candidates)} candidate combinations...",
                step="SAVING_RESULTS",
                progress=90,
            )
            rows = [
                {
                    **{
                        key: value
                        for key, value in row.items()
                        if key != "email_candidates"
                    },
                    "email": (row.get("email_candidates") or [""])[0],
                    "email_candidates": row.get("email_candidates", []),
                }
                for row in enriched_rows
            ]

        task_industries = (task.filters or {}).get("industries", [])
        default_industry = task_industries[0] if isinstance(task_industries, list) and task_industries else ""
        for r in rows:
            if not r.get("industry") and default_industry:
                r["industry"] = default_industry

        result_directory = Path(settings.BASE_DIR) / "results"
        result_directory.mkdir(exist_ok=True)
        result_filename = f"task_{task.pk}.csv"
        result_path = result_directory / result_filename

        fieldnames = [
            "First Name",
            "Last Name",
            "Email",
            "Title",
            "Company",
            "Location",
            "Industry",
            "LInkedin",
            "Website",
        ]
        with result_path.open("w", newline="", encoding="utf-8") as result_file:
            writer = csv.DictWriter(result_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "First Name": row.get("first_name", ""),
                        "Last Name": row.get("last_name", ""),
                        "Email": row.get("email", ""),
                        "Title": row.get("job_title", "") or row.get("title", ""),
                        "Company": row.get("company_name", "") or row.get("company", ""),
                        "Location": row.get("location", ""),
                        "Industry": row.get("industry", "") or default_industry,
                        "LInkedin": row.get("linkedin_profile_url", "") or row.get("linkedin", ""),
                        "Website": row.get("company_domain", "") or row.get("website", ""),
                    }
                )

        # Standalone clean list of all email combinations (ready for MailTester Desktop App or bulk tools)
        combinations_filename = f"task_{task.pk}_combinations.csv"
        combinations_path = result_directory / combinations_filename
        with combinations_path.open("w", newline="", encoding="utf-8") as comb_file:
            comb_writer = csv.writer(comb_file)
            comb_writer.writerow(["Email Combination"])
            for candidate in candidates:
                comb_writer.writerow([candidate])

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

        if enable_verification:
            checks_saved = stats.get("checks_saved", 0)
            completion_msg = (
                f"Completed. Scraped {len(rows)} prospects with valid emails "
                f"from {raw_row_count} leads (Early-Stop saved {checks_saved} redundant API calls); "
                f"generated candidates for {rows_with_candidates} leads."
            )
        else:
            completion_msg = (
                f"Completed. Scraped {len(rows)} leads and generated {len(candidates)} "
                f"email candidate combinations across {rows_with_candidates} leads (verification bypassed)."
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