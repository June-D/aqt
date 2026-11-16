from datetime import date

from backend.app.core.calendar import _calendar_cfg, is_trading_day


def test_weekend_is_closed():
    assert is_trading_day(date(2026, 10, 3)) is False  # Saturday


def test_weekday_open_unless_holiday():
    cfg = _calendar_cfg()
    holidays = {str(x) for x in (cfg.get("holidays") or [])}
    d = date(2026, 3, 4)  # Wednesday
    if d.isoformat() in holidays:
        assert is_trading_day(d) is False
    else:
        assert is_trading_day(d) is True


def test_national_day_holiday():
    assert is_trading_day(date(2026, 10, 1)) is False
