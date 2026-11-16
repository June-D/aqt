"""A 股价格/金额展示精度：最小变动单位 0.01 元。"""

from __future__ import annotations


def round_price(value: float | int | None) -> float:
    if value is None:
        return 0.0
    return round(float(value) + 1e-9, 2)


def round_money(value: float | int | None) -> float:
    return round_price(value)
