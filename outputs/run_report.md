# Run Report

- Options rows loaded: 42524
- Underlying rows loaded: 1076
- Canonical panel rows: 41178
- Underlyings discovered: اهرم
- Macro workbook missing/default rate used: True
- LOB daily reductions generated: 3608
- Figures generated: 9

## Liquidity Ranking
| underlying_name | contracts | rows | no_trade_rate | total_volume | mean_hl_spread | mean_amihud | lob_days | mean_rel_spread | median_depth | liquidity_score | liquidity_rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| اهرم | 450 | 41178 | 0.5625819612414396 | 675875200.0 | 0.3278748202857929 | 6.959631200650633e-06 | 467 | 0.9229580614574918 | 147.0 | 3.0 | 1 |

## Price Discovery Daily (per type)
| underlying_name | opt_type | nobs | peak_lag | peak_corr | peak_corr_signed | granger_underlying_to_option_p | granger_option_to_underlying_p | data_sufficiency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| اهرم | call | 365 | -3 | -0.0676618774705608 | -0.0676618774705608 | 0.8355005812974379 | 0.43341441267703107 | OK |
| اهرم | put | 365 | -5 | -0.06439022257794505 | 0.06439022257794505 | 0.9672725520693587 | 0.7806330945464726 | OK |

## Data Sufficiency
| underlying_name | panel_rows | contracts | lob_panel_rows | q3_status |
| --- | --- | --- | --- | --- |
| اهرم | 41178 | 450 | 467 | OK |

## Notes
- Dividend yield is set to q=0 as specified.
- Q1 lead-lag is computed separately for calls and puts (P1 fix). peak_lag=0
  means strongest association is contemporaneous; no daily lead-lag detected.
  Do not describe as 'the underlying leads'.
- Q2 uses winsorized relative deviation (1/99th pct within underlying) as DV,
  with a tick_floor so deep-OTM cheap options do not dominate. Stale-close
  rows are excluded. Standard errors are clustered by (contract, date).
  See config.yaml [regression] for floor, winsorization, and cluster settings.
- No column named *information_share* holds a file-count ratio. lob_file_option_share
  is a data-coverage descriptor only. gg_option_share is NaN / INSUFFICIENT_DATA
  until synchronized intraday underlying-option midpoints are available.
- Q3 roughness reported full-sample AND non-stale subset (P6 fix). The
  'midpoint is cleaner' claim requires improvement to persist on non-stale rows.
- Parity violation rate shown at r in {0.28, 0.34, 0.40} and stale/non-stale
  split (P8 fix). The 24% figure is rate-sensitive until Main_DataBase.xlsx
  is supplied. See parity_violations_sensitivity.csv.
- LOB-heavy claims are flagged INSUFFICIENT_DATA when midpoint pairs or
  synchronized intraday data are too sparse.