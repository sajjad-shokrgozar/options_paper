import pandas as pd

from src.panel import build_panel


def test_no_trade_survives(tmp_path):
    (tmp_path / "options_history.csv").write_text(
        "symbol,id,date,jdate,min,max,yesterday,first,close,last,trades_count,volume,value,title,underlying,strike,maturity\n"
        "c1,1,20250322,14040102,0,0,10,0,10,10,0,0,0,t,اختیارخ اهرم,100,14050101\n",
        encoding="utf-8",
    )
    (tmp_path / "underlying_history.csv").write_text(
        "symbol,id,date,jdate,min,max,yesterday,first,close,last,trades_count,volume,value,ret,cumprod,adj_price\n"
        "اهرم,10,20250321,14040101,100,100,100,100,100,100,1,1,100,1,1,100\n"
        "اهرم,10,20250322,14040102,100,100,100,100,100,100,1,1,100,1,1,100\n",
        encoding="utf-8",
    )
    cfg = {"data_root": tmp_path, "day_count": 365, "ann_factor": 252, "risk_free_default": 0.34,
           "canonical_underlyings": ["اهرم"], "iv_bounds": [0.001, 5], "min_option_price": 1}
    panel, *_ = build_panel(cfg, pd.DataFrame())
    assert len(panel) == 1
    assert bool(panel.iloc[0]["no_trade"]) is True
