import logging
import time
from pathlib import Path
from scraper.browser import BrowserManager

logger = logging.getLogger(__name__)

LOGIN_URL = "https://www.adapt.io/login.htm?slc=web&login=tru"
LEADS_URL = "https://leads.adapt.io/"


def login_to_adapt(
    page,
    email: str,
    password: str,
) -> None:
    page.goto(
        LOGIN_URL,
        wait_until="domcontentloaded",
    )

    sign_in_link = page.locator(
        'a[data-ng-click="showSigninPopup();"]'
    )

    sign_in_link.click()

    page.locator(
        'input[name="emailSignIn"]'
    ).fill(email)

    page.locator(
        'input[name="passwordSignin"]'
    ).fill(password)

    page.locator(
        'button[data-ng-click="signInUser()"]'
    ).click()

    page.wait_for_url(
        lambda url: url.startswith(LEADS_URL.rstrip("/")),
        timeout=60_000,
    )

    # Wait for dashboard components to initialize and cookies to settle
    try:
        page.wait_for_selector(
            'text="Prospect Search"',
            timeout=10_000,
        )
    except Exception:
        page.wait_for_timeout(3000)


def is_authenticated(page) -> bool:
    """
    Checks whether the page/session is currently authenticated with Adapt.io.
    Avoids false positives by checking for redirection to login or presence of
    authenticated dashboard/search components.
    """
    try:
        current_url = page.url.lower()
        if not current_url.startswith("https://leads.adapt.io") or "login" in current_url:
            try:
                page.goto(
                    "https://leads.adapt.io/dashboard",
                    wait_until="commit",
                    timeout=15_000,
                )
            except Exception:
                page.goto(
                    "https://leads.adapt.io/",
                    wait_until="commit",
                    timeout=15_000,
                )

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            url = page.url.lower()
            if "login" in url:
                return False

            # Check if logged-in elements or navigation are visible
            try:
                if (
                    page.locator('text="Prospect Search"').first.is_visible()
                    or page.locator('text="Dashboard"').first.is_visible()
                    or page.locator('a[href*="advanced-search"]').first.is_visible()
                ):
                    return True
            except Exception:
                pass

            page.wait_for_timeout(500)

        final_url = page.url.lower()
        if "login" in final_url:
            return False

        return False
    except Exception as exc:
        logger.warning("Session authentication check encountered error: %s", exc)
        return False


def inspect_login_page() -> None:
    manager = BrowserManager()

    try:
        manager.start()

        page = manager.new_page()

        page.goto(
            LOGIN_URL,
            wait_until="domcontentloaded",
        )

        page.wait_for_timeout(3000)

        html = page.locator("body").inner_html()

        Path("adapt_login.html").write_text(
            html,
            encoding="utf-8",
        )

        print("Saved rendered HTML to adapt_login.html")
        print("Body text:")
        print(page.locator("body").inner_text())

    finally:
        manager.close()


def get_session_state(manager: BrowserManager) -> dict:
    return manager.get_storage_state()