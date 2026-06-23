from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd


def save_figures(panel: pd.DataFrame, ranking: pd.DataFrame, discovery_daily: pd.DataFrame, lob_profile: pd.DataFrame, q2_by: pd.DataFrame, q3: pd.DataFrame, out_dir: Path) -> list[str]:
    fig_dir = Path(out_dir) / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    ax = ranking.sort_values("liquidity_rank").plot.bar(x="underlying_name", y="no_trade_rate", legend=False, title="No-trade frequency by underlying")
    ax.set_ylabel("No-trade share")
    p = fig_dir / "no_trade_frequency_by_underlying.png"; plt.tight_layout(); plt.savefig(p, dpi=160); plt.close(); paths.append(str(p))
    term = panel.copy()
    term["ttm_bucket"] = pd.cut(term["T"], bins=[0, 30/365, 90/365, 180/365, 365/365, 10], labels=["0-30d", "31-90d", "91-180d", "181-365d", ">365d"])
    term = term.groupby(["underlying_name", "ttm_bucket"], observed=True).agg(no_trade_rate=("no_trade", "mean")).reset_index()
    if not term.empty:
        fig, ax = plt.subplots()
        for name, g in term.groupby("underlying_name"):
            ax.plot(g["ttm_bucket"].astype(str), g["no_trade_rate"], marker="o", label=name)
        ax.set_title("No-trade term structure")
        ax.set_xlabel("Time to maturity")
        ax.set_ylabel("No-trade share")
        ax.legend(loc="best")
        p = fig_dir / "no_trade_term_structure.png"; plt.tight_layout(); plt.savefig(p, dpi=160); plt.close(); paths.append(str(p))
    ax = discovery_daily.plot.bar(x="underlying_name", y="peak_corr", legend=False, title="Daily lead-lag peak correlation")
    ax.set_ylabel("Peak correlation")
    p = fig_dir / "lead_lag_peak_correlation.png"; plt.tight_layout(); plt.savefig(p, dpi=160); plt.close(); paths.append(str(p))
    if "parity_gap" in panel.columns:
        sample = panel.dropna(subset=["parity_gap", "daily_hl_spread_proxy"]).copy()
        if not sample.empty:
            fig, ax = plt.subplots()
            sc = ax.scatter(
                sample["daily_hl_spread_proxy"],
                sample["parity_gap"],
                c=sample["no_trade"].astype(int),
                cmap="viridis",
                s=12,
                alpha=0.65,
            )
            ax.set_title("Parity gap vs daily spread proxy")
            ax.set_xlabel("Daily high-low spread proxy")
            ax.set_ylabel("Parity gap")
            cbar = fig.colorbar(sc, ax=ax)
            cbar.set_label("No-trade flag")
            p = fig_dir / "parity_gap_vs_liquidity.png"; plt.tight_layout(); plt.savefig(p, dpi=160); plt.close(); paths.append(str(p))
    coef = q2_by[q2_by["term"].eq("daily_spread_proxy")]
    if not coef.empty:
        ax = coef.plot.bar(x="underlying_name", y="coef", yerr="std_err", legend=False, title="Q2 liquidity-premium slope by underlying")
        p = fig_dir / "q2_liquidity_premium_coefficients.png"; plt.tight_layout(); plt.savefig(p, dpi=160); plt.close(); paths.append(str(p))
    if lob_profile is not None and not lob_profile.empty and "hour" in lob_profile:
        prof = lob_profile.groupby("hour").agg(rel_spread=("rel_spread", "median"), depth_total=("depth_total", "median")).reset_index()
        ax = prof.plot(x="hour", y="rel_spread", marker="o", title="Intraday relative spread profile")
        p = fig_dir / "intraday_rel_spread_profile.png"; plt.tight_layout(); plt.savefig(p, dpi=160); plt.close(); paths.append(str(p))
    if q3 is not None and not q3.empty:
        q = q3.dropna(subset=["roughness_improvement"])
        if not q.empty:
            ax = q.plot.scatter(x="no_trade_rate", y="roughness_improvement", title="IV midpoint improvement vs no-trade frequency")
            p = fig_dir / "q3_improvement_vs_liquidity.png"; plt.tight_layout(); plt.savefig(p, dpi=160); plt.close(); paths.append(str(p))
    smiles = panel.dropna(subset=["iv_close", "iv_mid", "moneyness"])
    if not smiles.empty:
        for name, g in smiles.groupby("underlying_name"):
            key_counts = g.groupby(["date", "maturity"]).size().sort_values(ascending=False)
            if key_counts.empty:
                continue
            date, maturity = key_counts.index[0]
            s = g[(g["date"] == date) & (g["maturity"] == maturity)].sort_values("moneyness")
            fig, ax = plt.subplots()
            ax.plot(s["moneyness"], s["iv_close"], marker="o", linestyle="-", label="close IV")
            ax.plot(s["moneyness"], s["iv_mid"], marker="x", linestyle="--", label="mid IV")
            ax.set_title(f"IV smile close vs mid - {name}")
            ax.set_xlabel("Moneyness")
            ax.set_ylabel("Implied volatility")
            ax.legend(loc="best")
            safe_name = "".join(ch if ch.isalnum() else "_" for ch in str(name))
            p = fig_dir / f"iv_smile_close_vs_mid_{safe_name}.png"; plt.tight_layout(); plt.savefig(p, dpi=160); plt.close(); paths.append(str(p))
    cross = ranking.merge(discovery_daily[["underlying_name", "peak_corr"]], on="underlying_name", how="left")
    if not cross.empty:
        fig, ax = plt.subplots()
        ax.scatter(cross["liquidity_rank"], cross["peak_corr"], s=60)
        for _, row in cross.iterrows():
            ax.annotate(str(row["underlying_name"]), (row["liquidity_rank"], row["peak_corr"]))
        ax.set_title("Price discovery vs liquidity rank")
        ax.set_xlabel("Liquidity rank")
        ax.set_ylabel("Lead-lag peak correlation")
        p = fig_dir / "cross_section_discovery_vs_liquidity.png"; plt.tight_layout(); plt.savefig(p, dpi=160); plt.close(); paths.append(str(p))
    return paths
