# SQL Logic

Every reporting metric is computed in a `.sql` file under `sql/`. `src/views.py`
only reads and executes them. This keeps the SQL as the single source of truth
for what a number means: a reviewer can point at any figure in the dashboard or
the commentary and be shown the query behind it.

Each file opens with the business question it answers.

## The eight views

| File | Key techniques |
|---|---|
| `vw_portfolio_summary.sql` | `FILTER` aggregates for status splits, `LAG` for quarter-over-quarter movement and growth |
| `vw_segment_performance.sql` | `UNION ALL` unpivot to long form, partitioned window for share-of-portfolio, partitioned `LAG` per segment |
| `vw_delinquency.sql` | Nested aggregate over window (`sum(count(*)) OVER`) for within-segment shares |
| `vw_roll_rates.sql` | Self-join on `loan_id` across consecutive periods, partitioned window for the rate denominator |
| `vw_vintage_performance.sql` | Running `sum() OVER (PARTITION BY vintage ORDER BY quarters_on_book)` for the cumulative curve, normalised by a cohort-level CTE |
| `vw_loss_recovery.sql` | `UNION ALL` unpivot, conditional `FILTER` counts |
| `vw_provision.sql` | Two observed-PD CTEs at different horizons, joined per segment |
| `vw_provision_movement.sql` | `LAG` for opening position, `greatest()` to split movement into charge and release |

## Patterns worth explaining

**Long, not wide.** `vw_segment_performance` and `vw_delinquency` emit one row
per segment_type / segment_value / period rather than a column per dimension.
Adding a dimension is then a `UNION ALL` branch, not a schema change, and the
dashboard can slice any dimension without a new view.

**Nested aggregate over window.** `sum(count(*)) OVER (PARTITION BY ...)` is a
window function applied to an aggregate in the same `SELECT`. It gives each
group's share of its partition in a single pass, without a self-join.

**Config values are substituted, not hard-coded.** SQL files declaring
placeholders like `{lgd}` get them filled from `src/config.py` at execution
time, so an assumption lives in one place. Files without placeholders are never
passed through `.format()`, so literal braces are safe.

**Reconciliation as a column.** `vw_provision_movement` carries
`reconciliation_error` rather than asserting the balance elsewhere. If opening
+ increase − decrease ever stops equalling closing, the view says so on the row.

## Two adaptations forced by the source

Both documented in the file headers rather than left for a reader to discover.

**Roll rates are status transitions.** There are no delinquency buckets, so the
matrix is active → active / default / payoff. Because default and payoff are
terminal, there are **no cures** to show. Forward-filled rows are excluded from
both sides of the self-join — pairing a carried-forward row with a reported one
would manufacture a "stayed in the same state" transition that never happened.

**Loss severity is `NULL`.** There are no recovery, expense or realised-loss
amounts, so `vw_loss_recovery` returns the column as `NULL` rather than a
guess, and reports exposure at default and LTV at default instead.

## Validation

Checks run against the built views, not assumed:

- Roll rates sum to exactly 100% within every from-status and period.
- Segment balances reconcile to the portfolio total to 0.00 on all five
  dimensions (also enforced as data quality rule
  `segment_balance_reconciliation`).
- `vw_vintage_performance` independently reproduces the lifetime default rates
  computed straight from `fact_credit_event`.
- Delinquency shares sum to 100% across all segment-periods.
- Provision movement reconciles to zero error on every row.
