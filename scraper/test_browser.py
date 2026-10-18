from unittest.mock import patch

from .browser import BrowserManager


def test_proxy_candidates_fallback_order(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBSHARE_PROXY_ENABLED", "true")
    monkeypatch.setenv("WEBSHARE_PROXY_SERVER", "http://blocked-proxy:8080")
    monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", "user")
    monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", "pass")

    proxies_file = tmp_path / "proxies.txt"
    proxies_file.write_text(
        "1.1.1.1:80:alice:pw\n"
        "2.2.2.2:81:bob:pw2\n",
        encoding="utf-8",
    )

    with patch.object(BrowserManager, "_proxy_file_path", return_value=proxies_file):
        candidates = BrowserManager._proxy_candidates()

    assert candidates[0]["server"] == "http://blocked-proxy:8080"
    assert candidates[0]["username"] == "user"
    assert candidates[1]["server"] == "http://1.1.1.1:80"
    assert candidates[1]["username"] == "alice"
    assert candidates[2]["server"] == "http://2.2.2.2:81"
    assert candidates[2]["username"] == "bob"


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