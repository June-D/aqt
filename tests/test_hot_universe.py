from backend.app.services.hot_universe import _codes_from_df, _norm_code, _rows_from_df, effective_whitelist, merge_hot_entries


def test_norm_code():
    assert _norm_code("SH600519") == "600519"
    assert _norm_code("000001.SZ") == "000001"
    assert _norm_code("bad") is None


def test_codes_from_df():
    import pandas as pd

    df = pd.DataFrame({"排名": [1, 2], "代码": ["600519", "000001"], "名称": ["茅台", "平安"]})
    assert _codes_from_df(df, 10) == ["600519", "000001"]


def test_rows_from_df_keeps_name_and_industry():
    import pandas as pd

    df = pd.DataFrame(
        {
            "排名": [1, 2],
            "代码": ["600519", "000001"],
            "名称": ["贵州茅台", "平安银行"],
            "行业": ["白酒", "银行"],
        }
    )
    rows = _rows_from_df(df, 10)
    assert rows == [
        {"symbol": "600519", "name": "贵州茅台", "industry": "白酒"},
        {"symbol": "000001", "name": "平安银行", "industry": "银行"},
    ]


def test_merge_hot_entries_prefers_first_seen_keeps_later_name():
    a = [{"symbol": "600519", "name": "茅台", "industry": ""}]
    b = [{"symbol": "600519", "name": "贵州茅台", "industry": "白酒"}, {"symbol": "000001", "name": "平安", "industry": ""}]
    merged = merge_hot_entries(a, b, limit=10)
    assert [r["symbol"] for r in merged] == ["600519", "000001"]
    assert merged[0]["name"] == "茅台"
    assert merged[0]["industry"] == "白酒"


def test_effective_whitelist_merge(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.hot_universe.load_yaml_config",
        lambda: {
            "risk": {"whitelist": ["600519"], "blacklist": ["000001"]},
            "intel": {
                "hot_pool": {
                    "enabled": True,
                    "mode": "merge",
                    "extra_symbols": ["300750"],
                    "blacklist": [],
                }
            },
        },
    )
    monkeypatch.setattr(
        "backend.app.services.hot_universe.load_hot_pool",
        lambda db: ["000001", "601318"],
    )
    # 000001 在 risk 黑名单 → 剔除；其余合并
    assert effective_whitelist(db=object()) == ["601318", "600519", "300750"]
