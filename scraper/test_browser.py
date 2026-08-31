from .browser import BrowserManager


def test_browser():
    manager = BrowserManager()

    try:
        manager.start()

        page = manager.context.new_page()

        page.goto("https://example.com")

        print("Page title:", page.title())
        print("Page URL:", page.url)

    finally:
        manager.close()

if __name__ == "__main__":
    test_browser()