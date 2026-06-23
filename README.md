# Iranian Equity-Option Research Pipeline

This folder implements the study described in `../RESEARCH_SPEC.md`.

## Run

**PowerShell (Windows):**
```powershell
cd paper
python run_all.py
pytest -q
```

**POSIX (Linux / macOS):**
```bash
cd paper
PYTHONDONTWRITEBYTECODE=1 python run_all.py
pytest -q
```

Inputs are read from `config.yaml:data_root` and are never modified. Outputs are written under `paper/outputs/`.

## Main Outputs

- `outputs/panel_daily.parquet`: canonical daily option panel.
- `outputs/tables/*.csv`: tables for descriptive liquidity, parity, price discovery, liquidity premium, IV quality, and data sufficiency.
- `outputs/figures/*.png`: figures for no-trade term structure, lead-lag (per call/put type), parity/liquidity, liquidity ranking, intraday LOB profile, and IV close-vs-mid comparisons when available.
- `outputs/run_report.md`: concise machine-generated digest for manuscript drafting.

## Key Correction Notes

- **Q1 lead-lag** is computed separately for calls and puts. A `peak_lag=0` result means the strongest association is contemporaneous; it should not be described as "the underlying leads."
- **Q2 regression** uses a winsorized, tick-floored relative deviation as the DV with two-way cluster-robust standard errors. Settings are tunable in `config.yaml` under `[regression]`.
- **Intraday information share** columns hold NaN + `INSUFFICIENT_DATA` until synchronized underlying-option midpoints are available. The `lob_file_option_share` column is a data-coverage descriptor only.
- **Q3 IV quality** reports roughness on both the full sample and the non-stale subset. See `roughness_improvement_ns` for the identification-clean figure.
- **Parity violation rate** is reported across a grid of r values (0.28, 0.34, 0.40) and for stale/non-stale subsamples in `parity_violations_sensitivity.csv`.

## Interpretation

The pipeline is deliberately conservative. It computes daily-data results for every underlying found in the files, and it marks LOB-heavy or regression-heavy claims as insufficient when the available local data cannot support them. If the full six-underlying dataset and macro workbook are added later, the same code will discover the extra underlyings, instruments, dates, and risk-free-rate history from disk.
