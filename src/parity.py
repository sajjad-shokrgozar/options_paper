from __future__ import annotations

import numpy as np
import pandas as pd
from .pricing_bs import no_arb_bounds


def add_parity_and_bounds(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = panel.copy()
    lower_upper = [no_arb_bounds(S, K, T, r, kind) if np.isfinite(S) and np.isfinite(K) and T > 0 else (np.nan, np.nan)
                   for S, K, T, r, kind in zip(df["S"], df["strike"], df["T"], df["r"], df["opt_type"])]
    df["noarb_lower"] = [x[0] for x in lower_upper]
    df["noarb_upper"] = [x[1] for x in lower_upper]
    df["bound_violation"] = (df["close"] < df["noarb_lower"]) | (df["close"] > df["noarb_upper"])
    df["bound_violation_amount"] = np.where(df["close"] < df["noarb_lower"], df["noarb_lower"] - df["close"],
                                      np.where(df["close"] > df["noarb_upper"], df["close"] - df["noarb_upper"], 0.0))
    key = ["underlying_name", "date", "strike", "maturity"]
    calls = (
        df[df["opt_type"] == "call"]
        .groupby(key, as_index=False)
        .agg(call_close=("close", "median"), S=("S", "first"), T=("T", "first"), r=("r", "first"))
    )
    puts = (
        df[df["opt_type"] == "put"]
        .groupby(key, as_index=False)
        .agg(put_close=("close", "median"))
    )
    pairs = calls.merge(puts, on=key, how="inner")
    if not pairs.empty:
        pairs["parity_gap"] = pairs["call_close"] - pairs["put_close"] - (pairs["S"] - pairs["strike"] * np.exp(-pairs["r"] * pairs["T"]))
        df = df.merge(pairs[key + ["parity_gap"]], on=key, how="left")
    else:
        df["parity_gap"] = np.nan
    table = df.groupby("underlying_name").agg(
        rows=("id", "size"),
        bound_violations=("bound_violation", "sum"),
        bound_violation_rate=("bound_violation", "mean"),
        median_abs_parity_gap=("parity_gap", lambda x: x.abs().median()),
        p95_abs_parity_gap=("parity_gap", lambda x: x.abs().quantile(0.95)),
    ).reset_index()
    return df, table
