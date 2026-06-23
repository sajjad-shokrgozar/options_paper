# Iranian Equity-Option Research Pipeline

This folder implements the study described in `../RESEARCH_SPEC.md`.

## Run

```powershell
cd paper
python run_all.py
pytest -q
```

Inputs are read from `config.yaml:data_root` and are never modified. Outputs are written under `paper/outputs/`.

## Main Outputs

- `outputs/panel_daily.parquet`: canonical daily option panel.
- `outputs/tables/*.csv`: tables for descriptive liquidity, parity, price discovery, liquidity premium, IV quality, and data sufficiency.
- `outputs/figures/*.png`: figures for no-trade term structure, lead-lag, parity/liquidity, liquidity ranking, intraday LOB profile, and IV close-vs-mid comparisons when available.
- `outputs/run_report.md`: concise machine-generated digest for manuscript drafting.

## Interpretation

The pipeline is deliberately conservative. It computes daily-data results for every underlying found in the files, and it marks LOB-heavy or regression-heavy claims as insufficient when the available local data cannot support them. If the full six-underlying dataset and macro workbook are added later, the same code will discover the extra underlyings, instruments, dates, and risk-free-rate history from disk.
