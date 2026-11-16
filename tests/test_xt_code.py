from agent.xt_adapter import to_xt_code


def test_to_xt_code():
    assert to_xt_code("600519") == "600519.SH"
    assert to_xt_code("000001") == "000001.SZ"
    assert to_xt_code("300750.SZ") == "300750.SZ"
