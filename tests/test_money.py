from backend.app.core.money import round_price


def test_round_price_two_decimals():
    assert round_price(27.213599999999996) == 27.21
    assert round_price(101.86090499999999) == 101.86
    assert round_price(27.2 * 1.0005) == 27.21
