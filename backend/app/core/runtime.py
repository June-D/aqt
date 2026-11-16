from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.app.core.config import get_settings


@dataclass
class RuntimeState:
    live_trading_enabled: bool = field(default_factory=lambda: get_settings().live_trading_enabled)
    paper_force_enabled: Optional[bool] = None


runtime_state = RuntimeState()
