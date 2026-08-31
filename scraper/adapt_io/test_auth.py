import json
import os

from scraper.browser import BrowserManager
from scraper.adapt_io.auth import (
    get_session_state,
    login_to_adapt,
)


def test_login():
    email = os.environ["ADAPT_EMAIL"]
    password = os.environ["ADAPT_PASSWORD"]

    manager = BrowserManager()

    try:
        manager.start()

        page = manager.new_page()

        login_to_adapt(
            page,
            email=email,
            password=password,
        )

        print("Login successful.")
        print("URL:", page.url)
        print("TITLE:", page.title())

        session_state = get_session_state(manager)

        with open(
            "adapt_session.json",
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                session_state,
                file,
                indent=2,
            )

        print("Session state saved.")

    finally:
        manager.close()


if __name__ == "__main__":
    test_login()