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

## Price Discovery Daily
| underlying_name | nobs | peak_lag | peak_corr | granger_underlying_to_option_p | granger_option_to_underlying_p | data_sufficiency |
| --- | --- | --- | --- | --- | --- | --- |
| اهرم | 372 | 0 | -0.13281008040549738 | 0.010993365632393797 | 0.1740479498970981 | OK |

## Data Sufficiency
| underlying_name | panel_rows | contracts | lob_panel_rows | q3_status |
| --- | --- | --- | --- | --- |
| اهرم | 41178 | 450 | 467 | OK |

## Notes
- Dividend yield is set to q=0 as specified.
- Daily Q2 uses realized-volatility Black-Scholes deviations and daily high-low spread proxies.
- LOB-heavy claims are flagged when midpoint pairs or synchronized intraday data are too sparse.