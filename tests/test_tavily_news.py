from backend.app.intel.tavily_news import fetch_tavily_news_for_symbols


def test_fetch_tavily_maps_results(monkeypatch):
    monkeypatch.setattr("backend.app.intel.tavily_news.tavily_configured", lambda: True)
    monkeypatch.setattr(
        "backend.app.intel.tavily_news._tavily_cfg",
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
                "source": "tavily",
                "title": f"{code} 大涨",
                "summary": "demo",
                "url": f"https://example.com/{code}",
                "published_at": None,
                "fingerprint": f"fp-{code}",
            }
        ]

    monkeypatch.setattr("backend.app.intel.tavily_news.search_tavily", fake_search)
    rows = fetch_tavily_news_for_symbols(["600519", "000001"])
    assert len(rows) == 2
    assert rows[0]["title"].startswith("[600519]")
