# Claude Handoff: Iranian Equity-Option Research Outputs

## What Was Implemented

I implemented the empirical research pipeline described in `../RESEARCH_SPEC.md` inside the `paper/` folder. The implementation is modular, reproducible, and designed to scale from the currently available data to the full six-underlying dataset when it is supplied.

The code reads the raw data from the project root, leaves all inputs unchanged, builds a canonical option panel, computes option-pricing diagnostics, liquidity measures, price-discovery tables, IV-quality measures, and exports CSV tables, figures, a parquet panel, and an auto-generated run report.

The main command is:

```powershell
cd paper
$env:PYTHONDONTWRITEBYTECODE='1'
python run_all.py
```

## Important Data Caveats

The research specification describes six underlyings, but the data currently present in this workspace contains only one discovered underlying:

```text
اهرم
```

The code is not hardcoded to Ahrom. It discovers underlyings, instruments, and LOB folders from the files. If the full six-underlying files are added later, the same pipeline should process them without structural changes.

The macro workbook `Main_DataBase.xlsx` was not present in the project root. Because of that, the pipeline used the configured fallback annual risk-free rate:

```text
r = 0.34
```

This is explicitly flagged in `outputs/run_report.md`. Claude should mention this as a limitation unless the macro workbook is later added and the pipeline rerun.

## Final Validation Summary

The final successful run produced:

```text
panel rows: 41178
underlyings discovered: 1 ['اهرم']
duplicate id-date rows: 0
no-trade rate: 0.5626
panel rows with LOB midpoint: 467
CSV tables: 18
PNG figures: 9
```

Core manual checks passed:

- Black-Scholes price to implied-volatility roundtrip.
- Put-call parity identity under high interest rate.
- Jalali date anchor `1404/01/01 -> 2025-03-21`.
- Option underlying/type parser.
- Five-level LOB reducer: midpoint, spread, and depth.

`pytest` tests are included in `paper/tests/`, but `pytest` was not installed in the current Python environment during the run.

## Code Structure

Main files:

- `run_all.py`: orchestrates the full pipeline.
- `config.yaml`: data root, output directory, day count, annualization factor, risk-free fallback, IV bounds, and LOB settings.
- `src/io_load.py`: loads daily option/underlying files, parses option type and underlying name, discovers the LOB tree, joins macro rates when available.
- `src/lob.py`: reduces raw LOB depth files to per-day midpoint, spread, depth, imbalance, and intraday profiles.
- `src/panel.py`: builds the canonical daily panel.
- `src/pricing_bs.py`: Black-Scholes pricing, vega, no-arbitrage bounds, implied-volatility solver.
- `src/parity.py`: put-call parity residuals and no-arbitrage bound violations.
- `src/liquidity.py`: daily and contract-level liquidity metrics and underlying liquidity ranking.
- `src/regression.py`: Q2 liquidity-premium regressions.
- `src/discovery.py`: Q1 daily lead-lag and LOB proxy information-share summary.
- `src/iv_quality.py`: Q3 close-IV vs midpoint-IV comparison.
- `src/figures.py`: figure generation.

## Main Output Files

### Canonical Panel

`outputs/panel_daily.parquet`

This is the main dataset for manuscript analysis. It has one row per option instrument-date after removing expired observations. It includes:

- Option metadata: instrument id, symbol, strike, maturity, type.
- Underlying mapping: `underlying_name`.
- Time to maturity: `T`.
- Underlying price and realized volatility.
- Option close, no-trade flag, stale-close flag.
- LOB midpoint/spread/depth where available.
- Black-Scholes benchmark price.
- Close-based and midpoint-based implied volatility.
- Put-call parity gap and no-arbitrage violation flags.

Important: final validation confirmed no duplicate `id,date` rows.

### Run Report

`outputs/run_report.md`

This is the best first file for Claude to read. It summarizes:

- Rows loaded.
- Underlyings discovered.
- Whether macro rates came from workbook or fallback.
- Number of LOB reductions.
- Liquidity ranking.
- Daily price-discovery result.
- Data-sufficiency flags.

Claude can use it as the high-level empirical digest.

## Tables

All tables are in `outputs/tables/`.

### `instrument_master.csv`

Maps each instrument id to:

- option symbol,
- underlying name,
- option type,
- strike,
- maturity,
- first and last observed dates.

This is the bridge between daily option data and LOB folder names.

### `lob_file_coverage.csv`

Counts the number of raw LOB day-files discovered per instrument id. Useful for describing data coverage.

### `lob_daily_metrics.csv`

Daily LOB summary by instrument-date. Includes:

- midpoint,
- relative spread,
- absolute spread,
- depth,
- order-book imbalance,
- microprice,
- number of valid snapshots.

This supports Q3 and LOB liquidity diagnostics.

### `lob_intraday_profile.csv`

Intraday hourly profile of relative spread and depth. Used for the intraday spread-profile figure.

### `contract_liquidity.csv`

Contract-level liquidity summary:

- no-trade rate,
- mean volume,
- median value,
- daily high-low spread proxy,
- Amihud proxy,
- LOB days,
- mean LOB relative spread,
- median LOB depth.

Use this for contract-level descriptive statistics.

### `daily_liquidity.csv`

Daily option-chain liquidity by underlying-date:

- option rows,
- no-trade rate,
- total volume,
- high-low spread proxy,
- Amihud proxy,
- LOB observations.

Use this for time-series liquidity descriptions.

### `underlying_liquidity_ranking.csv`

Cross-sectional liquidity ranking by underlying. In the current data it contains only Ahrom, but the structure supports the six-underlying comparison once full data is supplied.

Important current value:

```text
Ahrom no-trade rate: about 56.26%
```

### `parity_violations.csv`

No-arbitrage and put-call parity diagnostics by underlying.

Current Ahrom result:

```text
rows: 41178
bound violations: 9841
bound violation rate: about 23.90%
median absolute parity gap: about 1052.93
95th percentile absolute parity gap: about 13883.26
```

This is useful for the Q2 liquidity/frictions section.

### `price_discovery_daily.csv`

Q1 daily lead-lag table.

Current Ahrom result:

```text
nobs: 372
peak lag: 0
peak correlation: about -0.133
underlying -> option Granger p-value: about 0.011
option -> underlying Granger p-value: about 0.174
status: OK
```

Interpretation for Claude: in this daily Ahrom sample, the underlying-return series shows statistically detectable predictive content for option returns at lag 1 in the implemented Granger test direction, while the reverse direction is not significant at conventional levels. Phrase cautiously because this is a daily proxy and only one underlying is currently available.

### `price_discovery_intraday.csv`

LOB-based intraday price-discovery placeholder/proxy table.

The full Hasbrouck/Gonzalo-Granger information-share system requires richer synchronized underlying-option intraday data. The table reports data sufficiency and a proxy share where possible. Claude should not treat this as a final structural information-share estimate.

### `price_discovery_cross_section.csv`

Combines liquidity ranking, daily price-discovery metrics, intraday proxy status, and Q2 slope. With only one underlying, it is a format-ready table rather than a real cross-sectional test.

### `q2_liquidity_premium_daily.csv`

Main daily Q2 regression table. Dependent variable:

```text
absolute relative pricing deviation
```

The model uses daily liquidity proxies and controls:

- daily high-low spread proxy,
- no-trade flag,
- moneyness,
- time to maturity,
- realized volatility,
- underlying fixed effect where applicable.

Current important coefficients:

```text
no_trade[T.True]: positive, highly significant
daily_spread_proxy: positive, highly significant
```

Interpretation for Claude: in the available Ahrom data, illiquidity proxies are strongly associated with larger Black-Scholes pricing deviations. This supports the liquidity-premium/frictions hypothesis, but should be described as Ahrom-only until the full six-underlying panel is supplied.

### `q2_liquidity_premium_lob.csv`

LOB version of Q2 using:

- relative spread,
- log depth,
- no-trade,
- controls.

This is validation-oriented because LOB midpoint coverage is smaller than daily coverage.

### `q2_by_underlying.csv`

Runs Q2 separately per underlying. Currently only Ahrom is available.

### `q2_liquidity_interaction.csv`

Interaction regression table for liquidity slope by underlying. With only one underlying, this is structurally prepared but not a true cross-sectional interaction test yet.

### `q3_iv_quality.csv`

Q3 midpoint-vs-close implied-volatility quality table.

It compares close-IV and midpoint-IV where both exist. It reports paired observations, smile roughness, improvement, stale-close share, and data-sufficiency status.

Current Ahrom status:

```text
OK
```

### `q3_improvement_vs_liquidity.csv`

Joins Q3 improvement metrics to liquidity rank/no-trade rate. Currently one underlying only, so it is not yet a meaningful cross-sectional scatter test.

### `data_sufficiency_flags.csv`

Compact table showing:

- panel rows,
- number of contracts,
- LOB midpoint rows,
- Q3 status.

Current Ahrom:

```text
panel rows: 41178
contracts: 450
LOB panel rows: 467
Q3 status: OK
```

## Figures

All figures are in `outputs/figures/`.

### `no_trade_frequency_by_underlying.png`

Bar chart of no-trade share by underlying. Currently only Ahrom.

### `no_trade_term_structure.png`

No-trade share by time-to-maturity bucket. Useful for showing whether illiquidity is concentrated in short- or long-maturity contracts.

### `lead_lag_peak_correlation.png`

Daily Q1 lead-lag peak correlation by underlying.

### `parity_gap_vs_liquidity.png`

Scatter of put-call parity gap versus daily high-low spread proxy, colored by no-trade flag. Useful for visually connecting arbitrage deviations to illiquidity.

### `q2_liquidity_premium_coefficients.png`

Coefficient plot for the Q2 daily liquidity-premium slope by underlying.

### `intraday_rel_spread_profile.png`

Hourly LOB relative-spread profile. This can support the microstructure discussion.

### `q3_improvement_vs_liquidity.png`

Scatter of IV roughness improvement versus no-trade frequency. Currently only one underlying, so use cautiously.

### `iv_smile_close_vs_mid_اهرم.png`

Example implied-volatility smile comparing close-based IV and midpoint-based IV for Ahrom on a selected maturity/date with available paired data.

### `cross_section_discovery_vs_liquidity.png`

Prepared cross-sectional discovery-versus-liquidity plot. Currently one point because only Ahrom exists in the data.

## Suggested Manuscript Use

Claude should use the outputs as follows:

1. Use `run_report.md` for the empirical overview.
2. Use `underlying_liquidity_ranking.csv`, `contract_liquidity.csv`, and `daily_liquidity.csv` in the data/descriptive-statistics section.
3. Use `price_discovery_daily.csv` for Q1, but describe it as Ahrom-only given current data.
4. Use `parity_violations.csv` and `q2_*` tables for Q2 liquidity-premium evidence.
5. Use `q3_iv_quality.csv`, `q3_improvement_vs_liquidity.csv`, and the IV smile figure for Q3.
6. Use data-sufficiency flags to avoid overstating results where the full six-underlying or macro data is not yet present.

## Key Limitations To State Clearly

- Current local daily files contain Ahrom only, not all six underlyings described in the research specification.
- Macro workbook is missing, so the risk-free rate uses a transparent fallback of `0.34`.
- True cross-sectional tests across six underlyings are structurally implemented but cannot be substantively interpreted until the full data is supplied.
- LOB-heavy intraday information-share estimates should be treated as data-sufficiency/proxy outputs, not final Hasbrouck or Gonzalo-Granger estimates.

## Bottom-Line Empirical Message From Current Data

With the currently available Ahrom data, the pipeline finds a high no-trade rate, many no-arbitrage/parity deviations, and strong positive relationships between illiquidity proxies and Black-Scholes pricing deviations. These are consistent with a liquidity-frictions interpretation of option pricing in a thin, high-interest-rate market. The cross-underlying claims remain ready to run but not yet evidentially supported until the full six-underlying dataset and macro workbook are added.
