import httpx

from backend.app.market import alltick


def setup_function():
    alltick.reset_rate_limit_state()


def test_kline_second_call_uses_cache(monkeypatch):
    calls = {"n": 0}

    def fake(*_a, **_k):
        calls["n"] += 1
        return [{"ts": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}]

    monkeypatch.setattr(alltick, "fetch_kline", fake)
    s1, b1, _m1 = alltick.safe_fetch_kline("601127", "5m", "tok", "https://example")
    s2, b2, m2 = alltick.safe_fetch_kline("601127", "5m", "tok", "https://example")
    assert s1 == "ok" and s2 == "ok"
    assert calls["n"] == 1
    assert b1 == b2
    assert m2 == "cached"


def test_kline_429_returns_stale_without_token_in_message(monkeypatch):
    bars = [{"ts": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}]
    monkeypatch.setattr(alltick, "fetch_kline", lambda *_a, **_k: bars)
    alltick.safe_fetch_kline("601127", "5m", "tok", "https://example")

    def boom(*_a, **_k):
        req = httpx.Request("GET", "https://example/kline?token=secret-token")
        resp = httpx.Response(429, request=req)
        raise httpx.HTTPStatusError("429", request=req, response=resp)

    monkeypatch.setattr(alltick, "fetch_kline", boom)
    alltick.expire_cache()
    monkeypatch.setattr(alltick, "MIN_INTERVAL_SEC", 0.0)
    alltick._last_http_at = 0.0
    status, out, msg = alltick.safe_fetch_kline("601127", "5m", "tok", "https://example")
    assert status == "ok"
    assert out == bars
    assert "429" in msg
    assert "secret-token" not in msg
    assert "token=" not in msg.lower()


def test_quotes_and_kline_not_both_live_within_interval(monkeypatch):
    kcalls = {"n": 0}
    qcalls = {"n": 0}

    def fake_k(*_a, **_k):
        kcalls["n"] += 1
        return [{"ts": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}]

    def fake_q(symbols, *_a, **_k):
        qcalls["n"] += 1
        return [{"symbol": s, "price": 1.0} for s in symbols]

    monkeypatch.setattr(alltick, "fetch_kline", fake_k)
    monkeypatch.setattr(alltick, "fetch_quotes", fake_q)
    sk, bars, _ = alltick.safe_fetch_kline("601127", "5m", "tok", "https://example")
    sq, quotes, msg = alltick.safe_fetch_quotes(["601127", "600519"], "tok", "https://example")
    assert sk == "ok" and bars
    assert kcalls["n"] == 1
    assert qcalls["n"] == 0
    assert sq == "error"
    assert quotes == []
    assert "限频" in msg


def test_trade_tick_caps_codes_at_five(monkeypatch):
    seen = {"n": None}

    class _Resp:
        status_code = 200
        request = httpx.Request("GET", "https://example/trade-tick")

        def raise_for_status(self):
            return None

        def json(self):
            return {"ret": 200, "data": {"tick_list": []}}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def get(self, url, params):
            import json

            q = json.loads(params["query"])
            seen["n"] = len(q["data"]["symbol_list"])
            assert "token" not in str(q)
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    syms = [f"60000{i}" for i in range(8)]
    out = alltick.fetch_quotes(syms, "tok", "https://example")
    assert seen["n"] == 5
    assert len(out) == 8


def test_kline_json_ret_is_logged_not_bare_runtimeerror(monkeypatch):
    req = httpx.Request("GET", "https://example/kline")
    payload = {"ret": 603, "msg": "token level not enough"}

    class _Resp:
        status_code = 200
        request = req

        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def get(self, url, params):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setattr(alltick, "MIN_INTERVAL_SEC", 0.0)
    status, bars, msg = alltick.safe_fetch_kline("601127", "5m", "tok", "https://example")
    assert status == "error"
    assert bars == []
    assert msg != "RuntimeError"
    assert "603" in msg
    assert "token=" not in msg.lower()
