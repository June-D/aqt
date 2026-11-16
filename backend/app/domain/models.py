from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Bar(BaseModel):
    symbol: str
    dt: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class Signal(BaseModel):
    symbol: str
    side: Side
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = ""
    trade_pct: Optional[float] = None


class OrderRequest(BaseModel):
    symbol: str
    side: Side
    quantity: int
    price: Optional[float] = None
    strategy_id: Optional[str] = None
    reason: str = ""


class AccountSnapshot(BaseModel):
    cash: float
    market_value: float
    total_equity: float
    daily_pnl: float = 0.0


class PositionView(BaseModel):
    symbol: str
    quantity: int
    avg_cost: float
    market_price: float = 0.0
    market_value: float = 0.0


class SubmitResult(BaseModel):
    success: bool
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.REJECTED
    message: str = ""
    filled_price: Optional[float] = None
    filled_quantity: int = 0


class EquityPoint(BaseModel):
    date: date
    equity: float


class BacktestMetrics(BaseModel):
    total_return: float
    max_drawdown: float
    win_rate: float
    trade_count: int
    sharpe: float
    final_equity: float
    equity_curve: list[EquityPoint] = Field(default_factory=list)


class SystemStatus(BaseModel):
    gateway_type: str
    live_trading_enabled: bool
    initial_cash: float
    as_of: datetime