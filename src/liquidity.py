from __future__ import annotations

import numpy as np
import pandas as pd


def liquidity_tables(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = panel.copy()
    contract = df.groupby(["underlying_name", "id", "symbol"]).agg(
        rows=("id", "size"),
        no_trade_rate=("no_trade", "mean"),
        mean_volume=("volume", "mean"),
        median_value=("value", "median"),
        mean_hl_spread=("daily_hl_spread_proxy", "mean"),
        mean_amihud=("amihud_daily", "mean"),
        lob_days=("mid", lambda x: x.notna().sum()),
        mean_rel_spread=("rel_spread", "mean"),
        median_depth=("depth_total", "median"),
    ).reset_index()
    daily = df.groupby(["underlying_name", "date"]).agg(
        option_rows=("id", "size"),
        no_trade_rate=("no_trade", "mean"),
        total_volume=("volume", "sum"),
        mean_hl_spread=("daily_hl_spread_proxy", "mean"),
        mean_amihud=("amihud_daily", "mean"),
        lob_obs=("mid", lambda x: x.notna().sum()),
        mean_rel_spread=("rel_spread", "mean"),
        median_depth=("depth_total", "median"),
    ).reset_index()
    rank = df.groupby("underlying_name").agg(
        contracts=("id", "nunique"),
        rows=("id", "size"),
        no_trade_rate=("no_trade", "mean"),
        total_volume=("volume", "sum"),
        mean_hl_spread=("daily_hl_spread_proxy", "mean"),
        mean_amihud=("amihud_daily", "mean"),
        lob_days=("mid", lambda x: x.notna().sum()),
        mean_rel_spread=("rel_spread", "mean"),
        median_depth=("depth_total", "median"),
    ).reset_index()
    rank["liquidity_score"] = (
        rank["no_trade_rate"].rank(ascending=True, pct=True)
        + rank["mean_hl_spread"].fillna(rank["mean_hl_spread"].median()).rank(ascending=True, pct=True)
        + rank["total_volume"].rank(ascending=False, pct=True)
    )
    rank["liquidity_rank"] = rank["liquidity_score"].rank(method="dense").astype(int)
    return contract, daily, rank.sort_values("liquidity_rank")
