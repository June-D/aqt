from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.app.core.config import load_yaml_config
from backend.app.domain.models import PositionView


@dataclass
class SizedOrder:
    symbol: str
    side: str  # BUY / SELL
    quantity: int
    reason: str
    sector: str
    confidence: float


def _intel_cfg() -> dict:
    cfg = dict(load_yaml_config().get("intel") or {})
    try:
        from backend.app.core.db import SessionLocal
        from backend.app.models import SystemStateRow

        db = SessionLocal()
        try:
            row = db.get(SystemStateRow, "app_settings")
            if row and isinstance(row.value, dict):
                overlay = row.value.get("intel") or {}
                if isinstance(overlay, dict):
                    cfg.update({k: v for k, v in overlay.items() if v is not None})
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        pass
    return cfg


def plan_orders(
    predictions: list[dict],
    cash: float,
    equity: float,
    positions: list[PositionView],
    prices: dict[str, float],
) -> list[SizedOrder]:
    cfg = _intel_cfg()
    min_conf = float(cfg.get("min_confidence", 0.7))
    max_pos_pct = float(cfg.get("max_position_pct", 0.10))
    max_buy_cash_pct = float(cfg.get("max_buy_cash_pct", 0.15))
    max_holdings = int(cfg.get("max_holdings", 10))
    max_new = int(cfg.get("max_new_buys_per_run", 3))
    max_per_sector = int(cfg.get("max_per_sector", 3))
    sell_mode = str(cfg.get("sell_mode") or "all").lower()
    sell_frac = float(cfg.get("sell_fraction_on_down", 0.5))
    allow_auto_sell = bool(cfg.get("allow_auto_sell", True))
    trade_pct = float(cfg.get("trade_pct", 0.1))

    pos_map = {p.symbol: p for p in positions if p.quantity > 0}
    sector_count: dict[str, int] = {}
    for p in predictions:
        sym = p["symbol"]
        if sym in pos_map:
            sec = p.get("sector") or "未知"
            sector_count[sec] = sector_count.get(sec, 0) + 1

    orders: list[SizedOrder] = []
    new_buys = 0
    holdings = len(pos_map)

    ranked = sorted(predictions, key=lambda x: float(x.get("confidence") or 0), reverse=True)
    for pred in ranked:
        conf = float(pred.get("confidence") or 0)
        if conf < min_conf:
            continue
        symbol = pred["symbol"]
        direction = pred["direction"]
        sector = pred.get("sector") or "未知"
        price = float(prices.get(symbol) or 0)
        if price <= 0:
            continue

        if direction == "DOWN" and symbol in pos_map:
            if not allow_auto_sell:
                continue
            held = pos_map[symbol].quantity
            if sell_mode == "pct":
                qty = int(held * sell_frac) // 100 * 100
            else:
                qty = int(held) // 100 * 100
            if qty >= 100:
                orders.append(
                    SizedOrder(
                        symbol=symbol,
                        side="SELL",
                        quantity=qty,
                        reason=f"情报看跌 conf={conf:.2f} {pred.get('reason')}",
                        sector=sector,
                        confidence=conf,
                    )
                )
            continue

        if direction != "UP":
            continue
        if new_buys >= max_new:
            continue
        if symbol not in pos_map and holdings + new_buys >= max_holdings:
            continue
        if sector_count.get(sector, 0) >= max_per_sector and symbol not in pos_map:
            continue

        budget_equity = equity * max_pos_pct
        budget_cash = cash * min(max_buy_cash_pct, trade_pct)
        budget = min(budget_equity, budget_cash)
        if symbol in pos_map:
            current_mv = pos_map[symbol].market_value
            budget = max(0.0, budget_equity - current_mv)
            budget = min(budget, budget_cash)

        qty = int(budget // (price * 100)) * 100
        if qty < 100:
            continue
        cost = qty * price
        if cost > cash:
            qty = int(cash // (price * 100)) * 100
            cost = qty * price
        if qty < 100:
            continue

        orders.append(
            SizedOrder(
                symbol=symbol,
                side="BUY",
                quantity=qty,
                reason=f"情报看涨 conf={conf:.2f} {pred.get('reason')}",
                sector=sector,
                confidence=conf,
            )
        )
        cash -= cost
        new_buys += 1
        sector_count[sector] = sector_count.get(sector, 0) + 1

    return orders
