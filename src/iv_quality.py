from __future__ import annotations

import numpy as np
import pandas as pd
from .fixes_reference import run_q3_iv_quality


def iv_quality(panel: pd.DataFrame, ranking: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    P6: Q3 IV quality on the FULL sample and the NON-STALE subset.

    The old implementation computed roughness only on the full sample. With
    ~46% stale closes, the close-IV smile was rough largely because of stale
    prices, making the midpoint smile look smoother almost by construction.

    Now roughness_close, roughness_mid, and roughness_improvement are reported
    for both the full sample (_full columns) and the non-stale subset (_ns
    columns). The 'midpoint is cleaner' claim is supported only if improvement
    persists on the non-stale subset.

    Output columns added vs old version:
        paired_obs_nonstale,
        roughness_close_ns, roughness_mid_ns, roughness_improvement_ns
    The data_sufficiency field distinguishes OK / OK_FULL_ONLY / INSUFFICIENT_DATA.
    """
    min_pairs = cfg.get("lob", {}).get("min_q3_pairs", 30)
    table = run_q3_iv_quality(panel, min_paired=min_pairs)
    imp = table.merge(
        ranking[["underlying_name", "liquidity_rank", "no_trade_rate"]],
        on="underlying_name",
        how="left",
    )
    return table, imp
