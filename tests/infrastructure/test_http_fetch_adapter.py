import pytest

from updater.infrastructure.browser.http_fetch import HttpFetchAdapter, HttpFetchError


class FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            raise RuntimeError(f"HTTP {self._status}")


def _adapter(response, recorder=None):
    def fake_get(url, headers=None, timeout=None):
        if recorder is not None:
            recorder.append({"url": url, "headers": headers, "timeout": timeout})
        return response
    return HttpFetchAdapter(get=fake_get)


def test_fetch_html_returns_whole_body_when_no_selector():
    calls = []
    adapter = _adapter(FakeResponse("<html>0.147.0</html>"), calls)
    assert adapter.fetch_html("https://x") == "<html>0.147.0</html>"
    assert "User-Agent" in calls[0]["headers"]


def test_fetch_html_extracts_selector():
    adapter = _adapter(FakeResponse('<div><span id="v">1.5.9</span></div>'))
    assert "1.5.9" in adapter.fetch_html("https://x", "#v")


def test_fetch_html_raises_when_selector_missing():
    adapter = _adapter(FakeResponse("<div></div>"))
    with pytest.raises(HttpFetchError, match="not found"):
        adapter.fetch_html("https://x", "#missing")


def test_fetch_html_raises_on_http_error():
    adapter = _adapter(FakeResponse("boom", status=503))
    with pytest.raises(HttpFetchError, match="HTTP fetch failed"):
        adapter.fetch_html("https://x")
