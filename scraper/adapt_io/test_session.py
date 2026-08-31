import json

from scraper.browser import BrowserManager


LEADS_URL = "https://leads.adapt.io/"


def test_session():
    with open(
        "adapt_session.json",
        "r",
        encoding="utf-8",
    ) as file:
        session_state = json.load(file)

    manager = BrowserManager()

    try:
        manager.start(
            storage_state=session_state,
        )

        page = manager.new_page()

        page.goto(
            LEADS_URL,
            wait_until="domcontentloaded",
        )

        print("URL:", page.url)
        print("TITLE:", page.title())

        print("\nBODY TEXT:")
        print(page.locator("body").inner_text()[:3000])

    finally:
        manager.close()


if __name__== "__main__":
    test_session()