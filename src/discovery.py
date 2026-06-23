from __future__ import annotations

import numpy as np
import pandas as pd
import warnings
from statsmodels.tsa.stattools import grangercausalitytests


def price_discovery_daily(panel: pd.DataFrame, max_lag: int = 5) -> pd.DataFrame:
    rows = []
    for name, g in panel.sort_values("date_dt").groupby("underlying_name"):
        d = g.loc[(g["moneyness"] - 1).abs().groupby(g["date"]).idxmin().dropna()] if not g.empty else g
        series = d.groupby("date_dt").agg(underlying_ret=("underlying_log_ret", "first"), option_ret=("option_ret", "median")).dropna()
        if len(series) < 30:
            rows.append({"underlying_name": name, "nobs": len(series), "peak_lag": np.nan, "peak_corr": np.nan,
                         "granger_underlying_to_option_p": np.nan, "granger_option_to_underlying_p": np.nan,
                         "data_sufficiency": "INSUFFICIENT_DATA"})
            continue
        corrs = {}
        for lag in range(-max_lag, max_lag + 1):
            if lag < 0:
                corrs[lag] = series["underlying_ret"].corr(series["option_ret"].shift(-lag))
            else:
                corrs[lag] = series["underlying_ret"].shift(lag).corr(series["option_ret"])
        peak_lag = max(corrs, key=lambda k: abs(corrs[k]) if pd.notna(corrs[k]) else -1)
        p_uo = np.nan
        p_ou = np.nan
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                p_uo = grangercausalitytests(series[["option_ret", "underlying_ret"]], maxlag=min(3, len(series)//10), verbose=False)[1][0]["ssr_ftest"][1]
                p_ou = grangercausalitytests(series[["underlying_ret", "option_ret"]], maxlag=min(3, len(series)//10), verbose=False)[1][0]["ssr_ftest"][1]
        except Exception:
            pass
        rows.append({"underlying_name": name, "nobs": len(series), "peak_lag": peak_lag, "peak_corr": corrs[peak_lag],
                     "granger_underlying_to_option_p": p_uo, "granger_option_to_underlying_p": p_ou,
                     "data_sufficiency": "OK"})
    return pd.DataFrame(rows)


def intraday_stub(lob_daily: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    if lob_daily is None or lob_daily.empty:
        return pd.DataFrame([{"underlying_name": "ALL", "n_lob_days": 0, "option_information_share_mid": np.nan, "data_sufficiency": "INSUFFICIENT_DATA"}])
    rows = []
    for name, g in lob_daily.groupby("underlying_name", dropna=False):
        days = g["date"].nunique()
        status = "OK_PROXY_ONLY" if days >= cfg.get("lob", {}).get("min_intraday_days", 2) else "INSUFFICIENT_DATA"
        opt = g[g["opt_type"].isin(["call", "put"])]
        und = g[g["opt_type"].eq("underlying")]
        proxy = len(opt) / max(1, len(opt) + len(und)) if len(g) else np.nan
        rows.append({"underlying_name": name, "n_lob_days": days, "option_information_share_mid": proxy, "data_sufficiency": status})
    return pd.DataFrame(rows)


def cross_section(daily: pd.DataFrame, intraday: pd.DataFrame, ranking: pd.DataFrame, q2_by: pd.DataFrame) -> pd.DataFrame:
    out = ranking[["underlying_name", "liquidity_rank", "no_trade_rate"]].merge(daily, on="underlying_name", how="left")
    if not intraday.empty:
        out = out.merge(intraday[["underlying_name", "option_information_share_mid", "data_sufficiency"]].rename(columns={"data_sufficiency": "intraday_sufficiency"}), on="underlying_name", how="left")
    prem = q2_by[q2_by["term"].eq("daily_spread_proxy")][["underlying_name", "coef", "p_value"]].rename(columns={"coef": "liquidity_premium_slope", "p_value": "liquidity_premium_p"})
    return out.merge(prem, on="underlying_name", how="left")
