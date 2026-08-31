from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)
import os
from urllib.parse import urlparse


class BrowserManager:
    def __init__(self):
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None

    def start(self, storage_state: dict | None = None) -> None:
        self.playwright = sync_playwright().start()

        launch_options = {
            "headless": os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true",
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        proxy = self._proxy_settings()
        if proxy:
            launch_options["proxy"] = proxy

        self.browser = self.playwright.chromium.launch(
            **launch_options,
        )

        context_options = {}

        if storage_state is not None:
            context_options["storage_state"] = storage_state

        self.context = self.browser.new_context(
            **context_options,
        )

    @staticmethod
    def _proxy_settings() -> dict | None:
        server = os.getenv("WEBSHARE_PROXY_SERVER")
        username = os.getenv("WEBSHARE_PROXY_USERNAME")
        password = os.getenv("WEBSHARE_PROXY_PASSWORD")

        if not server:
            return None

        parsed = urlparse(server if "://" in server else f"http://{server}")
        proxy = {
            "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
        }
        if username and password:
            proxy.update(
                username=username,
                password=password,
            )
        return proxy

    def new_page(self) -> Page:
        if self.context is None:
            raise RuntimeError("BrowserManager has not been started.")

        return self.context.new_page()

    def get_storage_state(self) -> dict:
        if self.context is None:
            raise RuntimeError("BrowserManager has not been started.")

        return self.context.storage_state()

    def close(self) -> None:
        if self.context:
            self.context.close()

        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()