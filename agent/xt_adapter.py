"""xtquant adapter. On machines without QMT this stays inactive."""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

ACCOUNT_ID = os.getenv("QMT_ACCOUNT_ID", "")
USERDATA = os.getenv("QMT_USERDATA_PATH", "")


def to_xt_code(symbol: str) -> str:
    s = symbol.strip().upper().replace(".SH", "").replace(".SZ", "")
    if s.startswith("6") or s.startswith("9"):
        return f"{s}.SH"
    return f"{s}.SZ"


class XtAdapter:
    def __init__(self) -> None:
        self._trader = None
        self._account = None
        self._lock = threading.Lock()
        self._connected = False
        self._last_error = ""

    def available(self) -> bool:
        try:
            import xtquant  # noqa: F401

            return True
        except Exception:
            return False

    def connect(self) -> dict[str, Any]:
        if not ACCOUNT_ID or not USERDATA:
            self._last_error = "QMT_ACCOUNT_ID / QMT_USERDATA_PATH 未配置"
            return {"ok": False, "error": self._last_error}
        try:
            from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
            from xtquant.xttype import StockAccount
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"xtquant 未安装: {exc}"
            return {"ok": False, "error": self._last_error}

        with self._lock:
            if self._connected and self._trader is not None:
                return {"ok": True, "connected": True}

            session_id = int(time.time()) % 1_000_000
            trader = XtQuantTrader(USERDATA, session_id)
            trader.register_callback(XtQuantTraderCallback())
            trader.start()
            trader.connect()
            account = StockAccount(ACCOUNT_ID)
            trader.subscribe(account)
            self._trader = trader
            self._account = account
            self._connected = True
            self._last_error = ""
            return {"ok": True, "connected": True}

    def health(self) -> dict[str, Any]:
        return {
            "xtquant_imported": self.available(),
            "account_id_configured": bool(ACCOUNT_ID),
            "userdata_configured": bool(USERDATA),
            "connected": self._connected,
            "error": self._last_error or None,
        }

    def place_order(self, symbol: str, side: str, quantity: int, price: Optional[float], remark: str) -> dict[str, Any]:
        info = self.connect()
        if not info.get("ok"):
            return {
                "success": False,
                "order_id": None,
                "status": "REJECTED",
                "message": info.get("error") or "xtquant 未就绪",
                "filled_price": None,
                "filled_quantity": 0,
            }
        from xtquant import xtconstant

        code = to_xt_code(symbol)
        xt_side = xtconstant.STOCK_BUY if side.upper() == "BUY" else xtconstant.STOCK_SELL
        price_type = xtconstant.FIX_PRICE if price else xtconstant.LATEST_PRICE
        px = float(price or 0)
        seq = self._trader.order_stock(
            self._account,
            code,
            xt_side,
            int(quantity),
            price_type,
            px,
            "AQT",
            remark or "",
        )
        ok = seq is not None and seq >= 0
        return {
            "success": ok,
            "order_id": str(seq) if seq is not None else None,
            "status": "SUBMITTED" if ok else "REJECTED",
            "message": "已提交" if ok else f"xtquant 拒绝 seq={seq}",
            "filled_price": None,
            "filled_quantity": 0,
        }

    def cancel(self, order_id: str) -> dict[str, Any]:
        info = self.connect()
        if not info.get("ok"):
            return {"success": False, "order_id": order_id, "status": "REJECTED", "message": info.get("error")}
        try:
            self._trader.cancel_order_stock(self._account, int(order_id))
            return {"success": True, "order_id": order_id, "status": "CANCELLED", "message": "已撤单"}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "order_id": order_id, "status": "REJECTED", "message": str(exc)}

    def positions(self) -> list[dict[str, Any]]:
        info = self.connect()
        if not info.get("ok"):
            return []
        try:
            raw = self._trader.query_stock_positions(self._account) or []
        except Exception:
            return []
        out = []
        for p in raw:
            qty = int(getattr(p, "volume", 0) or 0)
            if qty <= 0:
                continue
            code = str(getattr(p, "stock_code", "")).split(".")[0]
            cost = float(getattr(p, "avg_price", 0) or 0)
            last = float(getattr(p, "last_price", cost) or cost)
            out.append(
                {
                    "symbol": code,
                    "quantity": qty,
                    "avg_cost": cost,
                    "market_price": last,
                    "market_value": last * qty,
                }
            )
        return out

    def account(self) -> dict[str, Any]:
        info = self.connect()
        if not info.get("ok"):
            return {"cash": 0.0, "market_value": 0.0, "total_equity": 0.0, "daily_pnl": 0.0}
        try:
            a = self._trader.query_stock_asset(self._account)
        except Exception:
            return {"cash": 0.0, "market_value": 0.0, "total_equity": 0.0, "daily_pnl": 0.0}
        cash = float(getattr(a, "cash", 0) or 0)
        mv = float(getattr(a, "market_value", 0) or 0)
        eq = float(getattr(a, "total_asset", cash + mv) or (cash + mv))
        pnl = float(getattr(a, "frozen_cash", 0) and 0)
        return {
            "cash": cash,
            "market_value": mv,
            "total_equity": eq,
            "daily_pnl": float(getattr(a, "profit", 0) or 0) or pnl,
        }


xt_adapter = XtAdapter()
