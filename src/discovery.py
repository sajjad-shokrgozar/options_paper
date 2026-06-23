from __future__ import annotations

import numpy as np
import pandas as pd
from .fixes_reference import (
    price_discovery_daily_by_type,
    intraday_information_share,
    lob_file_option_share,
    drop_unmapped_underlyings,
)


def price_discovery_daily(panel: pd.DataFrame, max_lag: int = 5) -> pd.DataFrame:
    """
    P1: lead-lag computed SEPARATELY for calls and puts (type-consistent series).

    The old implementation selected the single nearest-ATM contract per date and
    pooled calls and puts, causing the option-return series to randomly switch
    sign regime day to day (negative peak_corr = -0.13 was a symptom of this).

    Now each (underlying_name, opt_type) gets its own volume-weighted near-ATM
    return series; puts are also reported sign-flipped so both types have the
    same expected contemporaneous sign as the underlying.

    peak_lag = 0 means the strongest association is contemporaneous, i.e. no
    daily lead-lag was detected. Do not describe this as "the underlying leads."
    """
    return price_discovery_daily_by_type(panel, max_lag=max_lag)


def intraday_stub(lob_daily: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    P2/P7: honest data-coverage descriptor + guarded information-share estimate.

    The old code computed len(opt) / (len(opt) + len(und)) and mislabelled it
    option_information_share_mid. That is a file-count ratio, not a Hasbrouck
    or Gonzalo-Granger share.

    Now:
      - lob_file_option_share: DATA-COVERAGE descriptor only (fraction of LOB
        rows belonging to option instruments).
      - gg_option_share: real GG component share, returned as NaN with
        INSUFFICIENT_DATA until synchronized underlying-option intraday midpoints
        can be built. Never a placeholder number.

    P7: drop_unmapped_underlyings removes the phantom NaN-named group that arose
    because the underlying's own LOB folders had no underlying_name assigned.
    """
    if lob_daily is not None and not lob_daily.empty:
        lob_daily = drop_unmapped_underlyings(lob_daily)  # P7

    coverage = lob_file_option_share(lob_daily)
    # No synchronized underlying-option intraday frame available yet.
    # intraday_information_share(None) returns a single "ALL" placeholder row;
    # we use a LEFT join so only real underlyings from coverage are kept.
    is_share = intraday_information_share(None)

    if coverage.empty:
        return is_share

    out = coverage.merge(
        is_share[["underlying_name", "gg_option_share", "data_sufficiency"]],
        on="underlying_name",
        how="left",
    )
    # Fill missing data_sufficiency for underlyings not in is_share
    if "data_sufficiency" not in out.columns:
        out["data_sufficiency"] = "INSUFFICIENT_DATA"
    else:
        out["data_sufficiency"] = out["data_sufficiency"].fillna("INSUFFICIENT_DATA")
    if "gg_option_share" not in out.columns:
        out["gg_option_share"] = float("nan")
    return out


def cross_section(
    daily: pd.DataFrame,
    intraday: pd.DataFrame,
    ranking: pd.DataFrame,
    q2_by: pd.DataFrame,
) -> pd.DataFrame:
    # P1: daily now has one row per (underlying_name, opt_type).
    # Use calls for the cross-section summary (positive expected sign).
    if "opt_type" in daily.columns:
        daily_cs = daily[daily["opt_type"].eq("call")]
    else:
        daily_cs = daily

    keep_daily = ["underlying_name", "peak_corr", "data_sufficiency"]
    if "peak_corr_signed" in daily_cs.columns:
        keep_daily.append("peak_corr_signed")

    out = ranking[["underlying_name", "liquidity_rank", "no_trade_rate"]].merge(
        daily_cs[keep_daily], on="underlying_name", how="left"
    )

    if intraday is not None and not intraday.empty:
        keep_intra = ["underlying_name"]
        for col in ("lob_file_option_share", "gg_option_share", "data_sufficiency"):
            if col in intraday.columns:
                keep_intra.append(col)
        out = out.merge(
            intraday[keep_intra].rename(columns={"data_sufficiency": "intraday_sufficiency"}),
            on="underlying_name",
            how="left",
        )

    prem = (
        q2_by[q2_by["term"].eq("daily_spread_proxy")][["underlying_name", "coef", "p_value"]]
        .rename(columns={"coef": "liquidity_premium_slope", "p_value": "liquidity_premium_p"})
    )
    return out.merge(prem, on="underlying_name", how="left")
