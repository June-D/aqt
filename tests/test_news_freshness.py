from datetime import datetime, timedelta

from backend.app.intel.news_fetch import _parse_time, collect_news


def test_parse_time_unix_and_str():
    assert _parse_time(1727862279).year >= 2024
    assert _parse_time("2026-10-02 08:24:39").day == 2
    assert _parse_time("20261002").month == 10
    assert _parse_time(None) is None


def test_parse_time_naive_china_wall_clock_stored_as_utc():
    """AppBuilder/国内源无时区字符串是北京时间；库内约定 UTC naive，前端再转上海。"""
    got = _parse_time("2026-10-03 11:36:31")
    assert got == datetime(2026, 10, 3, 3, 36, 31)
    assert got.tzinfo is None


def test_parse_time_aware_converted_to_utc_naive():
    assert _parse_time("2026-10-03T05:36:31Z") == datetime(2026, 10, 3, 5, 36, 31)
    assert _parse_time("Fri, 03 Oct 2026 05:36:31 GMT") == datetime(2026, 10, 3, 5, 36, 31)
    assert _parse_time("2026-10-03T13:36:31+08:00") == datetime(2026, 10, 3, 5, 36, 31)


def test_coerce_legacy_china_wall_clock_vs_utc_created_at():
    from backend.app.intel.news_fetch import coerce_stored_published_at

    created = datetime(2026, 10, 3, 5, 50, 0)
    published = datetime(2026, 10, 3, 11, 36, 31)
    assert coerce_stored_published_at(published, created) == datetime(2026, 10, 3, 3, 36, 31)
    already_utc = datetime(2026, 10, 3, 3, 36, 31)
    assert coerce_stored_published_at(already_utc, created) == already_utc


def test_collect_news_filters_stale(monkeypatch):
    fresh = {
        "source": "t",
        "title": "fresh",
        "summary": "",
        "url": "http://a",
        "published_at": datetime.utcnow(),
        "fingerprint": "f1",
    }
    stale = {
        "source": "t",
        "title": "stale",
        "summary": "",
        "url": "http://b",
        "published_at": datetime.utcnow() - timedelta(days=30),
        "fingerprint": "f2",
    }

    monkeypatch.setattr("backend.app.intel.news_fetch.fetch_rss", lambda n, u: [fresh, stale])
    monkeypatch.setattr("backend.app.intel.news_fetch.fetch_http_json", lambda c: [])
    monkeypatch.setattr("backend.app.intel.news_fetch.fetch_akshare_briefs", lambda: [])
    monkeypatch.setattr(
        "backend.app.intel.news_fetch.load_yaml_config",
        lambda: {"intel": {"rss_feeds": [{"name": "x", "url": "u"}], "http_sources": [], "max_age_hours": 48}},
    )
    rows = collect_news(limit=10)
    titles = [r["title"] for r in rows]
    assert titles == ["fresh"]
