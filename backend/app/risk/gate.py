from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.core.calendar import is_trading_day, session_open
from backend.app.core.config import load_yaml_config
from backend.app.core.runtime import runtime_state
from backend.app.data.market_data import market_data, normalize_symbol
from backend.app.domain.models import OrderRequest, Side
from backend.app.gateway.base import Gateway
from backend.app.models import OrderRow
from backend.app.services.risk_alerts import emit_risk_alert


class RiskGate:
    def __init__(self, db: Session, gateway: Gateway) -> None:
        self.db = db
        self.gateway = gateway
        self.cfg = load_yaml_config().get("risk", {})

    def _log(self, event_type: str, message: str, symbol: Optional[str] = None, detail: Optional[dict] = None) -> None:
        emit_risk_alert(
            self.db,
            event_type=event_type,
            message=message,
            symbol=symbol,
            level="warn",
            detail=detail,
            title=event_type,
        )

    def check(self, req: OrderRequest) -> tuple[bool, str]:
        req.symbol = normalize_symbol(req.symbol)

        if self.gateway.name != "sim" and not runtime_state.live_trading_enabled:
            msg = "LIVE 未开启，仅 SIM 网关可交易"
            self._log("LIVE_DISABLED", msg, req.symbol, req.model_dump(mode="json"))
            return False, msg

        if not is_trading_day():
            msg = "今日非交易日"
            self._log("CALENDAR", msg, req.symbol)
            return False, msg

        if not session_open():
            msg = "当前不在交易时段"
            self._log("SESSION", msg, req.symbol)
            return False, msg

        lot = int(self.cfg.get("lot_size", 100))
        if req.quantity <= 0 or req.quantity % lot != 0:
            msg = f"数量必须为 {lot} 的整数倍"
            self._log("LOT_SIZE", msg, req.symbol)
            return False, msg

        blacklist = self.cfg.get("blacklist") or []
        from backend.app.services.hot_universe import effective_whitelist

        whitelist = effective_whitelist(self.db)
        # 热点池黑名单并入 yaml blacklist
        hot_bl = ((load_yaml_config().get("intel") or {}).get("hot_pool") or {}).get("blacklist") or []
        blacklist = list({*blacklist, *hot_bl})
        if req.symbol in blacklist:
            msg = f"{req.symbol} 在黑名单中"
            self._log("BLACKLIST", msg, req.symbol)
            return False, msg
        if whitelist and req.symbol not in whitelist:
            msg = f"{req.symbol} 不在白名单"
            self._log("WHITELIST", msg, req.symbol)
            return False, msg

        min_interval = int(self.cfg.get("min_trade_interval_seconds", 60))
        since = datetime.utcnow() - timedelta(seconds=min_interval)
        recent = (
            self.db.query(OrderRow)
            .filter(OrderRow.symbol == req.symbol, OrderRow.created_at >= since)
            .filter(OrderRow.status.in_(["SUBMITTED", "FILLED", "PARTIAL"]))
            .first()
        )
        if recent:
            msg = f"{req.symbol} 未满足最小交易间隔 {min_interval} 秒"
            self._log("MIN_INTERVAL", msg, req.symbol)
            return False, msg

        account = self.gateway.query_account()
        max_daily_loss = float(self.cfg.get("max_daily_loss_pct", 0.05))
        if account.total_equity > 0 and account.daily_pnl < 0:
            loss_pct = abs(account.daily_pnl) / account.total_equity
            if loss_pct >= max_daily_loss:
                msg = f"触发日亏损熔断（{loss_pct:.2%}）"
                self._log("DAILY_LOSS", msg, req.symbol)
                return False, msg

        price = req.price or 0.0
        if price <= 0:
            price = float(market_data.latest_price(req.symbol) or 0.0)
            req.price = price or req.price

        self._board_checks(req, price)

        if price <= 0:
            return True, "ok"

        if req.side == Side.BUY:
            notional = price * req.quantity
            min_comm = float(load_yaml_config().get("fees", {}).get("min_commission", 5.0))
            need = notional + min_comm
            if need > account.cash:
                msg = f"可用资金不足：需要 {need:.2f}，现金 {account.cash:.2f}"
                self._log("CASH", msg, req.symbol)
                return False, msg

            max_pos = float(self.cfg.get("max_position_pct", 0.2))
            max_total = float(self.cfg.get("max_total_position_pct", 0.95))
            if account.total_equity > 0 and notional / account.total_equity > max_pos:
                msg = f"单票仓位上限 {max_pos:.0%} 已超出"
                self._log("MAX_POSITION", msg, req.symbol, {"notional": notional})
                return False, msg
            projected = account.market_value + notional
            if account.total_equity > 0 and projected / account.total_equity > max_total:
                msg = f"总仓位上限 {max_total:.0%} 已超出"
                self._log("MAX_TOTAL_POSITION", msg, req.symbol)
                return False, msg

            if req.strategy_id:
                max_strat = float(self.cfg.get("max_strategy_position_pct", 0.5))
                used = self._strategy_notional(req.strategy_id)
                if account.total_equity > 0 and (used + notional) / account.total_equity > max_strat:
                    msg = f"策略仓位上限 {max_strat:.0%} 已超出"
                    self._log("MAX_STRATEGY_POSITION", msg, req.symbol)
                    return False, msg

        return True, "ok"

    def _strategy_notional(self, strategy_id: str) -> float:
        rows = (
            self.db.query(OrderRow)
            .filter(OrderRow.strategy_id == strategy_id, OrderRow.status.in_(["FILLED", "PARTIAL"]))
            .all()
        )
        total = 0.0
        for r in rows:
            px = float(r.filled_price or r.price or 0)
            qty = int(r.filled_quantity or 0)
            if r.side == "BUY":
                total += px * qty
            else:
                total -= px * qty
        return max(total, 0.0)

    def _board_checks(self, req: OrderRequest, price: float) -> None:
        bars = market_data.fetch_daily(req.symbol)
        if len(bars) < 2:
            return
        last, prev = bars[-1], bars[-2]
        if last.volume <= 0 and last.high == last.low:
            msg = f"{req.symbol} 疑似停牌"
            self._log("HALT", msg, req.symbol)
            raise RiskReject(msg)
        prev_close = prev.close or 0
        if prev_close <= 0:
            return
        chg = (last.close - prev_close) / prev_close
        limit_pct = 0.095
        if req.side == Side.BUY and chg >= limit_pct and last.close >= last.high * 0.999:
            msg = f"{req.symbol} 疑似涨停，禁止买入"
            self._log("LIMIT_UP", msg, req.symbol)
            raise RiskReject(msg)
        if req.side == Side.SELL and chg <= -limit_pct and last.close <= last.low * 1.001:
            msg = f"{req.symbol} 疑似跌停，禁止卖出"
            self._log("LIMIT_DOWN", msg, req.symbol)
            raise RiskReject(msg)


class RiskReject(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
