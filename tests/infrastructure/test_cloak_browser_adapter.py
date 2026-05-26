import pytest

from updater.infrastructure.browser.cloak import BrowserLaunchError, CloakBrowserAdapter


def test_cloak_browser_adapter_requires_dependencies(monkeypatch):
    def fake_import(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("updater.infrastructure.browser.cloak.import_module", fake_import)

    adapter = CloakBrowserAdapter()

    with pytest.raises(BrowserLaunchError, match="playwright"):
        adapter.fetch_element_html("https://vendor.example/page", "firmware")


def test_cloak_browser_adapter_uses_domcontentloaded_before_reading_element(monkeypatch):
    calls = []

    class FakeFirstLocator:
        def inner_html(self, timeout):
            return "firmware html"

    class FakeLocator:
        first = FakeFirstLocator()

        def count(self):
            return 1

    class FakePage:
        def goto(self, url, wait_until, timeout):
            calls.append((url, wait_until, timeout))

        def locator(self, selector):
            return FakeLocator()

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            pass

    class FakeBrowser:
        def new_context(self, **kwargs):
            return FakeContext()

        def close(self):
            pass

    class FakeChromium:
        def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def stop(self):
            pass

    class FakeSyncPlaywright:
        def start(self):
            return FakePlaywright()

    def fake_import(name):
        class FakeModule:
            @staticmethod
            def sync_playwright():
                return FakeSyncPlaywright()

        return FakeModule()

    monkeypatch.setattr("updater.infrastructure.browser.cloak.import_module", fake_import)

    html = CloakBrowserAdapter(timeout_ms=1234).fetch_element_html("https://vendor.example/page", "firmware")

    assert html == "firmware html"
    assert calls == [("https://vendor.example/page", "domcontentloaded", 1234)]


def test_cloak_browser_adapter_waits_for_element_html_to_settle(monkeypatch):
    calls = []

    class FakeFirstLocator:
        def __init__(self):
            self.values = ["loading", "loading", "firmware html"]

        def inner_html(self, timeout):
            return self.values.pop(0) if self.values else "firmware html"

    class FakeLocator:
        first = FakeFirstLocator()

        def count(self):
            return 1

    class FakePage:
        def goto(self, url, wait_until, timeout):
            pass

        def locator(self, selector):
            return FakeLocator()

        def wait_for_timeout(self, timeout):
            calls.append(timeout)

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            pass

    class FakeBrowser:
        def new_context(self, **kwargs):
            return FakeContext()

        def close(self):
            pass

    class FakeChromium:
        def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def stop(self):
            pass

    class FakeSyncPlaywright:
        def start(self):
            return FakePlaywright()

    def fake_import(name):
        class FakeModule:
            @staticmethod
            def sync_playwright():
                return FakeSyncPlaywright()

        return FakeModule()

    monkeypatch.setattr("updater.infrastructure.browser.cloak.import_module", fake_import)

    html = CloakBrowserAdapter().fetch_element_html("https://vendor.example/page", "firmware")

    assert html == "firmware html"
    assert calls == [500, 500, 500, 500]


def test_cloak_browser_adapter_rejects_missing_element(monkeypatch):
    class FakeLocator:
        def count(self):
            return 0

    class FakePage:
        def goto(self, url, wait_until, timeout):
            self.url = url

        def locator(self, selector):
            self.selector = selector
            return FakeLocator()

    class FakeContext:
        def new_page(self):
            return FakePage()

        def close(self):
            self.closed = True

    class FakeBrowser:
        def new_context(self, **kwargs):
            return FakeContext()

        def close(self):
            self.closed = True

    class FakeChromium:
        def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def stop(self):
            self.stopped = True

    class FakeSyncPlaywright:
        def start(self):
            return FakePlaywright()

    def fake_import(name):
        class FakeModule:
            @staticmethod
            def sync_playwright():
                return FakeSyncPlaywright()

        return FakeModule()

    monkeypatch.setattr("updater.infrastructure.browser.cloak.import_module", fake_import)

    adapter = CloakBrowserAdapter()

    with pytest.raises(BrowserLaunchError, match="Element #firmware not found"):
        adapter.fetch_element_html("https://vendor.example/page", "firmware")
