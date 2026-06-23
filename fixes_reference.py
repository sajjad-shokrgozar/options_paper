"""
fixes_reference.py
==================

Reference implementations for the corrections listed in FIXES_FOR_CODEX.md.

These are drop-in functions for the Iranian equity-option pipeline. They are
written to match the existing panel columns (opt_type, moneyness,
underlying_log_ret, option_ret, date_dt, date, close, bs_price_rv21,
realized_vol_21, daily_hl_spread_proxy, no_trade, T, underlying_name, id,
depth_total, rel_spread, value, stale_close, iv_close, iv_mid).

INSTRUCTIONS FOR CODEX
----------------------
- Use these functions to REPLACE the broken logic in src/discovery.py,
  src/regression.py, src/iv_quality.py, and src/parity.py.
- Adapt column names ONLY if the real panel differs; keep behaviour identical.
- Do NOT remove existing data_sufficiency flags. Where a result is not
  estimable, return NaN + a flag, never a placeholder number.
- Every function is defensive about empty/short inputs and returns a tidy
  DataFrame or a flagged row instead of raising.

Dependencies: numpy, pandas, statsmodels (no scipy required).
"""

from __future__ import annotations

import warnings
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.tsa.stattools import grangercausalitytests


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _winsorize(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """Clip a series to its [lower, upper] quantiles. NaN-safe."""
    s = pd.to_numeric(s, errors="coerce")
    if s.dropna().empty:
        return s
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lo, hi)


def _safe_granger(frame: pd.DataFrame, maxlag: int) -> float:
    """Return the lag-1 ssr F-test p-value, or NaN. frame columns: [y, x]."""
    maxlag = max(1, int(maxlag))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = grangercausalitytests(frame, maxlag=maxlag)  # no verbose kwarg (deprecated)
        return float(res[1][0]["ssr_ftest"][1])
    except Exception:
        return np.nan


# --------------------------------------------------------------------------- #
# P1 — Q1 lead-lag, computed SEPARATELY for calls and puts
# --------------------------------------------------------------------------- #
def price_discovery_daily_by_type(
    panel: pd.DataFrame,
    max_lag: int = 5,
    atm_band: float = 0.05,
    min_obs: int = 30,
) -> pd.DataFrame:
    """
    Replacement for src/discovery.py:price_discovery_daily().

    Fixes the type-switching contamination: the old code picked one near-ATM
    contract per date and could flip between a call and a put day to day,
    producing a meaningless negative peak correlation.

    Here, for each (underlying_name, opt_type) we build a per-date
    volume-weighted return of the near-ATM band, then measure lead-lag against
    the underlying return. For puts we ALSO report a sign-flipped series
    (puts move opposite to the underlying) so the expected contemporaneous sign
    is positive for both types and the two are comparable.

    Output columns:
        underlying_name, opt_type, nobs, peak_lag, peak_corr,
        peak_corr_signed, granger_underlying_to_option_p,
        granger_option_to_underlying_p, data_sufficiency
    """
    rows: list[dict] = []
    need = {"underlying_name", "opt_type", "moneyness", "date_dt", "date",
            "option_ret", "underlying_log_ret"}
    if not need.issubset(panel.columns):
        missing = sorted(need - set(panel.columns))
        raise KeyError(f"panel missing columns for Q1: {missing}")

    has_value = "value" in panel.columns

    for (name, otype), g in panel.groupby(["underlying_name", "opt_type"]):
        if otype not in ("call", "put"):
            continue
        band = g[(g["moneyness"] - 1.0).abs() <= atm_band].copy()
        if band.empty:
            rows.append(_q1_insufficient(name, otype, 0))
            continue

        # per-date volume-weighted option return for THIS type only
        def _vw(sub: pd.DataFrame) -> float:
            r = pd.to_numeric(sub["option_ret"], errors="coerce")
            if has_value:
                w = pd.to_numeric(sub["value"], errors="coerce").clip(lower=0)
            else:
                w = pd.Series(1.0, index=sub.index)
            m = r.notna() & w.notna()
            if not m.any() or w[m].sum() == 0:
                return r[m].mean() if m.any() else np.nan
            return float(np.average(r[m], weights=w[m]))

        opt_by_date = band.groupby("date_dt").apply(_vw).rename("option_ret")
        und_by_date = (
            band.groupby("date_dt")["underlying_log_ret"].first().rename("underlying_ret")
        )
        series = pd.concat([und_by_date, opt_by_date], axis=1).dropna()
        if len(series) < min_obs:
            rows.append(_q1_insufficient(name, otype, len(series)))
            continue

        # sign-flip puts so both types should be positively related to underlying
        series["option_ret_signed"] = series["option_ret"] * (-1.0 if otype == "put" else 1.0)

        corrs, corrs_signed = {}, {}
        for lag in range(-max_lag, max_lag + 1):
            if lag < 0:
                corrs[lag] = series["underlying_ret"].corr(series["option_ret"].shift(-lag))
                corrs_signed[lag] = series["underlying_ret"].corr(series["option_ret_signed"].shift(-lag))
            else:
                corrs[lag] = series["underlying_ret"].shift(lag).corr(series["option_ret"])
                corrs_signed[lag] = series["underlying_ret"].shift(lag).corr(series["option_ret_signed"])
        peak_lag = max(corrs, key=lambda k: abs(corrs[k]) if pd.notna(corrs[k]) else -1)

        maxlag = min(3, len(series) // 10)
        p_uo = _safe_granger(series[["option_ret", "underlying_ret"]], maxlag)
        p_ou = _safe_granger(series[["underlying_ret", "option_ret"]], maxlag)

        rows.append({
            "underlying_name": name,
            "opt_type": otype,
            "nobs": len(series),
            "peak_lag": peak_lag,
            "peak_corr": corrs[peak_lag],
            "peak_corr_signed": corrs_signed[peak_lag],
            "granger_underlying_to_option_p": p_uo,
            "granger_option_to_underlying_p": p_ou,
            "data_sufficiency": "OK",
        })
    return pd.DataFrame(rows)


def _q1_insufficient(name, otype, nobs) -> dict:
    return {
        "underlying_name": name, "opt_type": otype, "nobs": nobs,
        "peak_lag": np.nan, "peak_corr": np.nan, "peak_corr_signed": np.nan,
        "granger_underlying_to_option_p": np.nan,
        "granger_option_to_underlying_p": np.nan,
        "data_sufficiency": "INSUFFICIENT_DATA",
    }


# --------------------------------------------------------------------------- #
# P2 — real (guarded) intraday information share + honest coverage ratio
# --------------------------------------------------------------------------- #
def intraday_information_share(
    lob_paired: pd.DataFrame | None,
    min_paired_snaps: int = 200,
) -> pd.DataFrame:
    """
    Replacement for the FAKE share in src/discovery.py:intraday_stub().

    `lob_paired` must contain SYNCHRONIZED intraday midpoints of the underlying
    and a near-ATM option on a common grid, with columns:
        underlying_name, ts, under_mid, opt_mid
    If you cannot build that frame, pass None / empty and every row is flagged
    INSUFFICIENT_DATA with a NaN share. NEVER emit a placeholder number.

    Where data suffice, a Gonzalo-Granger component share is computed from a
    bivariate VECM on the two midpoint (log) series.

    Output columns:
        underlying_name, n_paired_snaps, gg_option_share, data_sufficiency
    """
    if lob_paired is None or lob_paired.empty:
        return pd.DataFrame([{
            "underlying_name": "ALL", "n_paired_snaps": 0,
            "gg_option_share": np.nan, "data_sufficiency": "INSUFFICIENT_DATA",
        }])

    try:
        from statsmodels.tsa.vector_ar.vecm import VECM
    except Exception:
        VECM = None

    rows = []
    for name, g in lob_paired.groupby("underlying_name"):
        g = g.dropna(subset=["under_mid", "opt_mid"]).sort_values("ts")
        n = len(g)
        if VECM is None or n < min_paired_snaps:
            rows.append({"underlying_name": name, "n_paired_snaps": n,
                         "gg_option_share": np.nan,
                         "data_sufficiency": "INSUFFICIENT_DATA"})
            continue
        y = np.log(g[["under_mid", "opt_mid"]].astype(float).clip(lower=1e-9))
        try:
            model = VECM(y, k_ar_diff=1, coint_rank=1, deterministic="ci").fit()
            # Gonzalo-Granger component share: row of the (2x1) loading matrix
            # alpha orthogonalised. Share attributable to the option (2nd series).
            alpha = np.asarray(model.alpha).ravel()  # length 2
            # component weights are proportional to the orthogonal complement of alpha
            gamma = np.array([alpha[1], -alpha[0]])
            w = np.abs(gamma) / np.abs(gamma).sum() if np.abs(gamma).sum() > 0 else np.array([np.nan, np.nan])
            opt_share = float(w[1])  # weight on the option series
            rows.append({"underlying_name": name, "n_paired_snaps": n,
                         "gg_option_share": opt_share,
                         "data_sufficiency": "OK"})
        except Exception:
            rows.append({"underlying_name": name, "n_paired_snaps": n,
                         "gg_option_share": np.nan,
                         "data_sufficiency": "ESTIMATION_FAILED"})
    return pd.DataFrame(rows)


def lob_file_option_share(lob_daily: pd.DataFrame) -> pd.DataFrame:
    """
    HONEST renaming of the old metric: this is a DATA-COVERAGE descriptor only,
    the fraction of LOB rows that are option (vs underlying) rows. It is NOT an
    information share and must never be labelled as one.
    """
    if lob_daily is None or lob_daily.empty or "opt_type" not in lob_daily:
        return pd.DataFrame(columns=["underlying_name", "lob_file_option_share"])
    rows = []
    for name, g in lob_daily.groupby("underlying_name", dropna=True):  # drop phantom NaN group
        opt = (g["opt_type"].isin(["call", "put"])).sum()
        tot = len(g)
        rows.append({"underlying_name": name,
                     "lob_file_option_share": opt / tot if tot else np.nan})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# P3 + P4 + P5 — Q2 regressions: capped/winsorized DV, clustered SE, vol control
# --------------------------------------------------------------------------- #
def build_q2_dependent(
    panel: pd.DataFrame,
    tick_floor: float = 1.0,
    winsor: tuple[float, float] = (0.01, 0.99),
    drop_stale: bool = True,
) -> pd.DataFrame:
    """
    Build the Q2 regression frame with a well-behaved dependent variable.

    Fixes:
      * P3: divide by max(close, tick_floor) instead of raw close, drop sub-tick
        and (optionally) stale rows, winsorize the relative deviation WITHIN
        underlying. Also keep a level deviation in rials as a robustness target.
    Returns a frame with columns added:
        abs_dev, rel_dev, rel_dev_w (winsorized), log_depth_total,
        daily_spread_proxy
    """
    df = panel.copy()
    if "stale_close" not in df.columns:
        df["stale_close"] = False
    df["abs_dev"] = (df["close"] - df["bs_price_rv21"]).abs()
    denom = df["close"].clip(lower=tick_floor)
    df["rel_dev"] = df["abs_dev"] / denom

    keep = df["close"] >= tick_floor
    if drop_stale:
        keep &= ~df["stale_close"].fillna(False)
    df = df[keep].copy()

    df["rel_dev_w"] = (
        df.groupby("underlying_name")["rel_dev"]
        .transform(lambda s: _winsorize(s, winsor[0], winsor[1]))
    )
    df["log_depth_total"] = np.log1p(df.get("depth_total", np.nan))
    df["daily_spread_proxy"] = df["daily_hl_spread_proxy"].fillna(
        df["daily_hl_spread_proxy"].median()
    )
    return df


def _fit_clustered(formula: str, data: pd.DataFrame, cluster_cols: list[str]):
    """OLS with one- or two-way cluster-robust SEs (P4)."""
    codes = [pd.factorize(data[c])[0] for c in cluster_cols if c in data.columns]
    if not codes:
        return smf.ols(formula, data=data).fit(cov_type="HC1")
    groups = codes[0] if len(codes) == 1 else np.column_stack(codes)
    return smf.ols(formula, data=data).fit(cov_type="cluster",
                                           cov_kwds={"groups": groups})


def _tidy(model, label: str, underlying: str, n_clusters) -> pd.DataFrame:
    return pd.DataFrame({
        "model": label, "underlying_name": underlying,
        "term": model.params.index, "coef": model.params.values,
        "std_err": model.bse.values, "t": model.tvalues.values,
        "p_value": model.pvalues.values, "nobs": int(model.nobs),
        "r2": getattr(model, "rsquared", np.nan),
        "n_clusters": n_clusters,
        "dep_var": label,
    })


def run_q2_clustered(
    panel: pd.DataFrame,
    dep: str = "rel_dev_w",
    cluster_cols: tuple[str, str] = ("id", "date"),
    min_obs: int = 50,
) -> pd.DataFrame:
    """
    Replacement for src/regression.py:run_q2().

    Uses the winsorized DV from build_q2_dependent(), clustered SEs (P4), and
    reports the DV mean/SD so magnitudes are interpretable (P3). For the
    implied-realized confound (P5), prefer dep="iv_close" via run_q2_iv() below,
    or keep the price-error DV here while controlling for realized vol.

    Output: tidy regression table with n_clusters and DV moments in a footer row.
    """
    df = build_q2_dependent(panel)
    reg = df.replace([np.inf, -np.inf], np.nan).dropna(
        subset=[dep, "daily_spread_proxy", "no_trade", "moneyness", "T", "realized_vol_21"]
    )
    if len(reg) < min_obs:
        return pd.DataFrame([{"model": "daily", "underlying_name": "pooled",
                              "term": "INSUFFICIENT_DATA", "coef": np.nan,
                              "std_err": np.nan, "t": np.nan, "p_value": np.nan,
                              "nobs": len(reg), "r2": np.nan, "n_clusters": 0,
                              "dep_var": dep}])
    formula = (f"{dep} ~ daily_spread_proxy + no_trade + moneyness + T "
               f"+ realized_vol_21 + C(underlying_name)")
    cluster_list = [c for c in cluster_cols if c in reg.columns]
    n_clusters = int(reg[cluster_list[0]].nunique()) if cluster_list else 0
    model = _fit_clustered(formula, reg, cluster_list)
    out = _tidy(model, "daily_clustered", "pooled", n_clusters)
    # footer: DV moments so a reader can judge coefficient magnitudes
    footer = pd.DataFrame([{
        "model": "daily_clustered", "underlying_name": "pooled",
        "term": "_DV_MEAN_SD_", "coef": float(reg[dep].mean()),
        "std_err": float(reg[dep].std()), "t": np.nan, "p_value": np.nan,
        "nobs": len(reg), "r2": np.nan, "n_clusters": n_clusters, "dep_var": dep,
    }])
    return pd.concat([out, footer], ignore_index=True)


def run_q2_iv(
    panel: pd.DataFrame,
    cluster_cols: tuple[str, str] = ("id", "date"),
    min_obs: int = 50,
) -> pd.DataFrame:
    """
    P5 identification-clean alternative: regress close-based implied vol on the
    liquidity proxies and controls. The DV (iv_close) is NOT a deterministic
    function of realized vol, so the liquidity coefficient is not mechanically
    tied to the benchmark construction. realized_vol_21 stays as a control for
    the level of volatility.
    """
    if "iv_close" not in panel.columns:
        return pd.DataFrame([{"model": "iv", "term": "MISSING_iv_close",
                              "coef": np.nan}])
    df = build_q2_dependent(panel)
    reg = df.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["iv_close", "daily_spread_proxy", "no_trade", "moneyness", "T", "realized_vol_21"]
    )
    if len(reg) < min_obs:
        return pd.DataFrame([{"model": "iv", "underlying_name": "pooled",
                              "term": "INSUFFICIENT_DATA", "nobs": len(reg)}])
    formula = ("iv_close ~ daily_spread_proxy + no_trade + moneyness + T "
               "+ realized_vol_21 + C(underlying_name)")
    cluster_list = [c for c in cluster_cols if c in reg.columns]
    n_clusters = int(reg[cluster_list[0]].nunique()) if cluster_list else 0
    model = _fit_clustered(formula, reg, cluster_list)
    return _tidy(model, "iv_clustered", "pooled", n_clusters)


# --------------------------------------------------------------------------- #
# P6 — Q3 IV quality on full sample AND non-stale subset
# --------------------------------------------------------------------------- #
def _smile_roughness(g: pd.DataFrame, iv_col: str) -> float:
    """Mean absolute second difference of IV across moneyness within date/maturity."""
    vals = []
    keys = ["date", "maturity"] if "maturity" in g.columns else ["date"]
    for _, s in g.dropna(subset=[iv_col, "moneyness"]).groupby(keys):
        s = s.sort_values("moneyness")
        if len(s) >= 3:
            vals.append(np.abs(np.diff(s[iv_col].to_numpy(), n=2)).mean())
    return float(np.mean(vals)) if vals else np.nan


def run_q3_iv_quality(panel: pd.DataFrame, min_paired: int = 30) -> pd.DataFrame:
    """
    Replacement for src/iv_quality.py output.

    Reports roughness/improvement on the FULL sample and on the NON-STALE
    subset, so the 'midpoint is cleaner' claim is not just an artefact of ~46%
    stale closes.

    Output columns:
        underlying_name, paired_obs, paired_obs_nonstale,
        roughness_close, roughness_mid, roughness_improvement,
        roughness_close_ns, roughness_mid_ns, roughness_improvement_ns,
        stale_close_share, data_sufficiency
    """
    if "stale_close" not in panel.columns:
        panel = panel.assign(stale_close=False)
    rows = []
    paired = panel.dropna(subset=["iv_close", "iv_mid", "moneyness"])
    for name, g in paired.groupby("underlying_name"):
        ns = g[~g["stale_close"].fillna(False)]
        rc, rm = _smile_roughness(g, "iv_close"), _smile_roughness(g, "iv_mid")
        rc_ns, rm_ns = _smile_roughness(ns, "iv_close"), _smile_roughness(ns, "iv_mid")
        suff = "OK" if len(g) >= min_paired else "INSUFFICIENT_DATA"
        if len(ns) < min_paired:
            suff = "OK_FULL_ONLY" if suff == "OK" else suff
        rows.append({
            "underlying_name": name,
            "paired_obs": int(len(g)),
            "paired_obs_nonstale": int(len(ns)),
            "roughness_close": rc, "roughness_mid": rm,
            "roughness_improvement": (rc - rm) if (pd.notna(rc) and pd.notna(rm)) else np.nan,
            "roughness_close_ns": rc_ns, "roughness_mid_ns": rm_ns,
            "roughness_improvement_ns": (rc_ns - rm_ns) if (pd.notna(rc_ns) and pd.notna(rm_ns)) else np.nan,
            "stale_close_share": float(g["stale_close"].fillna(False).mean()),
            "data_sufficiency": suff,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# P8 — parity / no-arbitrage violation rate with rate sensitivity
# --------------------------------------------------------------------------- #
def parity_rate_sensitivity(
    panel: pd.DataFrame,
    parity_violation_fn,
    r_grid: tuple[float, ...] = (0.28, 0.34, 0.40),
) -> pd.DataFrame:
    """
    Wrap the EXISTING parity routine and report how the violation rate moves with
    the assumed risk-free rate and with stale-close exclusion, so the 24% figure
    is not read as pure friction while Main_DataBase.xlsx is missing.

    `parity_violation_fn(panel_with_r)` must return a frame/Series indicating a
    boolean violation per row (adapt to the real src/parity.py interface).

    Output columns:
        underlying_name, r, sample, n, violation_rate
    """
    if "stale_close" not in panel.columns:
        panel = panel.assign(stale_close=False)
    out = []
    for r in r_grid:
        p = panel.copy()
        p["r"] = r
        viol = parity_violation_fn(p)
        viol = pd.Series(np.asarray(viol).astype(bool), index=p.index)
        for sample, mask in (("all", pd.Series(True, index=p.index)),
                             ("non_stale", ~p["stale_close"].fillna(False))):
            sub = p[mask]
            v = viol[mask]
            for name, idx in sub.groupby("underlying_name").groups.items():
                vv = v.loc[idx]
                out.append({"underlying_name": name, "r": r, "sample": sample,
                            "n": int(len(vv)),
                            "violation_rate": float(vv.mean()) if len(vv) else np.nan})
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- #
# P7 — generic phantom-group guard (use before any output groupby)
# --------------------------------------------------------------------------- #
def drop_unmapped_underlyings(df: pd.DataFrame, col: str = "underlying_name") -> pd.DataFrame:
    """Remove rows whose underlying_name is missing/blank so no phantom NaN group
    leaks into output tables. Prefer fixing the mapping in io_load/lob first."""
    if col not in df.columns:
        return df
    s = df[col].astype("string").str.strip()
    return df[s.notna() & (s != "")].copy()
