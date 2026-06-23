from __future__ import annotations

import math
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm


def bs_price(S, K, T, r, sigma, kind: str, q: float = 0.0) -> float:
    if min(S, K, T, sigma) <= 0:
        return np.nan
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if kind == "call":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    if kind == "put":
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
    raise ValueError(f"unknown option kind: {kind}")


def bs_vega(S, K, T, r, sigma, q: float = 0.0) -> float:
    if min(S, K, T, sigma) <= 0:
        return np.nan
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)


def no_arb_bounds(S, K, T, r, kind: str) -> tuple[float, float]:
    discK = K * math.exp(-r * T)
    if kind == "call":
        return max(0.0, S - discK), S
    if kind == "put":
        return max(0.0, discK - S), discK
    raise ValueError(kind)


def implied_vol(target_price, S, K, T, r, kind: str, bounds=(0.001, 5.0), min_price=1.0):
    if any(pd.isna(x) for x in [target_price, S, K, T, r]) or T <= 0 or S <= 0 or K <= 0:
        return np.nan, "bad_inputs"
    if target_price < min_price:
        return np.nan, "below_min_price"
    lo, hi = no_arb_bounds(float(S), float(K), float(T), float(r), kind)
    tol = max(1e-8, 1e-6 * max(1.0, target_price))
    if target_price < lo - tol:
        return np.nan, "below_noarb"
    if target_price > hi + tol:
        return np.nan, "above_noarb"
    a, b = bounds
    try:
        fa = bs_price(S, K, T, r, a, kind) - target_price
        fb = bs_price(S, K, T, r, b, kind) - target_price
        if fa * fb > 0:
            return np.nan, "not_bracketed"
        return brentq(lambda sig: bs_price(S, K, T, r, sig, kind) - target_price, a, b, xtol=1e-8), "ok"
    except Exception:
        return np.nan, "solver_error"


def add_pricing_columns(panel: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = panel.copy()
    vol = df["realized_vol_21"].fillna(df["realized_vol_63"]).fillna(df["realized_vol_21"].median())
    vol = vol.clip(lower=0.01, upper=5.0).fillna(0.5)
    df["bs_price_rv21"] = [
        bs_price(S, K, T, r, sig, kind)
        for S, K, T, r, sig, kind in zip(df["S"], df["strike"], df["T"], df["r"], vol, df["opt_type"])
    ]
    close_iv = [implied_vol(p, S, K, T, r, kind, cfg["iv_bounds"], cfg["min_option_price"])
                for p, S, K, T, r, kind in zip(df["close"], df["S"], df["strike"], df["T"], df["r"], df["opt_type"])]
    df["iv_close"] = [x[0] for x in close_iv]
    df["iv_close_fail_reason"] = [x[1] for x in close_iv]
    if "mid" in df.columns:
        mid_iv = [implied_vol(p, S, K, T, r, kind, cfg["iv_bounds"], cfg["min_option_price"])
                  for p, S, K, T, r, kind in zip(df["mid"], df["S"], df["strike"], df["T"], df["r"], df["opt_type"])]
        df["iv_mid"] = [x[0] for x in mid_iv]
        df["iv_mid_fail_reason"] = [x[1] for x in mid_iv]
    else:
        df["iv_mid"] = np.nan
        df["iv_mid_fail_reason"] = "no_mid"
    return df
