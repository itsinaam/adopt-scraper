import concurrent.futures
import csv
import logging
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Optional, Set

import requests

logger = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAILTESTER_API_URL = "https://happy.mailtester.ninja/ninja"


class MailTesterError(RuntimeError):
    pass


def get_mailtester_api_key() -> str:
    """
    Retrieves the MailTester subscription API key from environment variable or key.txt file.
    """
    env_key = os.getenv("MAILTESTER_API_KEY", "").strip()
    if env_key:
        return env_key

    key_path_str = os.getenv("MAILTESTER_KEY_PATH", "mailtester/key.txt")
    key_path = Path(key_path_str).resolve()

    if key_path.is_file():
        try:
            content = key_path.read_text(encoding="utf-8").strip()
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.upper().startswith("KEY="):
                    return line.split("=", 1)[1].strip()
                return line
        except Exception as exc:
            logger.warning("Could not read key file %s: %s", key_path, exc)

    raise MailTesterError("MailTester API key was not found in environment or key file.")


def _is_valid_status(status: str) -> bool:
    """Determine if a status string indicates a valid/deliverable email."""
    cleaned = status.strip().lower()
    if cleaned in ("valid", "true", "1", "ok", "accepted"):
        return True
    if cleaned.startswith("valid"):
        return True
    return False


def _read_valid_emails(output_files: list[Path]) -> tuple[set[str], dict]:
    """Helper for reading and parsing CSV results from legacy format or exported runs."""
    valid_emails = set()
    summary = {"files": [], "rows": 0, "headers": [], "statuses": {}}

    for output_file in output_files:
        with output_file.open(newline="", encoding="utf-8-sig") as csv_file:
            rows = list(csv.reader(csv_file))
            summary["files"].append(output_file.name)
            if not rows:
                continue

            for values in rows:
                all_values = [value.strip() for value in values]
                if not all_values:
                    continue

                email_idx = next(
                    (
                        i
                        for i, val in enumerate(all_values)
                        if EMAIL_PATTERN.match(val.lower())
                    ),
                    None,
                )
                if email_idx is None:
                    continue

                summary["rows"] += 1
                email = all_values[email_idx].lower()

                if len(all_values) > email_idx + 2 and all_values[email_idx + 1].lower() in ("mb", "ko", "ok"):
                    status = all_values[email_idx + 2]
                elif len(all_values) > email_idx + 1:
                    status = all_values[email_idx + 1]
                else:
                    status = ""

                status_key = status.strip().lower() or "<empty>"
                summary["statuses"][status_key] = summary["statuses"].get(status_key, 0) + 1

                if _is_valid_status(status):
                    valid_emails.add(email)

    summary["headers"] = sorted(set(summary["headers"]))
    return valid_emails, summary


def verify_single_email_api(
    email: str,
    api_key: str,
    session: Optional[requests.Session] = None,
    max_retries: int = 10,
) -> bool:
    """
    Verifies a single email candidate against the MailTester Ninja HTTP REST API.
    Handles rate-limiting ('Too Many Requests') with exponential backoff and jitter so no emails are dropped.
    """
    client = session or requests
    attempt = 0
    base_backoff = 3.0

    while attempt < max_retries:
        attempt += 1
        try:
            response = client.get(
                MAILTESTER_API_URL,
                params={"email": email, "key": api_key},
                timeout=15,
            )

            # Check for HTTP 429 Rate Limit
            if response.status_code == 429:
                backoff_time = (base_backoff * (1.5 ** (attempt - 1))) + random.uniform(1.0, 2.5)
                print(
                    f"[MAILTESTER] [RATE LIMIT 429] on {email}. Retrying in {backoff_time:.1f}s (attempt {attempt}/{max_retries})...",
                    flush=True,
                )
                logger.warning(
                    "MailTester API rate limit (HTTP 429) on %s. Retrying in %.2fs (attempt %d/%d)...",
                    email,
                    backoff_time,
                    attempt,
                    max_retries,
                )
                time.sleep(backoff_time)
                continue

            response.raise_for_status()
            data = response.json()

            code = str(data.get("code", "")).strip().lower()
            message = str(data.get("message", "")).strip()

            # Check if API returned rate limit message in body
            if "too many requests" in message.lower() or "adapt your query rates" in message.lower():
                backoff_time = (base_backoff * (1.5 ** (attempt - 1))) + random.uniform(1.5, 3.0)
                print(
                    f"[MAILTESTER] [RATE LIMIT] on {email}: '{message}'. Retrying in {backoff_time:.1f}s (attempt {attempt}/{max_retries})...",
                    flush=True,
                )
                logger.warning(
                    "MailTester rate limit in payload for %s: '%s'. Retrying in %.2fs (attempt %d/%d)...",
                    email,
                    message,
                    backoff_time,
                    attempt,
                    max_retries,
                )
                time.sleep(backoff_time)
                continue

            # Check validity
            is_valid = code == "ok" or message.lower() in ("accepted", "valid")
            status_text = "VALID" if is_valid else "INVALID"
            detail = message or code or ("accepted" if is_valid else "rejected")
            print(f"[MAILTESTER] {email} -> {status_text} ({detail})", flush=True)

            if is_valid:
                logger.info("MailTester verified VALID email: %s (%s - %s)", email, code, message)
            else:
                logger.debug("MailTester rejected email: %s (%s - %s)", email, code, message)

            return is_valid

        except (requests.RequestException, ValueError) as exc:
            backoff_time = (base_backoff * (1.5 ** (attempt - 1))) + random.uniform(1.0, 2.0)
            print(
                f"[MAILTESTER] [NETWORK ERROR] on {email}: {exc}. Retrying in {backoff_time:.1f}s (attempt {attempt}/{max_retries})...",
                flush=True,
            )
            logger.warning(
                "MailTester API error for %s (%s). Retrying in %.2fs (attempt %d/%d)...",
                email,
                exc,
                backoff_time,
                attempt,
                max_retries,
            )
            time.sleep(backoff_time)

    print(f"[MAILTESTER] [EXCEEDED RETRIES] for {email}. Marking as INVALID.", flush=True)
    logger.error("Exceeded max retries for email %s. Marking as unverifiable.", email)
    return False


def verify_candidates(candidates: list[str]) -> set[str]:
    """
    Verifies a list of candidate email addresses using direct HTTP REST API calls.
    Executes concurrently with rate pacing and auto-retry to prevent rate limit loss.
    """
    if not candidates:
        return set()

    # Deduplicate while preserving order
    unique_candidates = list(dict.fromkeys(candidates))
    total_candidates = len(unique_candidates)
    api_key = get_mailtester_api_key()

    concurrency = int(os.getenv("MAILTESTER_CONCURRENCY", "1"))
    print(
        f"[MAILTESTER] Starting verification for {total_candidates} candidates (concurrency={concurrency})...",
        flush=True,
    )
    logger.info(
        "Starting MailTester REST API verification for %d candidates with concurrency=%d...",
        total_candidates,
        concurrency,
    )

    valid_emails: Set[str] = set()
    session = requests.Session()
    counter_lock = threading.Lock()
    completed_counter = 0

    def _worker(email: str) -> tuple[str, bool]:
        nonlocal completed_counter
        # Pacing delay between calls to respect rate limits
        time.sleep(random.uniform(0.35, 0.6))
        is_valid = verify_single_email_api(email=email, api_key=api_key, session=session)
        with counter_lock:
            completed_counter += 1
            curr = completed_counter
        if curr % 25 == 0 or is_valid:
            print(
                f"[MAILTESTER] Progress: {curr}/{total_candidates} verified ({(curr / total_candidates) * 100:.1f}%) | {len(valid_emails) + (1 if is_valid else 0)} valid found so far",
                flush=True,
            )
        return email, is_valid

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_email = {
            executor.submit(_worker, email): email
            for email in unique_candidates
        }

        for future in concurrent.futures.as_completed(future_to_email):
            try:
                email, is_valid = future.result()
                if is_valid:
                    valid_emails.add(email)
            except Exception as exc:
                email = future_to_email[future]
                logger.error("Unexpected error verifying candidate %s: %s", email, exc)

    print(
        f"[MAILTESTER] Verification complete: Found {len(valid_emails)} valid emails out of {total_candidates} candidates.",
        flush=True,
    )
    logger.info(
        "MailTester API verification complete. Found %d valid emails out of %d candidates.",
        len(valid_emails),
        total_candidates,
    )
    return valid_emails


def verify_leads_early_stop(
    leads: list[dict],
    progress_callback: Optional[callable] = None,
) -> tuple[list[dict], set[str], dict]:
    """
    Verifies leads using the Early-Stop per Lead (Break on First Hit) strategy.

    For each lead:
    1. Reorders candidates if a winning email format is already known for the lead's domain.
    2. Tests candidates sequentially in order of probability.
    3. As soon as a candidate is verified as VALID, immediately BREAKS out of the candidate loop,
       skipping all remaining combinations for that lead.
    4. Caches the winning pattern for this domain so subsequent colleagues test that pattern on attempt #1.
    5. Concurrently executes across worker threads while respecting rate limits.

    Returns:
        (verified_leads, valid_emails, stats)
    """
    if not leads:
        return (
            [],
            set(),
            {
                "total_leads": 0,
                "completed_leads": 0,
                "valid_emails_count": 0,
                "checks_made": 0,
                "checks_saved": 0,
            },
        )

    total_leads = len(leads)
    api_key = get_mailtester_api_key()
    concurrency = int(os.getenv("MAILTESTER_CONCURRENCY", "1"))

    print(
        f"[MAILTESTER] Starting Early-Stop verification for {total_leads} leads (concurrency={concurrency})...",
        flush=True,
    )
    logger.info(
        "Starting MailTester Early-Stop verification for %d leads with concurrency=%d...",
        total_leads,
        concurrency,
    )

    session = requests.Session()
    domain_patterns: dict[str, int] = {}
    patterns_lock = threading.Lock()

    completed_lock = threading.Lock()
    completed_counter = 0
    valid_counter = 0
    total_checks_made = 0
    total_checks_saved = 0
    valid_emails: Set[str] = set()

    def _process_lead(lead: dict) -> tuple[dict, Optional[str], int, int]:
        nonlocal completed_counter, valid_counter, total_checks_made, total_checks_saved
        candidates = list(dict.fromkeys(lead.get("email_candidates") or []))
        if not candidates:
            with completed_lock:
                completed_counter += 1
            return dict(lead), None, 0, 0

        # Extract domain from candidates
        lead_domain = ""
        first_email = candidates[0]
        if "@" in first_email:
            lead_domain = first_email.split("@", 1)[1].lower()

        # Domain pattern prioritization: if we already learned a winning index for this domain, test it first!
        with patterns_lock:
            known_pattern_idx = domain_patterns.get(lead_domain)

        ordered_candidates = candidates
        if known_pattern_idx is not None and known_pattern_idx < len(candidates):
            winning_cand = candidates[known_pattern_idx]
            ordered_candidates = [winning_cand] + [
                c for i, c in enumerate(candidates) if i != known_pattern_idx
            ]

        lead_checks_made = 0
        lead_checks_saved = 0
        verified_email: Optional[str] = None

        for cand in ordered_candidates:
            # Pacing delay between calls to respect rate limits
            time.sleep(random.uniform(0.35, 0.6))
            is_valid = verify_single_email_api(email=cand, api_key=api_key, session=session)
            lead_checks_made += 1

            if is_valid:
                verified_email = cand
                lead_checks_saved = len(ordered_candidates) - lead_checks_made

                # Remember winning candidate format index for this domain
                try:
                    orig_idx = candidates.index(cand)
                    with patterns_lock:
                        domain_patterns[lead_domain] = orig_idx
                except ValueError:
                    pass

                # EARLY-STOP: Break immediately on first hit!
                break

        updated_lead = dict(lead)
        updated_lead["email"] = verified_email or ""

        with completed_lock:
            completed_counter += 1
            if verified_email:
                valid_counter += 1
                valid_emails.add(verified_email)
            total_checks_made += lead_checks_made
            total_checks_saved += lead_checks_saved
            curr_completed = completed_counter
            curr_valids = valid_counter
            curr_checks = total_checks_made
            curr_saved = total_checks_saved

        if curr_completed % 10 == 0 or curr_completed == total_leads or verified_email:
            pct = (curr_completed / total_leads) * 100
            print(
                f"[MAILTESTER] Progress: {curr_completed}/{total_leads} leads ({pct:.1f}%) | "
                f"{curr_valids} valid found | Total calls: {curr_checks} (Saved: {curr_saved} calls)",
                flush=True,
            )
            if progress_callback:
                try:
                    progress_callback(curr_completed, total_leads, curr_valids, curr_checks, curr_saved)
                except Exception as cb_err:
                    logger.debug("Progress callback error: %s", cb_err)

        return updated_lead, verified_email, lead_checks_made, lead_checks_saved

    results: list[dict] = [None] * total_leads

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_idx = {
            executor.submit(_process_lead, lead): idx
            for idx, lead in enumerate(leads)
        }

        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                updated_lead, _, _, _ = future.result()
                results[idx] = updated_lead
            except Exception as exc:
                logger.error("Unexpected error verifying lead index %d: %s", idx, exc)
                fallback_lead = dict(leads[idx])
                fallback_lead["email"] = ""
                results[idx] = fallback_lead

    stats = {
        "total_leads": total_leads,
        "completed_leads": completed_counter,
        "valid_emails_count": len(valid_emails),
        "checks_made": total_checks_made,
        "checks_saved": total_checks_saved,
    }

    print(
        f"[MAILTESTER] Early-Stop complete: Found {len(valid_emails)} valid emails across {total_leads} leads. "
        f"Total calls: {total_checks_made}, Saved calls: {total_checks_saved}!",
        flush=True,
    )
    logger.info(
        "MailTester Early-Stop complete: %d valid emails from %d leads. Calls: %d, Saved: %d.",
        len(valid_emails),
        total_leads,
        total_checks_made,
        total_checks_saved,
    )

    return results, valid_emails, stats