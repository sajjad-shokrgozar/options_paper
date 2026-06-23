from __future__ import annotations

import numpy as np
import pandas as pd
from .pricing_bs import no_arb_bounds


def add_parity_and_bounds(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = panel.copy()
    # Drop pre-existing parity columns so re-runs (e.g. sensitivity loop) don't
    # produce merge-suffix conflicts (parity_gap_x / parity_gap_y).
    _parity_cols = ["parity_gap", "noarb_lower", "noarb_upper",
                    "bound_violation", "bound_violation_amount"]
    df = df.drop(columns=[c for c in _parity_cols if c in df.columns])
    lower_upper = [
        no_arb_bounds(S, K, T, r, kind) if np.isfinite(S) and np.isfinite(K) and T > 0 else (np.nan, np.nan)
        for S, K, T, r, kind in zip(df["S"], df["strike"], df["T"], df["r"], df["opt_type"])
    ]
    df["noarb_lower"] = [x[0] for x in lower_upper]
    df["noarb_upper"] = [x[1] for x in lower_upper]
    df["bound_violation"] = (df["close"] < df["noarb_lower"]) | (df["close"] > df["noarb_upper"])
    df["bound_violation_amount"] = np.where(
        df["close"] < df["noarb_lower"], df["noarb_lower"] - df["close"],
        np.where(df["close"] > df["noarb_upper"], df["close"] - df["noarb_upper"], 0.0)
    )
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
        pairs["parity_gap"] = (
            pairs["call_close"] - pairs["put_close"]
            - (pairs["S"] - pairs["strike"] * np.exp(-pairs["r"] * pairs["T"]))
        )
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


def _violation_fn(panel_with_r: pd.DataFrame) -> pd.Series:
    """Returns a boolean violation Series from a panel that already has 'r' set."""
    df, _ = add_parity_and_bounds(panel_with_r)
    return df["bound_violation"].fillna(False)


def run_parity_sensitivity(panel: pd.DataFrame) -> pd.DataFrame:
    """
    P8: violation rate as a function of the assumed risk-free rate and
    stale/non-stale split.

    Because Main_DataBase.xlsx is currently absent and a flat r = 0.34 fallback
    is used, the headline 24% bound-violation rate cannot be cleanly attributed
    to frictions. This table shows how the rate moves over r in {0.28, 0.34, 0.40}
    and how it changes when stale-close rows are excluded, so the sensitivity is
    transparent until the macro workbook is supplied.
    """
    from .fixes_reference import parity_rate_sensitivity
    return parity_rate_sensitivity(panel, _violation_fn)
