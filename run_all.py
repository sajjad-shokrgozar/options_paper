from __future__ import annotations

from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from src.config import load_config, ensure_output_dirs
from src.io_load import load_options, load_underlyings, build_instrument_master, discover_lob_files
from src.lob import build_lob_daily
from src.panel import build_panel
from src.pricing_bs import add_pricing_columns
from src.parity import add_parity_and_bounds, run_parity_sensitivity
from src.liquidity import liquidity_tables
from src.regression import run_q2
from src.discovery import price_discovery_daily, intraday_stub, cross_section
from src.iv_quality import iv_quality
from src.figures import save_figures


def write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df is None or df.empty:
        return "_No rows._"
    small = df.head(max_rows).copy()
    small = small.fillna("")
    cols = list(small.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in small.iterrows():
        vals = [str(row[c]).replace("|", "\\|") for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    if len(df) > max_rows:
        lines.append(f"\n_Showing first {max_rows} of {len(df)} rows._")
    return "\n".join(lines)


def main() -> None:
    cfg = load_config(Path(__file__).with_name("config.yaml"))
    ensure_output_dirs(cfg)
    out = Path(cfg["output_dir"])
    tables = out / "tables"

    options = load_options(cfg)
    under = load_underlyings(cfg)
    master = build_instrument_master(options, under)
    lob_daily, lob_profile = build_lob_daily(cfg, master)
    write(lob_daily, tables / "lob_daily_metrics.csv")
    write(lob_profile, tables / "lob_intraday_profile.csv")
    write(discover_lob_files(cfg).groupby("instrument_id").agg(lob_files=("path", "size")).reset_index(), tables / "lob_file_coverage.csv")

    panel, master, under, load_report = build_panel(cfg, lob_daily)
    panel = add_pricing_columns(panel, cfg)
    panel, parity_table = add_parity_and_bounds(panel)
    panel.to_parquet(out / "panel_daily.parquet", index=False)
    write(master, tables / "instrument_master.csv")
    write(parity_table, tables / "parity_violations.csv")

    # P8: parity violation rate as a function of r and stale/non-stale split
    parity_sensitivity = run_parity_sensitivity(panel)
    write(parity_sensitivity, tables / "parity_violations_sensitivity.csv")

    contract_liq, daily_liq, ranking = liquidity_tables(panel)
    write(contract_liq, tables / "contract_liquidity.csv")
    write(daily_liq, tables / "daily_liquidity.csv")
    write(ranking, tables / "underlying_liquidity_ranking.csv")

    # P3/P4/P5: clustered SEs, winsorized DV, identification-clean spec
    q2_daily, q2_lob, q2_by, q2_inter = run_q2(panel, ranking, cfg)
    write(q2_daily, tables / "q2_liquidity_premium_daily.csv")
    write(q2_lob, tables / "q2_liquidity_premium_lob.csv")
    write(q2_by, tables / "q2_by_underlying.csv")
    write(q2_inter, tables / "q2_liquidity_interaction.csv")

    # P1: price_discovery_daily now returns one row per (underlying, opt_type)
    disc_daily = price_discovery_daily(panel)
    disc_intraday = intraday_stub(lob_daily, cfg)
    disc_cross = cross_section(disc_daily, disc_intraday, ranking, q2_by)
    write(disc_daily, tables / "price_discovery_daily.csv")
    write(disc_intraday, tables / "price_discovery_intraday.csv")
    write(disc_cross, tables / "price_discovery_cross_section.csv")

    # P6: iv_quality now reports full-sample and non-stale-subset roughness
    q3, q3_imp = iv_quality(panel, ranking, cfg)
    write(q3, tables / "q3_iv_quality.csv")
    write(q3_imp, tables / "q3_improvement_vs_liquidity.csv")

    figs = save_figures(panel, ranking, disc_daily, lob_profile, q2_by, q3_imp, out)
    suff = []
    for name in sorted(panel["underlying_name"].dropna().unique()):
        suff.append({
            "underlying_name": name,
            "panel_rows": int((panel["underlying_name"] == name).sum()),
            "contracts": int(panel.loc[panel["underlying_name"] == name, "id"].nunique()),
            "lob_panel_rows": int(panel.loc[panel["underlying_name"] == name, "mid"].notna().sum()),
            "q3_status": q3.loc[q3["underlying_name"] == name, "data_sufficiency"].iloc[0] if name in set(q3["underlying_name"]) else "INSUFFICIENT_DATA",
        })
    suff_df = pd.DataFrame(suff)
    write(suff_df, tables / "data_sufficiency_flags.csv")

    report = [
        "# Run Report",
        "",
        f"- Options rows loaded: {load_report['options_rows']}",
        f"- Underlying rows loaded: {load_report['underlying_rows']}",
        f"- Canonical panel rows: {load_report['panel_rows']}",
        f"- Underlyings discovered: {', '.join(load_report['underlyings'])}",
        f"- Macro workbook missing/default rate used: {load_report['macro_missing']}",
        f"- LOB daily reductions generated: {len(lob_daily)}",
        f"- Figures generated: {len(figs)}",
        "",
        "## Liquidity Ranking",
        markdown_table(ranking),
        "",
        "## Price Discovery Daily (per type)",
        markdown_table(disc_daily),
        "",
        "## Data Sufficiency",
        markdown_table(suff_df),
        "",
        "## Notes",
        "- Dividend yield is set to q=0 as specified.",
        "- Q1 lead-lag is computed separately for calls and puts (P1 fix). peak_lag=0",
        "  means strongest association is contemporaneous; no daily lead-lag detected.",
        "  Do not describe as 'the underlying leads'.",
        "- Q2 uses winsorized relative deviation (1/99th pct within underlying) as DV,",
        "  with a tick_floor so deep-OTM cheap options do not dominate. Stale-close",
        "  rows are excluded. Standard errors are clustered by (contract, date).",
        "  See config.yaml [regression] for floor, winsorization, and cluster settings.",
        "- No column named *information_share* holds a file-count ratio. lob_file_option_share",
        "  is a data-coverage descriptor only. gg_option_share is NaN / INSUFFICIENT_DATA",
        "  until synchronized intraday underlying-option midpoints are available.",
        "- Q3 roughness reported full-sample AND non-stale subset (P6 fix). The",
        "  'midpoint is cleaner' claim requires improvement to persist on non-stale rows.",
        "- Parity violation rate shown at r in {0.28, 0.34, 0.40} and stale/non-stale",
        "  split (P8 fix). The 24% figure is rate-sensitive until Main_DataBase.xlsx",
        "  is supplied. See parity_violations_sensitivity.csv.",
        "- LOB-heavy claims are flagged INSUFFICIENT_DATA when midpoint pairs or",
        "  synchronized intraday data are too sparse.",
    ]
    (out / "run_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"panel rows={len(panel)} underlyings={panel['underlying_name'].nunique()} outputs={out}")


if __name__ == "__main__":
    main()
