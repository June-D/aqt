from pathlib import Path

from backend.app.core.config import ROOT_DIR, get_settings


def test_pytest_does_not_use_workspace_trade_db():
    """pytest 不得写入 data/trade.db，避免覆盖用户 AllTick token。"""
    url = get_settings().database_url
    raw = url.replace("sqlite:///", "", 1)
    used = Path(raw).resolve()
    prod = (ROOT_DIR / "data" / "trade.db").resolve()
    assert used != prod, f"tests pointed at workspace db: {url}"
