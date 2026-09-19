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
    try:
        from django.conf import settings
        base_dir = Path(settings.BASE_DIR)
    except Exception:
        base_dir = Path(".")
    if email:
        safe_email = email.replace("@", "_at_").replace(".", "_")
        return base_dir / f"adapt_session_{safe_email}.json"
    return base_dir / "adapt_session.json"


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


def _delete_session_state(email: str | None = None) -> None:
    paths = {_get_session_file_path(email), _get_session_file_path(None)}
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
                logger.info("Deleted invalid Adapt.io session state from %s", path)
        except Exception as e:
            logger.warning("Could not delete Adapt.io session state from %s: %s", path, e)


def _should_clear_session(exc: Exception) -> bool:
    error_text = str(exc).lower()
    return any(
        marker in error_text
        for marker in (
            "targetclosederror",
            "target page, context or browser has been closed",
            "err_tunnel_connection_failed",
        )
    )


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
                new_state = manager.get_storage_state()
                _save_session_state(new_state, email)
                return new_state
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
    log_callback=None,
) -> list[dict[str, str]]:
    """Reuse existing saved session if valid; otherwise login once and persist session."""
    def emit_log(message: str, step: str = None, progress: int = None):
        print(f"[ADAPT] [{step or 'INFO'}] {message}", flush=True)
        if log_callback:
            try:
                log_callback(message, step=step, progress=progress)
            except Exception:
                pass
        logger.info(message)

    emit_log("Initializing browser environment for Adapt.io...", step="STARTING_BROWSER", progress=8)
    manager = BrowserManager()
    session_state = _load_session_state(email)

    try:
        authenticated = False
        if session_state:
            emit_log("Found saved Adapt.io session. Verifying validity...", step="VERIFYING_SESSION", progress=12)
            manager.start(storage_state=session_state)
            page = manager.new_page()
            try:
                if is_authenticated(page):
                    authenticated = True
                    emit_log("Saved session verified! Reusing session (login bypassed).", step="SESSION_REUSED", progress=20)
                    try:
                        _save_session_state(manager.get_storage_state(), email)
                    except Exception:
                        pass
                else:
                    emit_log("Saved session has expired. Will log in with credentials...", step="SESSION_EXPIRED", progress=15)
            except Exception as e:
                emit_log(f"Session validation encountered issue ({e}). Proceeding to login...", step="SESSION_CHECK_FAILED", progress=15)
                authenticated = False
        else:
            emit_log("No saved session found. Starting new browser session for login...", step="LOGIN_REQUIRED", progress=12)
            manager.start()
            page = manager.new_page()

        if not authenticated:
            if not password:
                raise ValueError("Adapt.io password is required because no valid saved session is available.")
            emit_log(f"Logging in to Adapt.io for {email}...", step="LOGGING_IN", progress=20)
            try:
                login_to_adapt(page, email=email, password=password)
            except PlaywrightTimeoutError as exc:
                raise TimeoutError("Adapt.io login timed out") from exc

            emit_log("Login succeeded! Saving session state for future runs...", step="SAVING_SESSION", progress=30)
            new_state = manager.get_storage_state()
            _save_session_state(new_state, email)

        emit_log("Navigating to Prospect Search...", step="OPENING_SEARCH", progress=35)
        try:
            open_prospect_search(page)
        except PlaywrightTimeoutError as exc:
            raise TimeoutError("Opening Prospect Search timed out") from exc

        emit_log("Applying search filters on Adapt.io...", step="APPLYING_FILTERS", progress=45)
        try:
            apply_filters(page, filters, log_callback=lambda msg: emit_log(msg, step="APPLYING_FILTERS"))
        except PlaywrightTimeoutError as exc:
            raise TimeoutError("Applying filters or executing search timed out") from exc

        emit_log("Scraping prospect leads from search results...", step="SCRAPING_RESULTS", progress=55)
        try:
            rows = scrape_prospects(page, log_callback=lambda msg: emit_log(msg, step="SCRAPING_RESULTS"))
            emit_log(f"Successfully scraped {len(rows)} raw prospects from Adapt.io.", step="SCRAPING_COMPLETED", progress=75)
            try:
                _save_session_state(manager.get_storage_state(), email)
            except Exception:
                pass
            return rows
        except PlaywrightTimeoutError as exc:
            raise TimeoutError("Reading search results timed out") from exc

    except Exception as exc:
        if _should_clear_session(exc):
            emit_log(
                "Adapt.io browser/proxy session failed. Clearing saved session for the next attempt...",
                step="SESSION_RESET",
            )
            _delete_session_state(email)
        raise
    finally:
        manager.close()