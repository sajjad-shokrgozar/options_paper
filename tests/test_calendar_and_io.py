from pathlib import Path
import pandas as pd
import pytest

from src.calendar import jalali_int_to_gregorian
from src.io_load import parse_underlying_label, discover_lob_files, load_lob_day_file
from src.lob import reduce_lob_snapshots


def test_jalali_anchor():
    assert str(jalali_int_to_gregorian(14040101).date()) == "2025-03-21"


def test_underlying_classifier_six_names():
    names = ["اهرم", "خودرو", "خساپا", "شستا", "وبملت", "وتجارت"]
    for name in names:
        assert parse_underlying_label(f"اختیارخ {name}", names) == (name, "call")
        assert parse_underlying_label(f"اختیارف {name}", names) == (name, "put")
    with pytest.raises(ValueError):
        parse_underlying_label("اختیارخ ناشناس", names)


def test_lob_tree_walk_and_date_assert(tmp_path):
    root = tmp_path / "best_limits_data" / "123"
    root.mkdir(parents=True)
    p = root / "20250101.csv"
    p.write_text("symbol,instrument_id,date,hEven,refID,number,qTitMeDem,pMeDem,pMeOf,qTitMeOf\nx,999,20250101,90101,1,1,10,100,102,20\n", encoding="utf-8")
    cfg = {"data_root": tmp_path}
    files = discover_lob_files(cfg)
    assert files.iloc[0]["instrument_id"] == 123
    assert files.iloc[0]["date"] == 20250101
    df = load_lob_day_file(p, 123, 20250101)
    assert df.iloc[0]["instrument_id"] == 123


def test_lob_reducer_synthetic_5_level():
    rows = []
    for level in range(1, 6):
        rows.append({"instrument_id": 1, "date": 20250101, "hEven": 90101, "refID": 1, "number": level,
                     "qTitMeDem": 10 * level, "pMeDem": 100 - level, "pMeOf": 101 + level, "qTitMeOf": 20 * level})
    out = reduce_lob_snapshots(pd.DataFrame(rows))
    assert len(out) == 1
    assert out.iloc[0]["mid"] == 100.5
    assert out.iloc[0]["spread"] == 3
    assert out.iloc[0]["depth_bid"] == 150
    assert out.iloc[0]["depth_ask"] == 300
