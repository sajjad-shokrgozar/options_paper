from __future__ import annotations

import numpy as np
import pandas as pd
from .fixes_reference import (
    build_q2_dependent,
    run_q2_clustered,
    _fit_clustered,
    _tidy,
)


def run_q2(
    panel: pd.DataFrame,
    ranking: pd.DataFrame,
    cfg: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    P3/P4/P5: Q2 liquidity-premium regressions with corrected DV, SEs, and
    identification.

    P3 (DV): the old DV divided by raw close, exploding for cheap OTM options.
      Now: |close - bs| / max(close, tick_floor), then winsorized at 1/99th
      percentile within underlying. Stale-close rows dropped from main spec.

    P4 (SEs): the old HC1 standard errors left t-stats around 56 and exact
      p = 0.0 because panel residuals are clustered by contract and date.
      Now: two-way cluster on (id, date). n_clusters reported in the table.

    P5 (identification): the old DV (|close - bs_price_rv21|) baked realized
      vol into the benchmark AND used it as a regressor, confounding the
      liquidity premium with the implied-realized vol premium.
      Now: winsorized relative deviation is the main DV while realized_vol_21
      remains a right-hand control; run_q2_iv() uses iv_close as an
      identification-clean alternative DV (not a function of realized vol).

    Returns (daily, lob, by_underlying, interaction) — same tuple shape as
    before so run_all.py does not need structural changes, only cfg passing.
    """
    rcfg = (cfg or {}).get("regression", {})
    tick_floor = float(rcfg.get("tick_floor", 1.0))
    winsor_lo = float(rcfg.get("winsor_lo", 0.01))
    winsor_hi = float(rcfg.get("winsor_hi", 0.99))
    cluster_cols = list(rcfg.get("cluster_cols", ["id", "date"]))
    min_obs = int(rcfg.get("min_obs", 50))

    # ---- main pooled daily spec (P3 + P4) ----------------------------------
    daily = run_q2_clustered(
        panel,
        dep="rel_dev_w",
        cluster_cols=tuple(cluster_cols),
        min_obs=min_obs,
    )

    # ---- build shared regression frame ------------------------------------
    df = build_q2_dependent(panel, tick_floor=tick_floor, winsor=(winsor_lo, winsor_hi))
    reg = df.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["rel_dev_w", "daily_spread_proxy", "no_trade", "moneyness", "T", "realized_vol_21"]
    )

    # ---- LOB spec (P4) ----------------------------------------------------
    lob_reg = df.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["rel_dev_w", "rel_spread", "log_depth_total", "no_trade", "moneyness", "T", "realized_vol_21"]
    )
    if len(lob_reg) >= min_obs:
        cl = [c for c in cluster_cols if c in lob_reg.columns]
        n_cl = int(lob_reg[cl[0]].nunique()) if cl else 0
        lob_m = _fit_clustered(
            "rel_dev_w ~ rel_spread + log_depth_total + no_trade + moneyness + T"
            " + realized_vol_21 + C(underlying_name)",
            lob_reg, cl,
        )
        lob = _tidy(lob_m, "lob_clustered", "pooled", n_cl)
    else:
        lob = pd.DataFrame([{
            "model": "lob_clustered", "underlying_name": "pooled",
            "term": "INSUFFICIENT_DATA", "coef": np.nan, "std_err": np.nan,
            "t": np.nan, "p_value": np.nan, "nobs": len(lob_reg),
            "r2": np.nan, "n_clusters": 0, "dep_var": "rel_dev_w",
        }])

    # ---- by-underlying spec (P4) ------------------------------------------
    by = []
    for name, g in reg.groupby("underlying_name"):
        if len(g) < 30:
            by.append({
                "model": "by_underlying_daily", "underlying_name": name,
                "term": "INSUFFICIENT_DATA", "coef": np.nan, "std_err": np.nan,
                "t": np.nan, "p_value": np.nan, "nobs": len(g),
                "r2": np.nan, "n_clusters": 0, "dep_var": "rel_dev_w",
            })
            continue
        cl = [c for c in cluster_cols if c in g.columns]
        n_cl = int(g[cl[0]].nunique()) if cl else 0
        m = _fit_clustered(
            "rel_dev_w ~ daily_spread_proxy + no_trade + moneyness + T + realized_vol_21",
            g, cl,
        )
        by.append(_tidy(m, "by_underlying_daily", name, n_cl))

    by_df = (
        pd.concat([x if isinstance(x, pd.DataFrame) else pd.DataFrame([x]) for x in by],
                  ignore_index=True)
        if by else pd.DataFrame()
    )

    # ---- interaction spec (only meaningful with multiple underlyings) ------
    inter = pd.DataFrame()
    if len(reg) >= min_obs and reg["underlying_name"].nunique() > 1:
        cl = [c for c in cluster_cols if c in reg.columns]
        n_cl = int(reg[cl[0]].nunique()) if cl else 0
        m = _fit_clustered(
            "rel_dev_w ~ daily_spread_proxy*C(underlying_name) + no_trade"
            " + moneyness + T + realized_vol_21",
            reg, cl,
        )
        inter = _tidy(m, "daily_interaction", "pooled", n_cl)

    return daily, lob, by_df, inter
