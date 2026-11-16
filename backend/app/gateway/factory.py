from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.data.market_data import market_data
from backend.app.gateway.base import Gateway
from backend.app.gateway.remote_xtquant import RemoteXtQuantGateway
from backend.app.gateway.sim import SimGateway


def build_gateway(db: Session) -> Gateway:
    # 交易模式优先读设置中的 SIM/LIVE；LIVE 走 QMT，SIM 走真行情模拟撮合
    mode = "sim"
    try:
        from backend.app.services.settings_service import get_trading_mode

        mode = get_trading_mode(db)
    except Exception:  # noqa: BLE001
        mode = "sim" if get_settings().gateway_type == "sim" else "live"

    if mode == "live":
        return RemoteXtQuantGateway()
    return SimGateway(db, price_lookup=market_data.latest_price)
