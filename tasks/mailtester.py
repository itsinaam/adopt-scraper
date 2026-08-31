import concurrent.futures
import csv
import logging
import os
import random
import re
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
    max_retries: int = 5,
) -> bool:
    """
    Verifies a single email candidate against the MailTester Ninja HTTP REST API.
    Handles rate-limiting ('Too Many Requests') with exponential backoff and jitter so no emails are dropped.
    """
    client = session or requests
    attempt = 0
    base_backoff = 2.0

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
                backoff_time = (base_backoff * (2 ** (attempt - 1))) + random.uniform(0.5, 1.5)
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
                backoff_time = (base_backoff * (2 ** (attempt - 1))) + random.uniform(1.0, 2.5)
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
            if is_valid:
                logger.info("MailTester verified VALID email: %s (%s - %s)", email, code, message)
            else:
                logger.debug("MailTester rejected email: %s (%s - %s)", email, code, message)

            return is_valid

        except (requests.RequestException, ValueError) as exc:
            backoff_time = (base_backoff * (2 ** (attempt - 1))) + random.uniform(0.5, 1.5)
            logger.warning(
                "MailTester API error for %s (%s). Retrying in %.2fs (attempt %d/%d)...",
                email,
                exc,
                backoff_time,
                attempt,
                max_retries,
            )
            time.sleep(backoff_time)

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
    api_key = get_mailtester_api_key()

    concurrency = int(os.getenv("MAILTESTER_CONCURRENCY", "2"))
    logger.info(
        "Starting MailTester REST API verification for %d candidates with concurrency=%d...",
        len(unique_candidates),
        concurrency,
    )

    valid_emails: Set[str] = set()
    session = requests.Session()

    def _worker(email: str) -> tuple[str, bool]:
        # Slight pacing delay between calls to respect rate limits (~5 per sec)
        time.sleep(random.uniform(0.05, 0.15))
        is_valid = verify_single_email_api(email=email, api_key=api_key, session=session)
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

    logger.info(
        "MailTester API verification complete. Found %d valid emails out of %d candidates.",
        len(valid_emails),
        len(unique_candidates),
    )
    return valid_emails