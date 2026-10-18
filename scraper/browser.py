from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)
import os
import base64
from pathlib import Path
from urllib import request
from urllib.parse import urlparse


class BrowserManager:
    def __init__(self):
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.active_proxy: dict | None = None

    @staticmethod
    def _proxy_file_path() -> Path:
        return Path(__file__).resolve().parent.parent / "proxies.txt"

    @staticmethod
    def _normalize_proxy(server: str, username: str | None = None, password: str | None = None, bypass: str | None = None) -> dict | None:
        if not server:
            return None

        candidate = server.strip()
        if not candidate:
            return None

        parsed = urlparse(candidate if "://" in candidate else f"http://{candidate}")
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return None

        proxy = {"server": f"{parsed.scheme}://{host}:{port}"}
        if username:
            proxy["username"] = username
        if password:
            proxy["password"] = password
        if bypass:
            proxy["bypass"] = bypass
        return proxy

    @staticmethod
    def _proxy_candidates() -> list[dict]:
        candidates: list[dict] = []
        seen: set[str] = set()

        proxy_enabled = os.getenv("WEBSHARE_PROXY_ENABLED", "false").lower() == "true"
        bypass = os.getenv("WEBSHARE_PROXY_BYPASS", "").strip()
        env_server = os.getenv("WEBSHARE_PROXY_SERVER", "").strip()
        if env_server:
            env_proxy = BrowserManager._normalize_proxy(
                env_server,
                os.getenv("WEBSHARE_PROXY_USERNAME", "").strip() or None,
                os.getenv("WEBSHARE_PROXY_PASSWORD", "").strip() or None,
                bypass or None,
            )
            if env_proxy:
                key = env_proxy["server"]
                candidates.append(env_proxy)
                seen.add(key)

        proxy_file = BrowserManager._proxy_file_path()
        if proxy_file.exists() and (proxy_enabled or env_server or proxy_file.exists()):
            with proxy_file.open("r", encoding="utf-8", errors="ignore") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split(":")
                    if len(parts) < 2:
                        continue

                    host = parts[0]
                    port = parts[1]
                    username = None
                    password = None

                    if len(parts) >= 4:
                        username = parts[2]
                        password = ":".join(parts[3:])
                    elif len(parts) == 3:
                        username = parts[2]

                    file_proxy = BrowserManager._normalize_proxy(
                        f"http://{host}:{port}",
                        username,
                        password,
                    )
                    if not file_proxy:
                        continue

                    key = file_proxy["server"]
                    if key in seen:
                        continue
                    candidates.append(file_proxy)
                    seen.add(key)

        return candidates

    @staticmethod
    def _probe_proxy(proxy: dict, target_url: str = "https://www.adapt.io/login.htm?slc=web&login=true") -> bool:
        server = proxy.get("server")
        if not server:
            return False

        username = proxy.get("username")
        password = proxy.get("password")
        proxy_url = server

        try:
            proxy_handler = request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            opener = request.build_opener(proxy_handler)
            if username and password:
                auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
                opener.addheaders = [("Proxy-Authorization", f"Basic {auth}")]

            req = request.Request(
                target_url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with opener.open(req, timeout=15) as response:
                status = getattr(response, "status", 200)
                body = ""
                try:
                    body = response.read().decode("utf-8", errors="ignore").lower()
                except Exception:
                    body = ""

                blocked_markers = (
                    "403 forbidden",
                    "forbidden",
                    "nginx",
                    "access denied",
                    "blocked",
                    "too many requests",
                )
                if status >= 400 or any(marker in body for marker in blocked_markers):
                    return False
                return 200 <= status < 400
        except Exception:
            return False

    @classmethod
    def _proxy_settings(cls) -> dict | None:
        proxy_enabled = os.getenv("WEBSHARE_PROXY_ENABLED", "false").lower() == "true"
        if not proxy_enabled and not cls._proxy_file_path().exists():
            return None

        for candidate in cls._proxy_candidates():
            if cls._probe_proxy(candidate):
                return candidate
        return None

    def start(self, storage_state: dict | None = None) -> None:
        self.playwright = sync_playwright().start()

        launch_options = {
            "headless": os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true",
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--start-maximized",
                f"--force-device-scale-factor={os.getenv('PLAYWRIGHT_SCALE_FACTOR', '0.8')}",
            ],
        }
        proxy = self._proxy_settings()
        if proxy:
            self.active_proxy = proxy
            launch_options["proxy"] = proxy

        self.browser = self.playwright.chromium.launch(
            **launch_options,
        )

        context_options = {
            "ignore_https_errors": True,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "viewport": {
                "width": int(os.getenv("PLAYWRIGHT_VIEWPORT_WIDTH", "1920")),
                "height": int(os.getenv("PLAYWRIGHT_VIEWPORT_HEIGHT", "1080")),
            },
        }

        if storage_state is not None:
            context_options["storage_state"] = storage_state

        self.context = self.browser.new_context(
            **context_options,
        )

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