# Business Insights

> **TEMPLATE — NOT YET COMPLETED.**
>
> The figures below are deliberately blank. Fill them in yourself after
> reviewing the analysis. Do not write the conclusion before seeing the number.
>
> Charts do not make someone an analyst; observations do. For each finding write
> **the number first**, then what it means for the business — a decision someone
> could actually take. A finding with no business meaning is a chart caption.
>
> Aim for four or five. Delete any you cannot support from the data.
> Each one below includes the query that produces its number.

---

## 1. Credit quality at origination and its effect under stress

**Finding:** ______________________________________________

**The numbers:** cumulative default rate by credit score band, ______ vs ______

**Business meaning:** _____________________________________

```sql
SELECT l.credit_score_band, count(*) AS loans,
       round(100.0 * count(e.loan_id) / count(*), 1) AS lifetime_default_pct
FROM dim_loan l LEFT JOIN fact_credit_event e USING (loan_id)
WHERE l.focus_cohort = 'Stressed cohort'
GROUP BY 1 ORDER BY 1;
```

---

## 2. Collateral position and default outcomes

**Finding:** ______________________________________________

**The numbers:** LTV at default ______ ; share underwater at default ______%

**Business meaning:** _____________________________________

```sql
SELECT segment_value, defaults, round(avg_ltv_at_default,1) AS ltv_at_default,
       round(pct_underwater_at_default,1) AS pct_underwater
FROM vw_loss_recovery WHERE segment_type = 'LTV band (at origination)'
ORDER BY segment_value;
```

---

## 3. Comparing the two cohorts on equal terms

**Finding:** ______________________________________________

**The numbers:** at ______ quarters on book, ______% vs ______%

**Business meaning:** _____________________________________

```sql
-- Compare only where BOTH cohorts are fully seasoned.
SELECT quarters_on_book, origination_vintage,
       round(cumulative_default_rate_by_balance_pct, 1) AS cum_default_pct,
       round(pct_cohort_still_observed, 0) AS pct_observed
FROM vw_vintage_performance
WHERE origination_vintage IN ('2003Q3','2006Q4') AND quarters_on_book <= 36
ORDER BY quarters_on_book, origination_vintage;
```

---

## 4. How quickly loans went bad

**Finding:** ______________________________________________

**The numbers:** average quarters on book at default, ______ vs ______

**Business meaning:** _____________________________________

```sql
SELECT origination_vintage, count(*) AS defaults,
       round(avg(quarters_on_book_at_default), 1) AS avg_quarters_to_default
FROM fact_credit_event WHERE focus_cohort IS NOT NULL
GROUP BY 1 ORDER BY 1;
```

---

## 5. A data quality finding worth reporting

**Finding:** ______________________________________________

**The numbers:** ______ rows, concentrated ______

**Business meaning:** _____________________________________

```sql
SELECT rule_name, severity, affected_rows FROM dq_results
WHERE phase = '4-quality' AND status = 'FAIL'
  AND run_timestamp = (SELECT max(run_timestamp) FROM dq_results WHERE phase='4-quality');
```

> Explaining *why* a real anomaly occurs, and deciding how to handle it, is a
> far better story than catching a defect you injected yourself. See
> [Data Quality Rules](Data%20Quality%20Rules.md) — one of the three failures is
> not a defect at all.

---

## Before you finish

- [ ] Every figure traced back to a query that reproduces it
- [ ] Every finding has a business meaning that names a decision
- [ ] Nothing claimed that this dataset cannot support — check
      [Known Assumptions](Known%20Assumptions.md)
- [ ] Cohort comparisons made only where both cohorts are seasoned
- [ ] Provision figures described as illustrative wherever quoted
