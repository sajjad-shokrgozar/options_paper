from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .io_load import discover_lob_files, load_lob_day_file


def reduce_lob_snapshots(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    cols = ["instrument_id", "date", "hEven", "refID", "number", "qTitMeDem", "pMeDem", "pMeOf", "qTitMeOf"]
    df = raw[[c for c in cols if c in raw.columns]].copy()
    if df.empty:
        return pd.DataFrame()
    df["number"] = df["number"].astype(int)
    piv = df.pivot_table(index=["instrument_id", "date", "hEven", "refID"], columns="number",
                         values=["pMeDem", "pMeOf", "qTitMeDem", "qTitMeOf"], aggfunc="last")
    piv.columns = [f"{'bid_px' if a=='pMeDem' else 'ask_px' if a=='pMeOf' else 'bid_qty' if a=='qTitMeDem' else 'ask_qty'}_{b}" for a, b in piv.columns]
    out = piv.reset_index().sort_values(["instrument_id", "date", "hEven", "refID"])
    out["bid_px_1"] = out.get("bid_px_1", np.nan)
    out["ask_px_1"] = out.get("ask_px_1", np.nan)
    out["crossed"] = out["ask_px_1"] < out["bid_px_1"]
    out["one_sided"] = (out["ask_px_1"] <= 0) | (out["bid_px_1"] <= 0) | out["ask_px_1"].isna() | out["bid_px_1"].isna()
    out = out[~out["crossed"] & ~out["one_sided"]].copy()
    if out.empty:
        return out
    out["mid"] = (out["bid_px_1"] + out["ask_px_1"]) / 2
    out["spread"] = out["ask_px_1"] - out["bid_px_1"]
    out["rel_spread"] = out["spread"] / out["mid"]
    bq = out.get("bid_qty_1", 0).fillna(0)
    aq = out.get("ask_qty_1", 0).fillna(0)
    out["microprice"] = np.where((bq + aq) > 0, (out["bid_px_1"] * aq + out["ask_px_1"] * bq) / (bq + aq), out["mid"])
    bid_qty_cols = [c for c in out.columns if c.startswith("bid_qty_")]
    ask_qty_cols = [c for c in out.columns if c.startswith("ask_qty_")]
    out["depth_bid"] = out[bid_qty_cols].fillna(0).sum(axis=1) if bid_qty_cols else 0
    out["depth_ask"] = out[ask_qty_cols].fillna(0).sum(axis=1) if ask_qty_cols else 0
    out["depth_total"] = out["depth_bid"] + out["depth_ask"]
    out["OBI"] = np.where(out["depth_total"] > 0, (out["depth_bid"] - out["depth_ask"]) / out["depth_total"], np.nan)
    out["time_hhmmss"] = out["hEven"].astype(int).astype(str).str.zfill(6)
    out["hour"] = out["time_hhmmss"].str[:2].astype(int)
    out["minute"] = out["time_hhmmss"].str[2:4].astype(int)
    return out


def build_lob_daily(cfg: dict, instrument_master: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    files = discover_lob_files(cfg)
    if files.empty:
        return pd.DataFrame(), files
    max_files = int(cfg.get("lob", {}).get("max_files_per_instrument", 8))
    selected = files.sort_values(["instrument_id", "date"]).groupby("instrument_id").head(max_files)
    rows = []
    profiles = []
    for rec in selected.itertuples(index=False):
        raw = load_lob_day_file(rec.path, rec.instrument_id, rec.date)
        red = reduce_lob_snapshots(raw)
        if red.empty:
            rows.append({"instrument_id": rec.instrument_id, "date": rec.date, "lob_snapshots": 0})
            continue
        rows.append({
            "instrument_id": rec.instrument_id,
            "date": rec.date,
            "mid": red["mid"].median(),
            "rel_spread": red["rel_spread"].median(),
            "spread": red["spread"].median(),
            "depth_total": red["depth_total"].median(),
            "OBI": red["OBI"].median(),
            "microprice": red["microprice"].median(),
            "lob_snapshots": len(red),
        })
        prof = red.groupby("hour").agg(rel_spread=("rel_spread", "median"), depth_total=("depth_total", "median")).reset_index()
        prof["instrument_id"] = rec.instrument_id
        prof["date"] = rec.date
        profiles.append(prof)
    daily = pd.DataFrame(rows)
    if not daily.empty:
        daily = daily.merge(instrument_master[["instrument_id", "underlying_name", "opt_type", "strike", "maturity"]], on="instrument_id", how="left")
    profile = pd.concat(profiles, ignore_index=True) if profiles else pd.DataFrame()
    if not profile.empty:
        profile = profile.merge(instrument_master[["instrument_id", "underlying_name", "opt_type"]], on="instrument_id", how="left")
    return daily, profile
