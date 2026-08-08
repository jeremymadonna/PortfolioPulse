# PortfolioPulse

**Credit portfolio monitoring and risk analytics on a real loan-level panel.**

A reporting pipeline over 50,000 US residential mortgages observed quarterly
from 2000 to 2015 — through the housing boom, the crash, and the recovery. It
builds a star schema in DuckDB, computes every metric in versioned SQL, and
surfaces portfolio size, delinquency, roll rates, vintage curves and default
exposure by segment.

> **Status:** Phases 1–2 complete (ingestion, star schema, six reporting views).
> Phases 3–7 in progress: provisioning, data quality framework, monthly
> commentary, Streamlit dashboard, documentation.

## Why this dataset

The performance file is a genuine monthly panel — one row per loan per period.
Roll rates and vintage analysis are impossible without one, and no snapshot
dataset (Lending Club and friends) can supply it. This is real observed
behaviour, not generated data, so there is no honesty caveat to write.

## Data source and attribution

Built on the **`mortgage` panel dataset**, companion data to *Credit Risk
Analytics: Measurement Techniques, Applications, and Examples in SAS* by Bart
Baesens, Daniel Roesch and Harald Scheule (John Wiley & Sons, 2016), originally
provided by **International Financial Research**. A randomised selection of
loan-level data from US residential mortgage-backed securities portfolios.

All data originates with those authors and International Financial Research.
This project claims no ownership of it and redistributes none of it. The
authors are not affiliated with this project and do not endorse it. Any errors
in derivation, banding or interpretation here are mine, not theirs.

| Source | Used for |
|---|---|
| [creditriskanalytics.net](http://www.creditriskanalytics.net/datasets-downloads.html) | The dataset (`mortgage_csv.rar`) |
| *Credit Risk Analytics* (Wiley, 2016) | Column definitions |
| US Bureau of Labor Statistics unemployment series | Independent check used to recover the calendar |

`data/` is gitignored. The file is freely downloadable, so this is not a hard
legal restriction, but it is third-party companion data to a copyrighted
textbook with no stated redistribution licence. The repo stays reproducible
from instructions rather than by carrying someone else's data.

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Download the data first -- see DATA.md
python src/ingest.py     # build the star schema
python src/views.py      # create the six reporting views
```

## The star schema

| Table | Grain | Rows |
|---|---|---|
| `dim_loan` | one row per loan | 50,000 |
| `fact_loan_quarter` | one row per loan per quarter | 623,732 |
| `fact_credit_event` | one row per defaulted loan | 15,154 |
| `dim_date` | one row per period | 60 |
| `dq_results` | data quality register, appended per run | — |

**The grain is quarterly, not monthly.** A 30-year loan shows
`mat_time - orig_time = 120` — 120 quarters. The fact table is named
`fact_loan_quarter` rather than `fact_loan_month` so the grain cannot be
misread.

## The six reporting views

Every metric is computed in a `.sql` file under `sql/`, never in Pandas. Each
opens with the business question it answers.

| View | Answers |
|---|---|
| `vw_portfolio_summary` | Balance, active loans, average balance, quarter-over-quarter growth, defaults and payoffs |
| `vw_segment_performance` | The same, cut by credit score band, LTV band, property type, occupancy and vintage |
| `vw_delinquency` | Status distribution and default rate, by quarter and segment |
| `vw_roll_rates` | Status at quarter *t* against *t+1*, balance moved, roll rate |
| `vw_vintage_performance` | Cumulative default rate by cohort, indexed on quarters on book |
| `vw_loss_recovery` | Default counts, exposure at default and LTV at default by segment |

## Recovering the calendar

The dataset's `time` column is deliberately deidentified — an integer 1..60 with
no stated calendar meaning. The embedded unemployment and house price series
anchor it:

| Period | Dataset UER | Implied quarter | Actual US UER |
|---|---|---|---|
| 1 | 3.8 | 2000Q2 | 3.9 |
| 14 | 6.2 | 2003Q3 | 6.1 |
| 25 | 4.7 (HPI peaks) | 2006Q2 | 4.6 |
| 39 | 10.0 (UER peaks) | 2009Q4 | 9.9 |
| 60 | 5.7 | 2015Q1 | 5.6 |

**This is a derived inference, not a stated fact.** It is used only for
labelling — every metric is computed on the raw integer period — and
`CALENDAR_ANCHOR = None` in `src/config.py` removes it without changing a
single number.

## What the two cohorts show

Cohorts were chosen from the data, not assumed: lifetime default rate rises
monotonically across origination quarters from 9.3% to 53.2%.

| | 2003Q3 | 2006Q4 |
|---|---|---|
| Loans | 1,427 | 3,822 |
| Avg credit score at origination | 674 | 660 |
| Avg LTV at origination | 79.7 | 80.1 |
| **Lifetime default rate** | **9.3%** | **53.2%** |
| Avg LTV **at default** | 66.1 | 106.7 |
| Avg quarters on book at default | 16.4 | 10.5 |

Interpretation is deliberately left to `docs/Business Insights.md`, which is
filled in after reviewing the analysis rather than written ahead of it.

## What this dataset cannot support

Recorded because it changes what the project can honestly report:

- **No delinquency buckets.** No days-past-due field; a loan is only active,
  defaulted or paid off. Roll rates are status transitions, and because default
  and payoff are terminal there are **no cures** to observe.
- **No recovery, expense or realised-loss amounts.** Loss severity (loss given
  default) cannot be computed and is absent rather than guessed. Exposure at
  default and LTV at default are reported instead.
- **No property state, loan purpose, channel or DTI.** Segmentation is credit
  score band, LTV band, property type and occupancy.
- **Cohorts season to different horizons.** 2006Q4 can be followed to 36
  quarters on book, 2003Q3 to 46. `vw_vintage_performance` carries
  `loans_observed` and `pct_cohort_still_observed` on every row so curves are
  only compared where both cohorts are fully seasoned.

## Data quality

Defects found in the source are reported, never silently cleaned. `dq_results`
records every finding with a run timestamp, severity and row count.

| Finding | Severity | Rows | Handling |
|---|---|---|---|
| Duplicate loan-periods (27 with conflicting balances) | HIGH | 339 | One row kept per loan-period, lower balance |
| Missing mid-panel periods | MEDIUM | 1,582 | Forward-filled, every row flagged `is_forward_filled` |
| Rows dated before stated origination | LOW | few | Excluded from vintage curves |

Forward-filled rows synthesise observations that were never reported, so they
carry a flag and are excluded from roll rates entirely. Macro variables are
never carried forward — they belong to the period, not the loan.

## Mapping to the job posting

| Posting requirement | Where this project answers it |
|---|---|
| Dashboards monitoring credit portfolio performance | Four-page Streamlit dashboard, quarterly trend views *(Phase 6)* |
| Analysis of portfolio performance indicators | Default rate, exposure at default, LTV at default, coverage ratio by segment |
| Interpret data, explain discrepancies, assess implications | Monthly commentary with segment contribution attribution *(Phase 5)*, Business Insights |
| Data quality analysis with governance teams | Validation rules, issue register, data quality score, reconciliation *(Phase 4)* |
| Migration of publications to a new data model | Star schema built from a raw flat source file |
| SQL | Six reporting views using CTEs and window functions (`LAG`, running sums, partitioned shares) |
| Power BI and Tableau | Power BI dashboard from exported marts *(Phase 6)* |

## Licence

Project code: MIT. The dataset it reads is governed by its authors' terms and
is not covered by this licence.
