# FIXES_FOR_CODEX.md

Correction spec for the Iranian equity-option research pipeline (`paper/`).

This file lists defects found by reviewing the current code against its own
outputs. Each item gives the **location**, the **defect**, the **required fix**,
and an **acceptance check** that must pass after the change. Do not change the
public output schema beyond what each item requires. Inputs under `data_root`
remain read-only. Keep the "discover everything from disk" design — no
hardcoding of `اهرم` or of six underlyings.

Work in priority order. Items P1–P3 invalidate headline results and must be
fixed first. P4–P6 are correctness/robustness. P7+ are hygiene.

---

## How to use the reference implementation

A companion file **`fixes_reference.py`** ships with this spec. It contains
ready, importable functions for the substantive items. **Use these functions to
replace the broken logic** rather than re-deriving them:

| Item | Function(s) in `fixes_reference.py` | Replaces in `paper/src/` |
| --- | --- | --- |
| P1 | `price_discovery_daily_by_type` | `discovery.py: price_discovery_daily` |
| P2 | `intraday_information_share`, `lob_file_option_share` | `discovery.py: intraday_stub` |
| P3 | `build_q2_dependent`, `run_q2_clustered` | `regression.py: run_q2` (DV) |
| P4 | `_fit_clustered` (used inside `run_q2_*`) | every `.fit(cov_type="HC1")` |
| P5 | `run_q2_iv` | new identification-clean Q2 spec |
| P6 | `run_q3_iv_quality`, `_smile_roughness` | `iv_quality.py` |
| P7 | `drop_unmapped_underlyings` | guard before output `groupby` |
| P8 | `parity_rate_sensitivity` | wraps `parity.py` |

Rules when wiring it in:
1. Copy `fixes_reference.py` into `paper/src/` (or import it from there). Do not
   leave it as a stray top-level script.
2. The functions assume the existing panel column names. If a real column name
   differs, **rename at the call site**, do not silently change function logic.
3. Keep every `data_sufficiency` flag the functions emit. Where a function
   returns NaN + a flag, that is the intended behaviour — do not backfill a
   number.
4. After wiring, delete the old broken bodies so they cannot be called by
   accident, and update `run_all.py` to call the new functions and write the new
   columns.
5. `intraday_information_share` needs a synchronized paired-midpoint frame
   (`underlying_name, ts, under_mid, opt_mid`). If you cannot build it from the
   LOB tree yet, call it with an empty frame so it returns INSUFFICIENT_DATA, and
   use `lob_file_option_share` only as a coverage descriptor. Never resurrect the
   old file-count ratio under an `*information_share*` name.

Each item below still states the defect and the acceptance check; the reference
function is the expected implementation of the "Required fix."

---

## P1 — Q1 lead-lag uses an incoherent, type-switching option-return series

**Location:** `src/discovery.py`, `price_discovery_daily()`.

**Defect:** Per date the code keeps the single contract closest to ATM via
`(moneyness - 1).abs().idxmin()`, then takes the median option return. But
`moneyness` is defined as `S/K` for calls and `K/S` for puts (both ≈ 1 at ATM),
so the selected contract can be a **call on one day and a put on the next**.
Put returns move opposite to the underlying, so the constructed option-return
series randomly switches sign regime day to day. This is the direct cause of the
**negative** `peak_corr = -0.13`, which is economically impossible for a clean
underlying-vs-option lead-lag and signals a contaminated series. The Granger
"underlying leads option" conclusion is built on this broken series.

**Required fix:**
1. Compute lead-lag **separately for calls and puts** (`opt_type` already exists
   on the panel). Never pool the two types into one return series.
2. For each type, build a per-date representative option return from a stable,
   type-consistent selection — e.g. the volume-weighted mean return of the
   near-ATM band (|moneyness − 1| ≤ 0.05) for that type, not a single
   switching contract. If the band is empty that date, return NaN for that date.
3. For puts, either run the analysis on **put returns vs underlying returns**
   and expect a negative contemporaneous sign, or convert to a
   delta-signed/synthetic-underlying return so that the expected lead-lag sign is
   positive for both types. State which convention you use in a comment.
4. Output one row per `(underlying_name, opt_type)` in
   `price_discovery_daily.csv`, adding an `opt_type` column. Update
   `cross_section()` and any figure that consumes this table accordingly.

**Acceptance check:**
- For calls, contemporaneous `peak_corr` is **positive** (a thin market can still
  be noisy, but a robustly negative call peak_corr means the series is still
  wrong).
- No single row mixes calls and puts.
- `peak_lag` and the Granger p-values are reported per type.

**Reporting note for the manuscript:** `peak_lag = 0` means the strongest
association is **contemporaneous**, i.e. no daily lead-lag was detected. Do not
describe this as "the underlying leads." The handoff text overstates this; phrase
it as "no daily-frequency lead-lag is detectable; intraday data would be needed
to test leadership."

---

## P2 — The intraday "information share" is a fabricated metric

**Location:** `src/discovery.py`, `intraday_stub()`; column
`option_information_share_mid` in `price_discovery_intraday.csv` and
`price_discovery_cross_section.csv`.

**Defect:** The value is computed as `len(opt) / (len(opt) + len(und))` — the
fraction of LOB **file rows** that belong to option instruments rather than the
underlying. This has nothing to do with Hasbrouck or Gonzalo-Granger information
shares. Because the underlying's own LOB folders are nearly empty, the ratio
collapses to ~0.99 mechanically. Carrying a column literally named
`option_information_share_mid` risks it being read as "options capture 99% of
price discovery."

**Required fix (choose one):**
- **Preferred:** Implement a real reduced-form information-share proxy only when
  synchronized intraday underlying-and-option midpoints exist: align LOB
  midpoints of the underlying and a near-ATM option on a common intraday grid,
  fit a bivariate VECM, and report Gonzalo-Granger component shares. If the data
  cannot support estimation (too few synchronized snapshots), output
  `data_sufficiency = "INSUFFICIENT_DATA"` and leave the share **NaN** — do not
  emit a placeholder number.
- **Minimum acceptable:** Delete the fake metric entirely. Rename the column to
  `lob_file_option_share` and document it as a **data-coverage** descriptor, not
  a price-discovery quantity. Remove it from `price_discovery_cross_section.csv`.

**Acceptance check:**
- No column named `*information_share*` ever holds the file-count ratio.
- Where a true share is not estimable, the cell is NaN with an explicit
  insufficiency flag.

---

## P3 — Q2 dependent variable explodes; coefficients are not interpretable

**Location:** `src/regression.py`, `run_q2()`.
`pricing_deviation = (close - bs_price_rv21).abs() / close.replace(0, NaN)`.

**Defect:** This relative deviation has a near-zero denominator for thin, deep-OTM
options whose close is a few rials, producing an extreme right tail. With no
winsorization the OLS is dominated by these outliers, which is why the intercept
and slopes are in the **thousands** (e.g. `no_trade ≈ +2676`) on a quantity that
should be O(1). A `no_trade` coefficient of 2676 on a "relative deviation" means
+267,600%, which is nonsensical and confirms the DV/scale is broken. The reported
`R² = 0.28` and the "highly significant" verdict are artifacts.

**Required fix:**
1. Build the DV deliberately and document units:
   - Compute the absolute relative deviation `dev = |close − bs| / max(close, tick)`
     using a floor (one tick / one rial) instead of dividing by raw close.
   - **Winsorize** `dev` at the 1st/99th percentiles (within underlying) before
     regression, or use a log1p transform. State which.
   - Optionally also report a level-deviation specification `|close − bs|` in
     rials as a robustness column, clearly labelled, so magnitudes are
     comparable.
2. Drop rows where `close` is below a sane minimum tick, and rows flagged stale,
   from the main spec; keep them only in a robustness run.
3. Re-examine sign/magnitude after winsorization; if `no_trade` and the spread
   proxy remain positive and significant, the liquidity-premium claim survives —
   if not, report that honestly.

**Acceptance check:**
- Winsorized-DV regression has coefficients of plausible magnitude relative to
  the DV's own standard deviation (report the DV mean/SD in the table footer).
- The table records the floor, the winsorization bounds, and the row count
  dropped.

---

## P4 — Standard errors are not clustered

**Location:** `src/regression.py` — all `.fit(cov_type="HC1")` calls.

**Defect:** HC1 corrects heteroskedasticity only. The panel has ~450 contracts
over many overlapping dates (41,178 rows); residuals are strongly correlated
within contract and within date. HC1 leaves t-stats massively inflated — hence
`t ≈ 56` and exact `p_value = 0.0` (and `liquidity_premium_p = 0.0` in the
cross-section), which are not credible.

**Required fix:**
- Use cluster-robust covariance. With `statsmodels`, refit with
  `cov_type="cluster"` and `cov_kwds={"groups": <contract id>}`; if feasible,
  two-way cluster on contract **and** date (Driscoll-Kraay via
  `cov_type="nw-groupsum"` with the date group is an acceptable alternative for
  the time dimension).
- Apply the same clustering to the daily, LOB, by-underlying, and interaction
  models.

**Acceptance check:**
- No regression reports `p_value` of exactly `0.0`; very small p-values print in
  scientific notation but the SEs reflect the clustered variance.
- The table footer names the clustering dimension and the number of clusters.

---

## P5 — Q2 identification confounds the implied-realized vol premium with liquidity

**Location:** `src/regression.py` (DV built from `bs_price_rv21`) and
`src/pricing_bs.py` (benchmark price uses realized vol).

**Defect:** The benchmark price is BS evaluated at **realized** vol
(`realized_vol_21`), and `realized_vol_21` is also a regressor. So
`|close − bs_price_rv21|` mixes (a) the implied-minus-realized volatility premium
with (b) liquidity frictions. Attributing the whole deviation to liquidity is not
identified, and putting `realized_vol_21` on both sides is mechanically awkward.

**Required fix:**
- Prefer an IV-based deviation target that does not bake realized vol into the
  benchmark: e.g. regress **`iv_close`** (or the close-vs-mid IV gap from Q3) on
  the liquidity proxies and controls, instead of a realized-vol BS price error.
- If you keep a price-error DV, add the contemporaneous realized vol **and** an
  implied-vol level control so the liquidity coefficient is net of the vol
  premium, and stop using the same realized-vol series to both build the
  benchmark and act as a control without comment. Document the choice.

**Acceptance check:**
- The main Q2 specification's DV is not a deterministic function of a right-hand
  variable.
- A short note in the run report states how the vol premium is separated from
  liquidity.

---

## P6 — Q3 improvement may be mechanically driven by stale closes

**Location:** `src/iv_quality.py`; output `q3_iv_quality.csv`
(`stale_close_share = 0.46`).

**Defect:** With ~46% of closes stale, the close-IV smile is rough largely
because stale prices are noisy; the midpoint smile then looks smoother almost by
construction. The headline "midpoint IV is cleaner" is partly tautological.

**Required fix:**
- Recompute `roughness_close`, `roughness_mid`, and `roughness_improvement` on
  the **non-stale** subset (using the existing stale-close flag), and report both
  the full-sample and non-stale-subset numbers side by side.
- Add the paired-observation count for the non-stale subset; flag
  `INSUFFICIENT_DATA` if it falls below the existing threshold.

**Acceptance check:**
- `q3_iv_quality.csv` has columns for full-sample and non-stale-subset roughness
  and improvement.
- The manuscript claim is supported only if improvement persists on the non-stale
  subset.

---

## P7 — Phantom empty-name underlying group

**Location:** `src/discovery.py`, `intraday_stub()`
(`groupby("underlying_name", dropna=False)`); visible as the blank-name row with
160 LOB days in `price_discovery_intraday.csv`.

**Defect:** The underlying's own LOB folders carry `opt_type = "underlying"` and
no `underlying_name`, so a NaN-named phantom group leaks into the cross-section.

**Required fix:**
- Map underlying LOB folders to their `underlying_name` in `io_load`/`lob` so the
  underlying's own book is attributed correctly, **or** drop rows with missing
  `underlying_name` before any groupby that feeds an output table
  (`dropna=True`).
- Audit every `groupby(..., dropna=False)` in the codebase for the same leak.

**Acceptance check:**
- No output table contains a row with empty/blank `underlying_name`.

---

## P8 — Parity / no-arbitrage violation rate is contaminated by the flat fallback rate

**Location:** `src/parity.py`; `r` filled with the 0.34 default when
`Main_DataBase.xlsx` is absent.

**Defect:** A single constant `r = 0.34` across the whole sample, plus stale
closes, inflate the 24% bound-violation rate; it cannot be cleanly attributed to
frictions.

**Required fix:**
- Keep the fallback but add a sensitivity column: recompute violation rates over
  a small grid of `r` (e.g. 0.28, 0.34, 0.40) and report how the rate moves, so
  the reader sees how much is rate-driven.
- Exclude stale-close rows from the headline violation rate and report them
  separately.
- Surface in the run report that this metric is rate-sensitive until the macro
  workbook is supplied.

**Acceptance check:**
- `parity_violations.csv` (or a companion table) shows violation rate as a
  function of `r` and a stale/non-stale split.

---

## P9 — Hygiene and reproducibility

- **README run command** is PowerShell-only. Add a POSIX equivalent
  (`PYTHONDONTWRITEBYTECODE=1 python run_all.py`) so the pipeline runs on
  Linux/macOS.
- **pytest was never actually executed** in the recorded run ("not installed").
  Pin `pytest` in requirements and make `run_all.py` (or CI) fail loudly if tests
  are skipped, so the validation claims are real.
- **`grangercausalitytests(..., verbose=False)`** is deprecated in recent
  statsmodels; switch to capturing the return dict without the `verbose` kwarg to
  avoid future breakage.
- Add a `winsorize`/`floor`/`cluster` settings block to `config.yaml` so the P3
  and P4 choices are transparent and tunable rather than hardcoded.

---

## Global acceptance for this round

After all fixes, re-run and confirm in `run_report.md`:
1. Q1 reports per-type lead-lag with a plausible call sign and the lead-lag
   framed as "contemporaneous / no daily lead detected."
2. No fabricated information-share number anywhere.
3. Q2 coefficients are of interpretable magnitude with clustered SEs and no exact
   zero p-values.
4. Q3 improvement reported full-sample **and** non-stale.
5. No blank-named underlying row.
6. Parity violation rate shown with rate sensitivity.
7. Every still-thin result keeps its `data_sufficiency` flag; do not manufacture
   significance where the single-underlying / missing-macro data cannot support
   it.

Do not delete the honest limitation flags already present — extend them.

Finally: the substantive fixes (P1–P8) must be implemented via the functions in
`fixes_reference.py`. If you deviate from a reference function, say why in the
run report and show that the acceptance check for that item still passes.
