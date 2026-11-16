from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings, load_yaml_config
from backend.app.core.money import round_money, round_price
from backend.app.domain.models import (
    AccountSnapshot,
    OrderRequest,
    OrderStatus,
    PositionView,
    Side,
    SubmitResult,
)
from backend.app.gateway.base import Gateway
from backend.app.models import AccountSnapshotRow, FillRow, OrderRow, PositionRow


class SimGateway(Gateway):
    name = "sim"

    def __init__(self, db: Session, price_lookup) -> None:
        self.db = db
        self.price_lookup = price_lookup
        self._ensure_account()

    def _ensure_account(self) -> None:
        row = (
            self.db.query(AccountSnapshotRow)
            .order_by(AccountSnapshotRow.id.desc())
            .first()
        )
        if row is None:
            cash = get_settings().initial_cash
            snap = AccountSnapshotRow(
                cash=cash,
                market_value=0.0,
                total_equity=cash,
                daily_pnl=0.0,
            )
            self.db.add(snap)
            self.db.commit()

    def _fees(self, side: Side, notional: float) -> tuple[float, float]:
        cfg = load_yaml_config().get("fees", {})
        commission = max(float(cfg.get("min_commission", 5.0)), notional * float(cfg.get("commission_rate", 0.0003)))
        stamp = notional * float(cfg.get("stamp_tax_rate", 0.001)) if side == Side.SELL else 0.0
        return commission, stamp

    def _cash(self) -> float:
        row = (
            self.db.query(AccountSnapshotRow)
            .order_by(AccountSnapshotRow.id.desc())
            .first()
        )
        return float(row.cash) if row else get_settings().initial_cash

    def _save_snapshot(self, cash: float, daily_pnl: float = 0.0) -> AccountSnapshot:
        positions = self.query_positions()
        market_value = sum(p.market_value for p in positions)
        snap = AccountSnapshotRow(
            cash=cash,
            market_value=market_value,
            total_equity=cash + market_value,
            daily_pnl=daily_pnl,
        )
        self.db.add(snap)
        self.db.commit()
        return AccountSnapshot(
            cash=cash,
            market_value=market_value,
            total_equity=cash + market_value,
            daily_pnl=daily_pnl,
        )

    def submit_order(self, req: OrderRequest) -> SubmitResult:
        order_id = str(uuid.uuid4())
        price = req.price if req.price is not None else float(self.price_lookup(req.symbol))
        cfg = load_yaml_config().get("fees", {})
        slip = float(cfg.get("slippage_bps", 5)) / 10000.0
        if req.side == Side.BUY:
            price *= 1 + slip
        else:
            price *= 1 - slip
        price = round_price(price)

        order = OrderRow(
            id=order_id,
            strategy_id=req.strategy_id,
            symbol=req.symbol,
            side=req.side.value,
            quantity=req.quantity,
            price=price,
            status=OrderStatus.SUBMITTED.value,
            reason=req.reason,
            gateway=self.name,
        )
        self.db.add(order)
        self.db.flush()

        notional = price * req.quantity
        commission, stamp = self._fees(req.side, notional)
        cash = self._cash()

        if req.side == Side.BUY:
            cost = notional + commission
            if cost > cash:
                order.status = OrderStatus.REJECTED.value
                order.message = f"insufficient cash: need {cost:.2f}, have {cash:.2f}"
                self.db.commit()
                return SubmitResult(
                    success=False,
                    order_id=order_id,
                    status=OrderStatus.REJECTED,
                    message=order.message,
                )
            pos = self.db.get(PositionRow, req.symbol)
            if pos is None:
                pos = PositionRow(symbol=req.symbol, quantity=0, avg_cost=0.0)
                self.db.add(pos)
            new_qty = pos.quantity + req.quantity
            pos.avg_cost = round_price(
                (pos.avg_cost * pos.quantity + price * req.quantity) / new_qty if new_qty else 0.0
            )
            pos.quantity = new_qty
            cash -= cost
        else:
            pos = self.db.get(PositionRow, req.symbol)
            if pos is None or pos.quantity < req.quantity:
                order.status = OrderStatus.REJECTED.value
                order.message = "insufficient position"
                self.db.commit()
                return SubmitResult(
                    success=False,
                    order_id=order_id,
                    status=OrderStatus.REJECTED,
                    message=order.message,
                )
            pos.quantity -= req.quantity
            if pos.quantity == 0:
                pos.avg_cost = 0.0
            cash += notional - commission - stamp

        fill = FillRow(
            order_id=order_id,
            symbol=req.symbol,
            side=req.side.value,
            quantity=req.quantity,
            price=price,
            commission=commission,
            stamp_tax=stamp,
        )
        self.db.add(fill)
        order.status = OrderStatus.FILLED.value
        order.filled_quantity = req.quantity
        order.filled_price = price
        order.message = "filled"
        self.db.commit()
        self._save_snapshot(cash)

        return SubmitResult(
            success=True,
            order_id=order_id,
            status=OrderStatus.FILLED,
            message="filled",
            filled_price=price,
            filled_quantity=req.quantity,
        )

    def cancel_order(self, order_id: str) -> SubmitResult:
        order = self.db.get(OrderRow, order_id)
        if order is None:
            return SubmitResult(success=False, message="order not found")
        if order.status in {OrderStatus.FILLED.value, OrderStatus.CANCELLED.value}:
            return SubmitResult(
                success=False,
                order_id=order_id,
                status=OrderStatus(order.status),
                message="cannot cancel",
            )
        order.status = OrderStatus.CANCELLED.value
        order.updated_at = datetime.utcnow()
        self.db.commit()
        return SubmitResult(
            success=True,
            order_id=order_id,
            status=OrderStatus.CANCELLED,
            message="cancelled",
        )

    def query_positions(self) -> list[PositionView]:
        rows = self.db.query(PositionRow).filter(PositionRow.quantity > 0).all()
        result: list[PositionView] = []
        for r in rows:
            px = float(self.price_lookup(r.symbol) or r.avg_cost)
            px = round_price(px)
            result.append(
                PositionView(
                    symbol=r.symbol,
                    quantity=r.quantity,
                    avg_cost=round_price(r.avg_cost),
                    market_price=px,
                    market_value=round_money(px * r.quantity),
                )
            )
        return result

    def query_account(self) -> AccountSnapshot:
        positions = self.query_positions()
        market_value = sum(p.market_value for p in positions)
        cash = self._cash()
        last = (
            self.db.query(AccountSnapshotRow)
            .order_by(AccountSnapshotRow.id.desc())
            .first()
        )
        daily_pnl = float(last.daily_pnl) if last else 0.0
        return AccountSnapshot(
            cash=cash,
            market_value=market_value,
            total_equity=cash + market_value,
            daily_pnl=daily_pnl,
        )