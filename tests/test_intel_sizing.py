from backend.app.intel.llm_client import normalize_symbol
from backend.app.intel.sizing import plan_orders
from backend.app.domain.models import PositionView


def test_normalize_symbol():
    assert normalize_symbol("600519") == "600519"
    assert normalize_symbol("SH600519") == "600519"
    assert normalize_symbol("bad") is None


def test_plan_orders_diversifies():
    preds = [
        {"symbol": "600519", "direction": "UP", "confidence": 0.9, "sector": "白酒", "reason": "a"},
        {"symbol": "000001", "direction": "UP", "confidence": 0.85, "sector": "银行", "reason": "b"},
        {"symbol": "300750", "direction": "UP", "confidence": 0.8, "sector": "电池", "reason": "c"},
        {"symbol": "601318", "direction": "UP", "confidence": 0.7, "sector": "保险", "reason": "d"},
    ]
    prices = {p["symbol"]: 100.0 for p in preds}
    orders = plan_orders(preds, cash=1_000_000, equity=1_000_000, positions=[], prices=prices)
    buys = [o for o in orders if o.side == "BUY"]
    assert 1 <= len(buys) <= 3
    assert all(o.quantity % 100 == 0 for o in buys)


def test_plan_orders_sells_on_down(monkeypatch):
    monkeypatch.setattr(
        "backend.app.intel.sizing._intel_cfg",
        lambda: {
            "min_confidence": 0.7,
            "sell_mode": "pct",
            "sell_fraction_on_down": 0.5,
            "allow_auto_sell": True,
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
    assert any(o.side == "SELL" and o.quantity == 500 for o in orders)
