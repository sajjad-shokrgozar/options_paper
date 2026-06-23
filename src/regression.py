from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


def _tidy_model(model, label: str, underlying: str = "pooled") -> pd.DataFrame:
    return pd.DataFrame({
        "model": label,
        "underlying_name": underlying,
        "term": model.params.index,
        "coef": model.params.values,
        "std_err": model.bse.values,
        "t": model.tvalues.values,
        "p_value": model.pvalues.values,
        "nobs": int(model.nobs),
        "r2": getattr(model, "rsquared", np.nan),
    })


def run_q2(panel: pd.DataFrame, ranking: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = panel.copy()
    df["pricing_deviation"] = (df["close"] - df["bs_price_rv21"]).abs() / df["close"].replace(0, np.nan)
    df["log_depth_total"] = np.log1p(df["depth_total"])
    df["daily_spread_proxy"] = df["daily_hl_spread_proxy"].fillna(df["daily_hl_spread_proxy"].median())
    reg = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["pricing_deviation", "daily_spread_proxy", "no_trade", "moneyness", "T", "realized_vol_21"])
    outputs = []
    if len(reg) >= 50 and reg["underlying_name"].nunique() >= 1:
        formula = "pricing_deviation ~ daily_spread_proxy + no_trade + moneyness + T + realized_vol_21 + C(underlying_name)"
        outputs.append(_tidy_model(smf.ols(formula, data=reg).fit(cov_type="HC1"), "daily_proxy"))
    daily = pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame(columns=["model", "underlying_name", "term", "coef", "std_err", "t", "p_value", "nobs", "r2"])
    by = []
    for name, g in reg.groupby("underlying_name"):
        if len(g) < 30:
            by.append({"model": "by_underlying_daily", "underlying_name": name, "term": "INSUFFICIENT_DATA", "coef": np.nan, "std_err": np.nan, "t": np.nan, "p_value": np.nan, "nobs": len(g), "r2": np.nan})
            continue
        m = smf.ols("pricing_deviation ~ daily_spread_proxy + no_trade + moneyness + T + realized_vol_21", data=g).fit(cov_type="HC1")
        by.append(_tidy_model(m, "by_underlying_daily", name))
    by_df = pd.concat([x if isinstance(x, pd.DataFrame) else pd.DataFrame([x]) for x in by], ignore_index=True) if by else pd.DataFrame()
    inter = pd.DataFrame()
    if len(reg) >= 50:
        m = smf.ols("pricing_deviation ~ daily_spread_proxy*C(underlying_name) + no_trade + moneyness + T + realized_vol_21", data=reg).fit(cov_type="HC1")
        inter = _tidy_model(m, "daily_interaction")
    lob_reg = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["pricing_deviation", "rel_spread", "log_depth_total", "no_trade", "moneyness", "T", "realized_vol_21"])
    if len(lob_reg) >= 50:
        lob = _tidy_model(smf.ols("pricing_deviation ~ rel_spread + log_depth_total + no_trade + moneyness + T + realized_vol_21 + C(underlying_name)", data=lob_reg).fit(cov_type="HC1"), "lob")
    else:
        lob = pd.DataFrame([{"model": "lob", "underlying_name": "pooled", "term": "INSUFFICIENT_DATA", "coef": np.nan, "std_err": np.nan, "t": np.nan, "p_value": np.nan, "nobs": len(lob_reg), "r2": np.nan}])
    return daily, lob, by_df, inter
