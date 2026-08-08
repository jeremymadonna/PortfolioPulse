# Data Quality Rules

Run: `python src/quality.py`

Ten rules against the built warehouse. Each returns a name, severity, pass/fail
and affected row count, appended to `dq_results` with a run timestamp so the
register accumulates history rather than being overwritten.

**Nothing is cleaned by these rules.** A failing rule is reported and left
failing. Deciding what to do about a defect is a judgement call for whoever owns
the numbers, not something a script should make silently.

## The rules

| # | Rule | Severity | Checks |
|---|---|---|---|
| 1 | `duplicate_loan_period` | HIGH | No loan appears twice in the same period |
| 2 | `negative_balance` | HIGH | No negative balances |
| 3 | `balance_increased_on_amortising_loan` | MEDIUM | A repaying loan's balance should fall |
| 4 | `row_dated_before_origination` | MEDIUM | No row predates its loan's stated origination |
| 5 | `loan_left_terminal_status` | HIGH | No loan leaves default or payoff |
| 6 | `missing_credit_score` | MEDIUM | Credit score populated |
| 7 | `missing_property_type` | LOW | Property type stated |
| 8 | `invalid_status_code` | HIGH | Status is 0, 1 or 2 |
| 9 | `segment_balance_reconciliation` | HIGH | Every segmentation adds back to the portfolio total |
| 10 | `reporting_period_continuity` | MEDIUM | No missing periods in `dim_date` |

## Scoring

Weighted by severity: HIGH 3, MEDIUM 2, LOW 1. The score is the share of total
severity weight that passed. Weighting rather than counting rules equally means
a wrong balance moves the score three times as far as a missing descriptive
attribute.

**Current score: 87.5 / 100** (8 of 10 rules passing).

## Findings on the real data

### `balance_increased_on_amortising_loan` — 21,290 rows — DO NOT "FIX"

The most interesting failure in the project. Balances rising on a repaying loan
looks like a defect, but the rises are not spread evenly:

| Vintage group | Active rows with a balance rise |
|---|---|
| 2000–2003 | 0.4% |
| 2004–2005 | 2.0% |
| 2006+ | **6.7%** |

A seventeenfold concentration in bubble-era originations, across 11.3% of the
book. That is the signature of **negative amortisation and option-ARM lending**,
where the scheduled payment does not cover the interest and the balance grows by
design. It is real product behaviour, not a reporting error. "Correcting" it
would destroy a genuine finding about how those vintages were underwritten.

Left failing deliberately, with this explanation attached.

### `missing_property_type` — 9,818 rows — LOW

The source encodes property type as three one-hot flags. 9,818 loans have all
three set to zero, which is a real "not stated" category rather than a defect.
Surfaced as `Other / not stated` and rated LOW.

### `row_dated_before_origination` — now PASSING

This originally failed on 2 rows, then 5 on a rerun — and a count that changes
between runs of the same pipeline is a bug, not a finding.

The cause was ours. Origination attributes were collapsed per loan with
`any_value()`, which picks arbitrarily. That is fine when the column really is
constant, and in this source it is not: **439 loans report origination
attributes that vary across their own rows** (49 with more than one `orig_time`,
381 with more than one FICO). Loan 11682 flips between `orig_time` 18 and −14
mid-panel. Whichever value `any_value()` happened to return changed
`quarters_on_book` for that loan, so the count moved between runs.

Fixed by taking the value reported at the loan's **earliest** period
(`arg_min(col, time)`), which is deterministic and defensible, and by having the
panel read `orig_time` from `dim_loan` rather than deriving it again so the two
tables cannot disagree. The rule now passes with zero rows, and two consecutive
rebuilds produce byte-identical tables.

The underlying source inconsistency has not disappeared — it is logged at
ingestion as `inconsistent_origination_attributes`.

## Defects found and corrected at ingestion

Logged separately under phase `1-ingest`, so the register distinguishes what was
wrong in the source from what remains in the model.

| Finding | Severity | Rows | Handling |
|---|---|---|---|
| Duplicate loan-periods | HIGH | 339 | One row kept per loan-period, lower balance (conservative). 27 pairs had conflicting balances. |
| Missing mid-panel periods | MEDIUM | 1,582 | Forward-filled across 1,168 loans. Every filled row flagged `is_forward_filled`. |
| Inconsistent origination attributes | MEDIUM | 439 loans | Value at the loan's earliest period is used (`arg_min`), so the result is deterministic. |

The forward-fill synthesises observations that were never reported. It is
flagged, logged, excluded from roll rates, and declared in
[Known Assumptions](Known%20Assumptions.md).
