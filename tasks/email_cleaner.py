import csv
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.utils import timezone

from .email_candidates import _clean_name, _extract_domain
from .models import CSVProcessTask
from .storage import supabase_storage

logger = logging.getLogger(__name__)

PERSONAL_EMAIL_DOMAINS = {
    # Google
    "gmail.com",
    "googlemail.com",
    # Yahoo
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.co.in",
    "yahoo.ca",
    "yahoo.fr",
    "yahoo.de",
    "yahoo.es",
    "yahoo.it",
    "yahoo.com.au",
    "ymail.com",
    "rocketmail.com",
    # Microsoft
    "hotmail.com",
    "hotmail.co.uk",
    "hotmail.fr",
    "hotmail.es",
    "hotmail.de",
    "hotmail.it",
    "outlook.com",
    "outlook.co.uk",
    "live.com",
    "live.co.uk",
    "msn.com",
    "passport.com",
    # AOL
    "aol.com",
    "aim.com",
    # Apple
    "icloud.com",
    "me.com",
    "mac.com",
    # Consumer ISPs & Telcos
    "sbcglobal.net",
    "att.net",
    "bellsouth.net",
    "comcast.net",
    "charter.net",
    "cox.net",
    "verizon.net",
    "earthlink.net",
    "optonline.net",
    "netzero.net",
    "roadrunner.com",
    "tds.net",
    "windstream.net",
    "frontier.com",
    "insightbb.com",
    "zoominternet.net",
    "new.rr.com",
    "newbc.rr.com",
    "wi.rr.com",
    # Privacy / Webmail
    "protonmail.com",
    "proton.me",
    "pm.me",
    "zoho.com",
    "yandex.com",
    "yandex.ru",
    "mail.com",
    "gmx.com",
    "gmx.net",
    "gmx.de",
    "web.de",
    "t-online.de",
    # Asian Webmail
    "qq.com",
    "163.com",
    "126.com",
    "sina.com",
    # Legacy / Other Free Webmail & ISP
    "juno.com",
    "prodigy.net",
    "centurytel.net",
    "nokiamail.com",
    "earthlink.com",
    "corp.earthlink.com",
}

OUTPUT_FIELDNAMES = [
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


def is_personal_email(email: str) -> bool:
    """
    Determines whether an email address belongs to a free or consumer webmail provider.
    """
    if not email or "@" not in email:
        return False
    domain = email.split("@")[-1].strip().lower()
    if domain in PERSONAL_EMAIL_DOMAINS:
        return True
    if domain.endswith(".rr.com"):
        return True
    # Catch any regional / country specific variations of major consumer webmail
    for prefix in (
        "yahoo.",
        "hotmail.",
        "outlook.",
        "live.",
        "msn.",
        "gmail.",
        "ymail.",
        "aol.",
        "icloud.",
        "protonmail.",
    ):
        if domain.startswith(prefix):
            return True
    if domain.endswith("earthlink.net") or domain.endswith("earthlink.com"):
        return True
    return False



def get_clean_business_email(row: Dict[str, str]) -> Tuple[Optional[str], bool]:
    """
    Inspects candidate email fields in the row.
    Returns (business_email, had_personal_email_removed).
    If only personal emails were found or empty, returns (None, had_personal).
    """
    e1 = (
        row.get("email_first")
        or row.get("Email First")
        or row.get("email")
        or row.get("Email")
        or row.get("business_email")
        or ""
    ).strip()

    e2 = (
        row.get("email_second")
        or row.get("Email Second")
        or row.get("personal_email")
        or ""
    ).strip()

    had_personal = False

    if e1:
        if is_personal_email(e1):
            had_personal = True
        elif "@" in e1:
            return e1, False

    if e2:
        if is_personal_email(e2):
            had_personal = True
        elif "@" in e2:
            return e2, had_personal

    return None, had_personal


def generate_single_combination(first_name: str, last_name: str, domain: str) -> str:
    """
    Generates a single standard professional email combination (first.last@domain)
    for contacts that lack an existing business email.
    """
    clean_first = first_name.strip().split()[0] if first_name.strip() else ""
    clean_last = last_name.strip().split()[-1] if last_name.strip() else ""

    f = _clean_name(clean_first)
    l = _clean_name(clean_last)
    d = _extract_domain(domain)

    if not d:
        return ""
    if f and l:
        return f"{f}.{l}@{d}"
    elif f:
        return f"{f}@{d}"
    elif l:
        return f"{l}@{d}"
    return ""


def extract_lead_fields(row: Dict[str, str]) -> Dict[str, str]:
    """
    Extracts and standardizes prospect lead attributes from various CSV column conventions.
    """
    first_name = (
        row.get("first_name")
        or row.get("First Name")
        or row.get("firstname")
        or row.get("FirstName")
        or ""
    ).strip()

    last_name = (
        row.get("last_name")
        or row.get("Last Name")
        or row.get("lastname")
        or row.get("LastName")
        or ""
    ).strip()

    title = (
        row.get("job_title")
        or row.get("Job Title")
        or row.get("title")
        or row.get("Title")
        or row.get("position")
        or ""
    ).strip()

    company = (
        row.get("company_name")
        or row.get("Company Name")
        or row.get("company")
        or row.get("Company")
        or ""
    ).strip()

    location = (
        row.get("city")
        or row.get("City")
        or row.get("location")
        or row.get("Location")
        or ""
    ).strip()

    industry = (
        row.get("industry")
        or row.get("Industry")
        or ""
    ).strip()

    linkedin = (
        row.get("url")
        or row.get("Url")
        or row.get("linkedin")
        or row.get("Linkedin")
        or row.get("LInkedin")
        or row.get("LinkedIn")
        or row.get("linkedin_url")
        or row.get("linkedin_profile_url")
        or ""
    ).strip()

    website = (
        row.get("company_domain")
        or row.get("Company Domain")
        or row.get("website")
        or row.get("Website")
        or row.get("domain")
        or row.get("Domain")
        or ""
    ).strip()

    return {
        "First Name": first_name,
        "Last Name": last_name,
        "Title": title,
        "Company": company,
        "Location": location,
        "Industry": industry,
        "LInkedin": linkedin,
        "Website": website,
    }


def process_csv_leads(
    csv_file,
    task: CSVProcessTask,
) -> Dict[str, Any]:
    """
    Processes an uploaded CSV file:
    1. Removes personal emails.
    2. Preserves existing valid business emails.
    3. For leads without an email, generates combination using company website domain.
    4. Drops leads without any valid email/domain.
    5. Deduplicates emails so all records in the resulting file are unique.
    6. Writes clean output CSV with columns:
       First Name,Last Name,Email,Title,Company,Location,Industry,LInkedin,Website
    7. Returns single download_url with summary statistics.
    """
    now = timezone.now()
    task.status = CSVProcessTask.Status.RUNNING
    task.current_step = "Processing CSV leads"
    task.started_at = now
    task.add_log(f"Started processing uploaded CSV: {task.file_name}")
    task.save(update_fields=["status", "current_step", "started_at", "logs", "updated_at"])

    # Ensure file pointer is at beginning if file-like
    if hasattr(csv_file, "seek"):
        try:
            csv_file.seek(0)
        except Exception:
            pass

    # Read CSV content supporting string, bytes, or file-like objects
    if hasattr(csv_file, "read"):
        raw_bytes = csv_file.read()
        if isinstance(raw_bytes, str):
            text = raw_bytes
        else:
            try:
                text = raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw_bytes.decode("latin1", errors="replace")
    elif isinstance(csv_file, (bytes, bytearray)):
        try:
            text = csv_file.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = csv_file.decode("latin1", errors="replace")
    elif isinstance(csv_file, str):
        if Path(csv_file).is_file():
            with open(csv_file, "r", encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
        else:
            text = csv_file
    else:
        raise ValueError("Unsupported csv_file format provided.")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    task.total_rows = len(rows)
    task.add_log(f"Parsed {task.total_rows} total rows from uploaded CSV.")

    clean_unique_rows: List[Dict[str, str]] = []
    seen_emails = set()

    valid_emails_count = 0
    personal_emails_removed_count = 0
    missing_emails_count = 0
    combinations_count = 0
    duplicates_count = 0

    for raw_row in rows:
        lead_fields = extract_lead_fields(raw_row)
        biz_email, had_personal = get_clean_business_email(raw_row)

        if had_personal:
            personal_emails_removed_count += 1

        if biz_email:
            final_email = biz_email.strip()
        else:
            missing_emails_count += 1
            # Generate combination using company website domain
            comb = generate_single_combination(
                lead_fields["First Name"],
                lead_fields["Last Name"],
                lead_fields["Website"],
            )
            if comb:
                combinations_count += 1
                final_email = comb.strip()
            else:
                final_email = ""

        # Only include leads that have a valid email
        if not final_email:
            continue

        # Deduplicate emails to ensure clean unique data
        email_key = final_email.lower()
        if email_key in seen_emails:
            duplicates_count += 1
            continue

        seen_emails.add(email_key)
        valid_emails_count += 1

        entry = {**lead_fields, "Email": final_email}
        clean_unique_rows.append(entry)

    task.valid_emails_count = valid_emails_count
    task.personal_emails_removed_count = personal_emails_removed_count
    task.missing_emails_count = missing_emails_count
    task.combinations_generated_count = combinations_count
    task.duplicates_removed_count = duplicates_count

    # Write clean output CSV file
    result_directory = Path(settings.BASE_DIR) / "results"
    result_directory.mkdir(exist_ok=True)

    out_filename = f"csv_task_{task.pk}.csv"
    out_path = result_directory / out_filename
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDNAMES)
        writer.writeheader()
        for r in clean_unique_rows:
            writer.writerow(r)

    # Supabase storage upload if configured
    remote_url = ""
    if supabase_storage.is_configured:
        task.add_log("Uploading clean CSV file to Supabase Storage...")
        try:
            upload_res = supabase_storage.upload_file(out_path, f"csv_tasks/{out_filename}")
            if isinstance(upload_res, dict):
                remote_url = upload_res.get("url") or ""
        except Exception as upload_err:
            logger.warning("Supabase storage upload failed: %s", upload_err)
            task.add_log(f"Warning: Remote storage upload failed: {upload_err}")

    download_endpoint = f"/api/tasks/csv-tasks/{task.pk}/download/"
    task.result_path = str(out_path)
    task.result_url = remote_url or download_endpoint
    task.combinations_path = str(out_path)
    task.combinations_url = task.result_url
    task.preview_data = clean_unique_rows[:20]

    task.status = CSVProcessTask.Status.COMPLETED
    task.completed_at = timezone.now()
    task.add_log(
        f"Processing complete: {valid_emails_count} clean unique leads created, "
        f"{personal_emails_removed_count} personal emails removed, "
        f"{duplicates_count} duplicate emails removed, "
        f"{combinations_count} combinations generated."
    )
    task.save()

    return {
        "task_id": task.pk,
        "task_name": task.task_name,
        "file_name": task.file_name,
        "status": task.status,
        "total_rows": task.total_rows,
        "valid_emails_count": task.valid_emails_count,
        "personal_emails_removed_count": task.personal_emails_removed_count,
        "missing_emails_count": task.missing_emails_count,
        "combinations_generated_count": task.combinations_generated_count,
        "duplicates_removed_count": task.duplicates_removed_count,
        "download_url": task.result_url,
        "preview_data": task.preview_data[:10],
    }
