from pathlib import Path
from scraper.browser import BrowserManager

LOGIN_URL = "https://www.adapt.io/login.htm"
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


def is_authenticated(page) -> bool:
    try:
        page.goto(
            LEADS_URL,
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        page.wait_for_timeout(2000)
        url = page.url.lower()
        return url.startswith("https://leads.adapt.io") and "login" not in url
    except Exception:
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