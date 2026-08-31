import re
import unicodedata
from urllib.parse import urlparse


def _clean_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z]", "", ascii_value).lower()


def _extract_domain(value: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""

    parsed = urlparse(value if "://" in value else f"https://{value}")
    hostname = parsed.hostname or ""
    return hostname.removeprefix("www.")


def generate_email_candidates(row: dict[str, str]) -> list[str]:
    """Generate the eight requested candidate formats for one lead."""
    first_name = _clean_name(
        row.get("first_name", row.get("First Name", ""))
    )
    last_name = _clean_name(
        row.get("last_name", row.get("Last Name", ""))
    )
    domain = _extract_domain(
        row.get("company_domain", row.get("Company Domain", ""))
    )

    if not first_name or not last_name or not domain:
        return []

    candidates = [
        f"{first_name}.{last_name}@{domain}",
        f"{first_name}{last_name}@{domain}",
        f"{first_name[0]}{last_name}@{domain}",
        f"{first_name}.{last_name[0]}@{domain}",
        f"{last_name}.{first_name}@{domain}",
        f"{last_name}{first_name}@{domain}",
        f"{first_name[0]}.{last_name}@{domain}",
        f"{first_name}{last_name[0]}@{domain}",
    ]
    return list(dict.fromkeys(candidate.lower() for candidate in candidates))


def add_email_candidates(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return copies of rows with an internal candidate-email list."""
    return [
        {
            **row,
            "email_candidates": generate_email_candidates(row),
        }
        for row in rows
    ]