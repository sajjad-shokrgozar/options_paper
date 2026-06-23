from __future__ import annotations

import numpy as np
import pandas as pd


def _roughness(g: pd.DataFrame, col: str) -> float:
    x = g.dropna(subset=[col, "moneyness"]).sort_values("moneyness")[col].values
    if len(x) < 4:
        return np.nan
    return float(np.var(np.diff(x, n=2)))


def iv_quality(panel: pd.DataFrame, ranking: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    paired = panel.dropna(subset=["iv_close", "iv_mid"]).copy()
    rows = []
    min_pairs = cfg.get("lob", {}).get("min_q3_pairs", 30)
    for name, g in panel.groupby("underlying_name"):
        gp = paired[paired["underlying_name"] == name]
        if len(gp) < min_pairs:
            rows.append({"underlying_name": name, "paired_obs": len(gp), "roughness_close": np.nan, "roughness_mid": np.nan,
                         "roughness_improvement": np.nan, "stale_close_share": g["stale_close"].mean(),
                         "data_sufficiency": "INSUFFICIENT_DATA"})
            continue
        rough_rows = []
        for (date, maturity), smile in gp.groupby(["date", "maturity"]):
            rough_rows.append({
                "date": date,
                "maturity": maturity,
                "rough_close": _roughness(smile, "iv_close"),
                "rough_mid": _roughness(smile, "iv_mid"),
            })
        rough = pd.DataFrame(rough_rows)
        rows.append({"underlying_name": name, "paired_obs": len(gp), "roughness_close": rough["rough_close"].median(),
                     "roughness_mid": rough["rough_mid"].median(),
                     "roughness_improvement": rough["rough_close"].median() - rough["rough_mid"].median(),
                     "stale_close_share": gp["stale_close"].mean(), "data_sufficiency": "OK"})
    table = pd.DataFrame(rows)
    imp = table.merge(ranking[["underlying_name", "liquidity_rank", "no_trade_rate"]], on="underlying_name", how="left")
    return table, imp
