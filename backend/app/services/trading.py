from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.domain.models import OrderRequest, OrderStatus, Signal, Side, SubmitResult
from backend.app.gateway.base import Gateway
from backend.app.models import AuditLogRow, OrderRow
from backend.app.risk.gate import RiskGate, RiskReject


class TradingService:
    def __init__(self, db: Session, gateway: Gateway) -> None:
        self.db = db
        self.gateway = gateway
        self.risk = RiskGate(db, gateway)

    def execute_signal(self, signal: Signal, strategy_id: str, price: float) -> SubmitResult:
        account = self.gateway.query_account()
        trade_pct = signal.trade_pct if signal.trade_pct is not None else 0.1

        if signal.side == Side.BUY:
            budget = account.cash * trade_pct
            qty = int(budget // (price * 100)) * 100
        else:
            positions = {p.symbol: p for p in self.gateway.query_positions()}
            pos = positions.get(signal.symbol)
            qty = pos.quantity if pos else 0

        if qty <= 0:
            return SubmitResult(success=False, message="quantity is zero")

        req = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            quantity=qty,
            price=price,
            strategy_id=strategy_id,
            reason=signal.reason,
        )
        return self.place_order(req)

    def place_order(self, req: OrderRequest) -> SubmitResult:
        try:
            ok, msg = self.risk.check(req)
        except RiskReject as exc:
            self._audit("ORDER_REJECTED_RISK", {"request": req.model_dump(mode="json"), "message": exc.message})
            return SubmitResult(success=False, message=exc.message)
        if not ok:
            self._audit("ORDER_REJECTED_RISK", {"request": req.model_dump(mode="json"), "message": msg})
            return SubmitResult(success=False, message=msg)

        result = self.gateway.submit_order(req)
        self._persist_remote_order(req, result)
        self._audit(
            "ORDER_SUBMIT",
            {"request": req.model_dump(mode="json"), "result": result.model_dump(mode="json")},
        )
        return result

    def cancel_order(self, order_id: str) -> SubmitResult:
        result = self.gateway.cancel_order(order_id)
        row = self.db.get(OrderRow, order_id)
        if row is None and result.order_id:
            row = self.db.get(OrderRow, result.order_id)
        if row is not None and result.success:
            row.status = result.status.value if result.status else OrderStatus.CANCELLED.value
            row.message = result.message
            row.updated_at = datetime.utcnow()
            self.db.commit()
        self._audit("ORDER_CANCEL", {"order_id": order_id, "result": result.model_dump(mode="json")})
        return result

    def _persist_remote_order(self, req: OrderRequest, result: SubmitResult) -> None:
        if self.gateway.name == "sim":
            return
        oid = result.order_id or str(uuid.uuid4())
        existing = self.db.get(OrderRow, oid)
        if existing is not None:
            existing.status = result.status.value
            existing.message = result.message
            existing.filled_price = result.filled_price
            existing.filled_quantity = result.filled_quantity
            existing.gateway_order_id = result.order_id
            self.db.commit()
            return
        self.db.add(
            OrderRow(
                id=oid,
                strategy_id=req.strategy_id,
                symbol=req.symbol,
                side=req.side.value,
                quantity=req.quantity,
                price=req.price,
                filled_quantity=result.filled_quantity,
                filled_price=result.filled_price,
                status=result.status.value,
                reason=req.reason,
                message=result.message,
                gateway=self.gateway.name,
                gateway_order_id=result.order_id,
            )
        )
        self.db.commit()

    def _audit(self, action: str, detail: dict) -> None:
        self.db.add(AuditLogRow(action=action, detail=detail))
        self.db.commit()
