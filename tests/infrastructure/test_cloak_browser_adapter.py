import pytest

from updater.infrastructure.browser.cloak import BrowserLaunchError, CloakBrowserAdapter


def test_cloak_browser_adapter_requires_dependencies(monkeypatch):
    def fake_import(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("updater.infrastructure.browser.cloak.import_module", fake_import)

    adapter = CloakBrowserAdapter()

    with pytest.raises(BrowserLaunchError, match="playwright"):
        adapter.fetch_element_html("https://vendor.example/page", "firmware")


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
