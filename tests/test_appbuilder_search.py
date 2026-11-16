from backend.app.intel.appbuilder_search import fetch_appbuilder_news_for_symbols, search_appbuilder


def test_fetch_appbuilder_maps_results(monkeypatch):
    monkeypatch.setattr("backend.app.intel.appbuilder_search.appbuilder_configured", lambda: True)
    monkeypatch.setattr(
        "backend.app.intel.appbuilder_search._cfg",
        lambda: {
            "enabled": True,
            "symbols_per_run": 2,
            "query_template": "A股 {symbol} 新闻",
            "include_market_pulse": False,
        },
    )

    def fake_search(query: str):
        code = "600519" if "600519" in query else "000001"
        return [
            {
                "source": "appbuilder",
                "title": f"{code} 大涨",
                "summary": "demo",
                "url": f"https://example.com/{code}",
                "published_at": None,
                "fingerprint": f"fp-{code}",
            }
        ]

    monkeypatch.setattr("backend.app.intel.appbuilder_search.search_appbuilder", fake_search)
    rows = fetch_appbuilder_news_for_symbols(["600519", "000001"])
    assert len(rows) == 2
    assert rows[0]["title"].startswith("[600519]")


class _FakeResp:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "references": [
                {
                    "type": "web",
                    "title": "茅台新闻",
                    "url": "https://example.com/mt",
                    "content": "摘要",
                    "date": "2026-10-02 10:00:00",
                },
                {"type": "image", "title": "图", "url": "https://example.com/img"},
            ]
        }


def test_search_appbuilder_parses_references(monkeypatch):
    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _FakeResp()

    monkeypatch.setattr(
        "backend.app.intel.appbuilder_search.get_settings",
        lambda: type("S", (), {"appbuilder_token": "bce-test"})(),
    )
    monkeypatch.setattr("backend.app.intel.appbuilder_search._cfg", lambda: {})
    monkeypatch.setattr("backend.app.intel.appbuilder_search.httpx.Client", _FakeClient)
    rows = search_appbuilder("A股 600519")
    assert len(rows) == 1
    assert rows[0]["title"] == "茅台新闻"
    assert rows[0]["source"] == "appbuilder"
