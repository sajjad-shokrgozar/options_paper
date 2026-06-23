from __future__ import annotations

import numpy as np
import pandas as pd

from .io_load import load_options, load_underlyings, build_instrument_master, load_macro_rates


def build_panel(cfg: dict, lob_daily: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    options = load_options(cfg)
    under = load_underlyings(cfg)
    master = build_instrument_master(options, under)
    opt = options[options["T"] > 0].copy()
    rates = load_macro_rates(cfg, opt["date_dt"])
    under_cols = ["underlying_name", "date", "close", "adj_price", "realized_vol_21", "realized_vol_63", "log_ret", "underlying_no_trade"]
    u = under[under_cols].rename(columns={"close": "S_close", "adj_price": "S", "log_ret": "underlying_log_ret"})
    panel = opt.merge(u, on=["underlying_name", "date"], how="left")
    panel = panel.merge(rates[["date_dt", "r", "macro_rate_source", "risk_free_filled"]], on="date_dt", how="left")
    panel["r"] = panel["r"].fillna(float(cfg.get("risk_free_default", 0.34)))
    panel["moneyness"] = np.where(panel["opt_type"] == "call", panel["S"] / panel["strike"], panel["strike"] / panel["S"])
    panel["option_ret"] = panel.sort_values(["id", "date_dt"]).groupby("id")["close"].pct_change()
    panel["daily_hl_spread_proxy"] = np.where((panel["max"] > 0) & (panel["min"] > 0), 2 * (panel["max"] - panel["min"]) / (panel["max"] + panel["min"]), np.nan)
    panel["amihud_daily"] = np.where(panel["value"] > 0, panel["option_ret"].abs() / panel["value"], np.nan)
    if lob_daily is not None and not lob_daily.empty:
        lob_cols = ["instrument_id", "date", "mid", "rel_spread", "spread", "depth_total", "OBI", "microprice", "lob_snapshots"]
        panel = panel.merge(lob_daily[lob_cols], left_on=["id", "date"], right_on=["instrument_id", "date"], how="left")
    else:
        for c in ["mid", "rel_spread", "spread", "depth_total", "OBI", "microprice", "lob_snapshots"]:
            panel[c] = np.nan
    report = {
        "options_rows": len(options),
        "panel_rows": len(panel),
        "underlying_rows": len(under),
        "underlyings": sorted(panel["underlying_name"].dropna().unique().tolist()),
        "macro_missing": bool((panel["macro_rate_source"] == "default_missing_macro_file").any()) if "macro_rate_source" in panel else True,
    }
    return panel, master, under, report
