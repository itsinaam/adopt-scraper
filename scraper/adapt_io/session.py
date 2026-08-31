import json
import logging
from pathlib import Path
from django.conf import settings
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from scraper.browser import BrowserManager
from scraper.adapt_io.auth import (
    is_authenticated,
    login_to_adapt,
)
from scraper.adapt_io.export import scrape_prospects
from scraper.adapt_io.filters import apply_filters, open_prospect_search

logger = logging.getLogger(__name__)
LEADS_URL = "https://leads.adapt.io/"


def _get_session_file_path(email: str | None = None) -> Path:
    base_dir = getattr(settings, "BASE_DIR", Path("."))
    if email:
        safe_email = email.replace("@", "_at_").replace(".", "_")
        return Path(base_dir) / f"adapt_session_{safe_email}.json"
    return Path(base_dir) / "adapt_session.json"


def _load_session_state(email: str | None = None) -> dict | None:
    session_file = _get_session_file_path(email)
    fallback_file = _get_session_file_path(None)
    
    for path in (session_file, fallback_file):
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Could not load session state from %s: %s", path, e)
    return None


def _save_session_state(state: dict, email: str | None = None) -> None:
    for path in (_get_session_file_path(email), _get_session_file_path(None)):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            logger.info("Saved Adapt.io session state to %s", path)
        except Exception as e:
            logger.warning("Could not save session state to %s: %s", path, e)


def authenticate_with_playwright(
    email: str,
    password: str | None,
    session_state: dict | None,
) -> dict:
    if session_state is None:
        session_state = _load_session_state(email)

    if session_state:
        manager = BrowserManager()
        try:
            manager.start(storage_state=session_state)
            page = manager.new_page()
            if is_authenticated(page):
                return manager.get_storage_state()
        finally:
            manager.close()

    if not password:
        raise ValueError(
            "Adapt.io password is required because the stored session is invalid."
        )

    manager = BrowserManager()
    try:
        manager.start()
        page = manager.new_page()
        login_to_adapt(
            page,
            email=email,
            password=password,
        )
        new_state = manager.get_storage_state()
        _save_session_state(new_state, email)
        return new_state
    finally:
        manager.close()


def scrape_with_playwright(
    email: str,
    password: str,
    filters: dict,
) -> list[dict[str, str]]:
    """Reuse existing saved session if valid; otherwise login once and persist session."""
    manager = BrowserManager()
    session_state = _load_session_state(email)

    try:
        manager.start(storage_state=session_state)
        page = manager.new_page()

        authenticated = False
        if session_state:
            try:
                if is_authenticated(page):
                    authenticated = True
                    logger.info("Reusing existing saved Adapt.io session for %s", email)
            except Exception as e:
                logger.warning("Failed checking saved session: %s", e)
                authenticated = False

        if not authenticated:
            logger.info("No active session found. Logging in to Adapt.io for %s...", email)
            try:
                login_to_adapt(page, email=email, password=password)
            except PlaywrightTimeoutError as exc:
                raise TimeoutError("login timed out") from exc

            if not is_authenticated(page):
                raise ValueError("Adapt.io authentication failed.")

            # Save state for subsequent runs
            new_state = manager.get_storage_state()
            _save_session_state(new_state, email)

        try:
            open_prospect_search(page)
        except PlaywrightTimeoutError as exc:
            raise TimeoutError("opening Prospect Search timed out") from exc

        try:
            apply_filters(page, filters)
        except PlaywrightTimeoutError as exc:
            raise TimeoutError("applying filters or executing search timed out") from exc

        try:
            return scrape_prospects(page)
        except PlaywrightTimeoutError as exc:
            raise TimeoutError("reading search results timed out") from exc

    finally:
        manager.close()