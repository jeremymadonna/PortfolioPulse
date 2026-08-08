# Data Dictionary

Generated from the live warehouse schema, so it cannot drift from the tables.

The grain is **quarterly**. See [Known Assumptions](Known%20Assumptions.md).

## `dim_loan`

50,000 rows.

| Column | Type | Notes |
|---|---|---|
| `loan_id` | BIGINT | Unique loan identifier (`id` in the source). |
| `orig_time` | BIGINT |  |
| `first_time` | BIGINT |  |
| `mat_time` | BIGINT |  |
| `original_term_quarters` | BIGINT |  |
| `origination_vintage` | VARCHAR | Origination cohort, calendar-labelled. |
| `credit_score` | BIGINT | FICO at origination. |
| `original_ltv` | DOUBLE | Loan-to-value at origination. |
| `original_balance` | DOUBLE | Amount lent at origination. Denominator for vintage curves. |
| `original_interest_rate` | DOUBLE |  |
| `property_type` | VARCHAR | Single family / Planned urban / Condominium / Other. 'Other' is the all-zero one-hot category in the source. |
| `occupancy` | VARCHAR | Investor or Owner occupied. |
| `credit_score_band` | VARCHAR | Banded credit score. Primary risk cut. |
| `ltv_band` | VARCHAR | Banded `original_ltv`. |
| `observed_from_origination` | BOOLEAN | FALSE where the loan predates the observation window (left censored). Excluded from vintage curves. |
| `focus_cohort` | VARCHAR | Marks the two contrast cohorts. |

## `fact_loan_quarter`

623,732 rows.

| Column | Type | Notes |
|---|---|---|
| `loan_id` | BIGINT | Unique loan identifier (`id` in the source). |
| `period` | BIGINT | Integer reporting period, 1..60. **Quarterly.** |
| `reporting_quarter` | VARCHAR | Calendar label for the period. DERIVED — see Known Assumptions. |
| `quarters_on_book` | BIGINT | `period - orig_time`. The analogue of months on book. |
| `current_balance` | DOUBLE | Unpaid principal balance — the amount still owed. |
| `current_ltv` | DOUBLE | Mark-to-market loan-to-value. Above 100 = negative equity. |
| `current_ltv_band` | VARCHAR | Banded `current_ltv`. Bands in `src/config.py`. |
| `current_interest_rate` | DOUBLE |  |
| `status_code` | BIGINT | 0 Active, 1 Default, 2 Payoff. Default and payoff are terminal. |
| `status_bucket` | VARCHAR | Readable form of `status_code`. |
| `default_time` | BIGINT |  |
| `payoff_time` | BIGINT |  |
| `is_forward_filled` | BOOLEAN | TRUE where the row was synthesised to close a reporting gap. Exclude for reported-only analysis. |
| `house_price_index` | DOUBLE | Period-level macro. Not carried forward into filled rows. |
| `gdp_growth` | DOUBLE | Period-level macro. |
| `unemployment_rate` | DOUBLE | Period-level macro. Used to recover the calendar. |
| `origination_vintage` | VARCHAR | Origination cohort, calendar-labelled. |
| `credit_score_band` | VARCHAR | Banded credit score. Primary risk cut. |
| `ltv_band` | VARCHAR | Banded `original_ltv`. |
| `property_type` | VARCHAR | Single family / Planned urban / Condominium / Other. 'Other' is the all-zero one-hot category in the source. |
| `occupancy` | VARCHAR | Investor or Owner occupied. |
| `focus_cohort` | VARCHAR | Marks the two contrast cohorts. |
| `observed_from_origination` | BOOLEAN | FALSE where the loan predates the observation window (left censored). Excluded from vintage curves. |

## `fact_credit_event`

15,154 rows.

| Column | Type | Notes |
|---|---|---|
| `loan_id` | BIGINT | Unique loan identifier (`id` in the source). |
| `default_period` | BIGINT | Period in which the loan first defaulted. |
| `default_quarter` | VARCHAR |  |
| `quarters_on_book_at_default` | BIGINT |  |
| `exposure_at_default` | DOUBLE | Balance outstanding when the loan defaulted. |
| `ltv_at_default` | DOUBLE | Loan-to-value at the moment of default. |
| `ltv_band_at_default` | VARCHAR |  |
| `original_balance` | DOUBLE | Amount lent at origination. Denominator for vintage curves. |
| `credit_score` | BIGINT | FICO at origination. |
| `credit_score_band` | VARCHAR | Banded credit score. Primary risk cut. |
| `ltv_band` | VARCHAR | Banded `original_ltv`. |
| `origination_vintage` | VARCHAR | Origination cohort, calendar-labelled. |
| `property_type` | VARCHAR | Single family / Planned urban / Condominium / Other. 'Other' is the all-zero one-hot category in the source. |
| `occupancy` | VARCHAR | Investor or Owner occupied. |
| `focus_cohort` | VARCHAR | Marks the two contrast cohorts. |
| `house_price_index` | DOUBLE | Period-level macro. Not carried forward into filled rows. |
| `unemployment_rate` | DOUBLE | Period-level macro. Used to recover the calendar. |

## `dim_date`

60 rows.

| Column | Type | Notes |
|---|---|---|
| `period` | BIGINT | Integer reporting period, 1..60. **Quarterly.** |
| `reporting_quarter` | VARCHAR | Calendar label for the period. DERIVED — see Known Assumptions. |
| `year` | INTEGER |  |
| `quarter` | INTEGER |  |

## `dim_period_macro`

60 rows.

| Column | Type | Notes |
|---|---|---|
| `period` | BIGINT | Integer reporting period, 1..60. **Quarterly.** |
| `house_price_index` | DOUBLE | Period-level macro. Not carried forward into filled rows. |
| `gdp_growth` | DOUBLE | Period-level macro. |
| `unemployment_rate` | DOUBLE | Period-level macro. Used to recover the calendar. |

## `dq_results`

12 rows.

| Column | Type | Notes |
|---|---|---|
| `run_timestamp` | TIMESTAMP | One timestamp per run, so a run's findings can be queried together. |
| `phase` | VARCHAR |  |
| `rule_name` | VARCHAR |  |
| `severity` | VARCHAR |  |
| `status` | VARCHAR |  |
| `affected_rows` | BIGINT | Count of rows failing the rule. 0 = pass. |
| `detail` | VARCHAR |  |

## Source columns not carried into the warehouse

`first_time`, `mat_time`, `hpi_orig_time`, `Interest_Rate_orig_time` and the
raw `REtype_*` one-hot flags are read at ingestion but either collapsed into
a derived column or dropped as unused. See `src/config.py` for the full
source column list.

