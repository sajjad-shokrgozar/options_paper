from __future__ import annotations

from pathlib import Path
import re
import numpy as np
import pandas as pd

from .calendar import yyyymmdd_to_datetime, jalali_int_to_gregorian, gregorian_to_jalali_year_month

CALL_PREFIX = "اختیارخ"
PUT_PREFIX = "اختیارف"


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def canonicalize_text(s) -> str:
    return "" if pd.isna(s) else str(s).replace("ي", "ی").replace("ك", "ک").strip()


def parse_underlying_label(label: str, allowed: list[str] | None = None) -> tuple[str, str]:
    txt = canonicalize_text(label)
    if txt.startswith(CALL_PREFIX):
        kind = "call"
        name = txt[len(CALL_PREFIX):].strip()
    elif txt.startswith(PUT_PREFIX):
        kind = "put"
        name = txt[len(PUT_PREFIX):].strip()
    else:
        raise ValueError(f"cannot parse option underlying label: {label!r}")
    if allowed and name not in allowed:
        raise ValueError(f"unknown underlying name {name!r}; allowed={allowed}")
    return name, kind


def load_options(cfg: dict) -> pd.DataFrame:
    df = _read_csv(Path(cfg["data_root"]) / "options_history.csv")
    allowed = cfg.get("canonical_underlyings")
    parsed = df["underlying"].map(lambda x: parse_underlying_label(x, allowed))
    df["underlying_name"] = parsed.map(lambda x: x[0])
    df["opt_type"] = parsed.map(lambda x: x[1])
    df["date_dt"] = df["date"].map(yyyymmdd_to_datetime)
    df["maturity_dt"] = df["maturity"].map(jalali_int_to_gregorian)
    df["T"] = (df["maturity_dt"] - df["date_dt"]).dt.days / float(cfg["day_count"])
    df["no_trade"] = (df["volume"].fillna(0) == 0) | (df["trades_count"].fillna(0) == 0)
    df["stale_close"] = df["no_trade"] & (df["close"] == df["yesterday"])
    return df


def load_underlyings(cfg: dict) -> pd.DataFrame:
    df = _read_csv(Path(cfg["data_root"]) / "underlying_history.csv")
    df["symbol"] = df["symbol"].map(canonicalize_text)
    df["underlying_name"] = df["symbol"]
    df["date_dt"] = df["date"].map(yyyymmdd_to_datetime)
    df = df.sort_values(["underlying_name", "date_dt"])
    df["underlying_no_trade"] = (df["volume"].fillna(0) == 0) | (df["trades_count"].fillna(0) == 0)
    df["adj_price_ffill"] = df.groupby("underlying_name")["adj_price"].ffill()
    df["log_ret"] = np.log(df["adj_price_ffill"] / df.groupby("underlying_name")["adj_price_ffill"].shift(1))
    df.loc[df["underlying_no_trade"], "log_ret"] = df.loc[df["underlying_no_trade"], "log_ret"].fillna(0.0)
    for win in [21, 63]:
        df[f"realized_vol_{win}"] = (
            df.groupby("underlying_name")["log_ret"]
            .rolling(win, min_periods=max(5, win // 3)).std()
            .reset_index(level=0, drop=True)
            * np.sqrt(cfg["ann_factor"])
        )
    return df


def build_instrument_master(options: pd.DataFrame, underlyings: pd.DataFrame) -> pd.DataFrame:
    opt = (
        options.groupby("id")
        .agg(symbol=("symbol", "first"), underlying_name=("underlying_name", "first"),
             opt_type=("opt_type", "first"), strike=("strike", "first"),
             maturity=("maturity", "first"), maturity_dt=("maturity_dt", "first"),
             first_seen=("date", "min"), last_seen=("date", "max"))
        .reset_index()
        .rename(columns={"id": "instrument_id"})
    )
    und = (
        underlyings.groupby("id")
        .agg(symbol=("symbol", "first"), underlying_name=("underlying_name", "first"),
             first_seen=("date", "min"), last_seen=("date", "max"))
        .reset_index()
        .rename(columns={"id": "instrument_id"})
    )
    und["opt_type"] = "underlying"
    und["strike"] = np.nan
    und["maturity"] = np.nan
    und["maturity_dt"] = pd.NaT
    cols = ["instrument_id", "symbol", "underlying_name", "opt_type", "strike", "maturity", "maturity_dt", "first_seen", "last_seen"]
    return pd.concat([opt[cols], und[cols]], ignore_index=True)


def load_macro_rates(cfg: dict, dates: pd.Series) -> pd.DataFrame:
    root = Path(cfg["data_root"])
    macro = root / "Main_DataBase.xlsx"
    out = pd.DataFrame({"date_dt": pd.to_datetime(pd.Series(dates).drop_duplicates()).sort_values()})
    out[["jalali_year", "jalali_month"]] = out["date_dt"].apply(lambda x: pd.Series(gregorian_to_jalali_year_month(x)))
    out["macro_rate_source"] = "default_missing_macro_file"
    out["risk_free_filled"] = True
    out["r"] = float(cfg.get("risk_free_default", 0.34))
    if not macro.exists():
        return out
    try:
        econ = pd.read_excel(macro, sheet_name="economic_variables")
        if "risk_free_rate" not in econ.columns:
            return out
        econ = econ.copy()
        month_col = "month_num" if "month_num" in econ.columns else "month"
        if month_col == "month":
            month_map = {"فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5, "شهریور": 6,
                         "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10, "بهمن": 11, "اسفند": 12}
            econ["jalali_month"] = econ["month"].map(lambda x: month_map.get(canonicalize_text(x), np.nan))
        else:
            econ["jalali_month"] = econ[month_col]
        econ["jalali_year"] = econ["year"]
        rates = econ[["jalali_year", "jalali_month", "risk_free_rate"]].dropna()
        merged = out.drop(columns=["r", "macro_rate_source", "risk_free_filled"]).merge(rates, on=["jalali_year", "jalali_month"], how="left")
        merged = merged.sort_values("date_dt")
        merged["r"] = merged["risk_free_rate"].ffill().fillna(float(cfg.get("risk_free_default", 0.34)))
        merged["risk_free_filled"] = merged["risk_free_rate"].isna()
        merged["macro_rate_source"] = np.where(merged["risk_free_filled"], "forward_or_default_fill", "Main_DataBase.xlsx")
        return merged.drop(columns=["risk_free_rate"])
    except Exception:
        return out


def discover_lob_files(cfg: dict) -> pd.DataFrame:
    root = Path(cfg["data_root"]) / "best_limits_data"
    rows = []
    if not root.exists():
        return pd.DataFrame(columns=["instrument_id", "date", "path"])
    for folder in root.iterdir():
        if not folder.is_dir() or not folder.name.isdigit():
            continue
        for file in folder.glob("*.csv"):
            if re.fullmatch(r"\d{8}", file.stem):
                rows.append({"instrument_id": int(folder.name), "date": int(file.stem), "path": str(file)})
    return pd.DataFrame(rows)


def load_lob_day_file(path: str | Path, folder_instrument_id: int, filename_date: int) -> pd.DataFrame:
    df = _read_csv(Path(path))
    if df.empty:
        return df
    if "date" in df.columns and not (df["date"].astype(int) == int(filename_date)).all():
        raise AssertionError(f"inner date mismatch in {path}")
    df["instrument_id"] = int(folder_instrument_id)
    df["date"] = int(filename_date)
    return df
