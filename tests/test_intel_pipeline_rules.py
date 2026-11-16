"""S9: 盘外只预测不下单；低置信度不下单。"""

from backend.app.core.db import SessionLocal, init_db
from backend.app.domain.models import PositionView
from backend.app.intel.sizing import plan_orders


def setup_module():
    init_db()


def test_low_confidence_does_not_plan_orders(monkeypatch):
    monkeypatch.setattr(
        "backend.app.intel.sizing._intel_cfg",
        lambda: {
            "min_confidence": 0.7,
            "max_new_buys_per_run": 3,
            "max_holdings": 10,
            "max_position_pct": 0.1,
            "max_buy_cash_pct": 0.15,
            "max_per_sector": 3,
            "sell_mode": "all",
            "allow_auto_sell": True,
        },
    )
    preds = [{"symbol": "600519", "direction": "UP", "confidence": 0.65, "sector": "白酒", "reason": "x"}]
    orders = plan_orders(preds, cash=1_000_000, equity=1_000_000, positions=[], prices={"600519": 100})
    assert orders == []


def test_sell_mode_all_sells_full_position(monkeypatch):
    monkeypatch.setattr(
        "backend.app.intel.sizing._intel_cfg",
        lambda: {
            "min_confidence": 0.7,
            "sell_mode": "all",
            "allow_auto_sell": True,
            "sell_fraction_on_down": 0.5,
            "max_new_buys_per_run": 3,
            "max_holdings": 10,
            "max_position_pct": 0.1,
            "max_buy_cash_pct": 0.15,
            "max_per_sector": 3,
        },
    )
    preds = [{"symbol": "600519", "direction": "DOWN", "confidence": 0.9, "sector": "白酒", "reason": "x"}]
    positions = [PositionView(symbol="600519", quantity=1000, avg_cost=10, market_price=12, market_value=12000)]
    orders = plan_orders(preds, cash=100000, equity=112000, positions=positions, prices={"600519": 12})
    assert any(o.side == "SELL" and o.quantity == 1000 for o in orders)


def test_run_intel_skips_orders_outside_session(monkeypatch):
    from backend.app.intel import pipeline as pl
    from backend.app.data.market_data import market_data as md_svc

    calls = {"place": 0}

    class FakeTrading:
        def __init__(self, db, gateway):
            pass

        def place_order(self, req):
            calls["place"] += 1
            from backend.app.domain.models import OrderStatus, SubmitResult

            return SubmitResult(
                success=True,
                order_id="x",
                status=OrderStatus.FILLED,
                message="ok",
                filled_quantity=req.quantity,
            )

    class FakeGW:
        name = "sim"

        def query_account(self):
            from backend.app.domain.models import AccountSnapshot

            return AccountSnapshot(cash=1_000_000, market_value=0, total_equity=1_000_000)

        def query_positions(self):
            return []

    monkeypatch.setattr(pl, "session_open", lambda: False)
    monkeypatch.setattr(pl, "build_gateway", lambda db: FakeGW())
    monkeypatch.setattr(pl, "TradingService", FakeTrading)
    monkeypatch.setattr(pl, "refresh_hot_pool", lambda db: ["600519"])
    monkeypatch.setattr(pl, "effective_whitelist", lambda db: ["600519"])
    monkeypatch.setattr(
        pl,
        "collect_news",
        lambda **kw: [
            {
                "source": "t",
                "title": "热点",
                "summary": "",
                "url": "",
                "published_at": None,
                "fingerprint": "fp-offsession-1",
            }
        ],
    )
    monkeypatch.setattr(
        pl,
        "predict_from_news",
        lambda db, news, focus_symbols=None: [
            {"symbol": "600519", "direction": "UP", "confidence": 0.9, "sector": "白酒", "reason": "r"}
        ],
    )
    monkeypatch.setattr(pl, "intel_enabled", lambda db: True)
    monkeypatch.setattr(md_svc, "latest_price", lambda s: 100.0)

    db = SessionLocal()
    try:
        res = pl.run_intel_cycle(db, force=True)
        assert res.get("ok") is True
        assert calls["place"] == 0
        assert res.get("orders") == []
        assert "盘外" in (res.get("message") or "")
    finally:
        db.close()
