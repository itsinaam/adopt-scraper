import json
from pathlib import Path
from django.conf import settings
from scraper.adapt_io.session import authenticate_with_playwright
from scraper.adapt_io.worker import run_in_thread


def authenticate_account_credentials(
    email: str,
    password: str,
    session_state: dict | None = None,
) -> dict:
    """
    Authenticates Adapt.io account credentials via Playwright.
    Optionally saves the verified session state to adapt_session.json.
    """
    session_state = run_in_thread(
        authenticate_with_playwright,
        email=email,
        password=password,
        session_state=session_state,
    )

    try:
        session_file = Path(settings.BASE_DIR) / "adapt_session.json"
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_state, f, indent=2)
    except Exception:
        pass

    return session_state