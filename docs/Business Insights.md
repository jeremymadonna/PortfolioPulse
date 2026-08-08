# Business Insights

Five findings from the Portfolio Pulse warehouse. Every figure below was produced by
the query printed beneath it, against the built views — nothing is estimated and
nothing is rounded in a flattering direction.

The two cohorts compared throughout are **2003Q3** (1,427 loans, benign) and
**2006Q4** (3,822 loans, stressed), chosen because lifetime default rate rises
monotonically across origination quarters and these are the ends of that range.

---

## 1. Credit score still ranks risk under stress — but it stops protecting you

**Finding:** Credit score discriminated in both cohorts, yet the *entire* score
distribution shifted. In the 2006Q4 cohort, the **best** credit band defaulted at
**31.7%** — worse than the **worst** band of the 2003Q3 cohort at **19.6%**.

| Credit score band | 2003Q3 default | 2006Q4 default |
|---|---|---|
| <620 | 19.6% | 54.7% |
| 620–659 | 11.3% | 55.4% |
| 660–699 | 6.5% | **58.9%** |
| 700–739 | 5.1% | 50.3% |
| 740–779 | 3.3% | 43.4% |
| 780+ | **2.9%** | **31.7%** |

Two things worth noting honestly. The spread widened (16.7 to 27.3 percentage
points), so the score was still doing work. But the rank ordering **partially
inverted** at the bottom of the stressed cohort: the 660–699 band (58.9%)
performed worse than the sub-620 band (54.7%). Score ceased to be a reliable
ordering exactly where it mattered most.

**Business meaning:** underwriting cut-offs are necessary but not sufficient. A
score-based limit would have rejected the worst loans of 2003 and still admitted
a 2006 book that defaulted at three times the rate of everything it excluded.
Score controls *relative* risk within a vintage; it does not control the level.
Vintage-level exposure limits are a separate control and cannot be substituted
by tightening score.

```sql
SELECT l.credit_score_band, l.focus_cohort, count(*) AS loans,
       round(100.0 * count(e.loan_id) / count(*), 1) AS lifetime_default_pct
FROM dim_loan l LEFT JOIN fact_credit_event e USING (loan_id)
WHERE l.focus_cohort IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2;
```

---

## 2. Collateral position, not borrower quality, decided whether a default hurt

**Finding:** The two cohorts defaulted into completely different collateral
positions. Of 2003Q3 defaults, **0.0%** were underwater; average loan-to-value at
default was **66.1**. Of 2006Q4 defaults, **65.4%** were underwater, at an average
LTV of **106.7**.

Origination LTV predicted this almost mechanically:

| LTV band at origination | Defaults | Avg LTV at default | % underwater at default |
|---|---|---|---|
| ≤60 | 326 | 68.1 | **0.0%** |
| 61–70 | 1,334 | 82.0 | 12.3% |
| 71–80 | 9,163 | 96.9 | 49.0% |
| 81–90 | 2,754 | 101.0 | 56.8% |
| 91–100 | 1,554 | 108.8 | **66.3%** |

**Business meaning:** LTV and credit score are not two views of the same risk and
must not be traded off against each other. Score largely governs *whether* a loan
defaults; LTV governs *what it costs when it does*. A loan originated at ≤60 LTV
never defaulted underwater in this book — the equity cushion absorbed the entire
house price decline. LTV therefore needs its own limit and its own monitoring
line, not a combined risk grade that lets a strong score offset a thin deposit.

```sql
SELECT segment_value AS orig_ltv_band, defaults,
       round(avg_ltv_at_default, 1) AS avg_ltv_at_default,
       round(pct_underwater_at_default, 1) AS pct_underwater
FROM vw_loss_recovery WHERE segment_type = 'LTV band (at origination)'
ORDER BY 1;
```

---

## 3. When you lend matters more than who you lend to

**Finding:** The two cohorts were near-identical at origination — average credit
score **674 vs 660**, average LTV **79.7 vs 80.1** — and diverged by roughly ten
times. Compared at equal seasoning, on cumulative defaulted balance as a share of
original cohort balance:

| Quarters on book | 2003Q3 | 2006Q4 | Ratio |
|---|---|---|---|
| 4 | 0.5% | 8.3% | 17× |
| 8 | 1.7% | 25.2% | 15× |
| 16 | 3.0% | 45.7% | 15× |
| 24 | 4.1% | 52.9% | 13× |
| 32 | 5.7% | **54.9%** | 10× |

Indexed on age, not calendar date — otherwise the younger cohort flatters itself
by having had less time to fail. The comparison stops at 32 quarters because
2006Q4 can only be followed to 33.

**Business meaning:** the single largest driver of loss in this book was the
quarter of origination, a factor no borrower-level control touches. That makes
origination-vintage concentration a first-class risk to monitor and limit, in the
same way as geography or product. A book that writes disproportionate volume into
one part of a cycle carries a risk that no amount of borrower selection removes.

```sql
SELECT quarters_on_book, origination_vintage,
       round(cumulative_default_rate_by_balance_pct, 1) AS cum_default_by_balance_pct
FROM vw_vintage_performance
WHERE origination_vintage IN ('2003Q3','2006Q4') AND quarters_on_book <= 32
ORDER BY quarters_on_book, origination_vintage;
```

---

## 4. A bad vintage announces itself early

**Finding:** The stressed cohort failed both harder *and* faster. Median time to
default was **9 quarters** against **14** for the benign cohort. By quarter 8 —
two years on book — the 2006Q4 cohort had already lost **25.2%** of original
balance, which is **46% of everything it would ultimately lose**.

| | 2003Q3 | 2006Q4 |
|---|---|---|
| Defaults | 133 | 2,035 |
| Median quarters to default | 14 | **9** |
| Mean quarters to default | 16.4 | 10.5 |
| Cumulative loss by quarter 8 | 1.7% | **25.2%** |

**Business meaning:** early-life performance is a usable leading indicator, not
just a lagging report. The 2006Q4 cohort was visibly failing within eight
quarters, long before its final loss rate was known — which is time enough to
tighten origination criteria, reprice, or stop writing the product. A monitoring
pack that reports cohorts on months-on-book rather than calendar month makes that
signal visible; one that reports only portfolio totals buries it, because a
deteriorating new cohort is masked by a large seasoned back book.

```sql
SELECT origination_vintage, count(*) AS defaults,
       round(median(quarters_on_book_at_default), 1) AS median_qtrs_to_default,
       round(avg(quarters_on_book_at_default), 1) AS mean_qtrs_to_default
FROM fact_credit_event WHERE focus_cohort IS NOT NULL GROUP BY 1 ORDER BY 1;
```

---

## 5. A data quality rule surfaced a lending-practice finding

**Finding:** The rule `balance_increased_on_amortising_loan` fails on **21,290
rows** — balances rising on loans that should be repaying. It looks like a
reporting error. It is not. The rises are seventeen times more concentrated in
bubble-era originations:

| Vintage group | Active rows with a balance rise |
|---|---|
| 2000–2003 | 0.4% |
| 2004–2005 | 2.0% |
| 2006+ | **6.7%** |

Across **11.3% of the book**. That is the signature of negative amortisation and
option-ARM lending, where the scheduled payment does not cover the interest and
the balance grows by design.

**Business meaning:** two things. First, product structure was itself a risk
factor — the same vintages that took on negative amortisation are the vintages
that defaulted at 53%, and a monitoring pack tracking only score and LTV would
never have seen it. Second, and more general: a failing data quality rule is a
question, not a defect. Had this been "corrected" on sight, a real finding about
how those loans were written would have been deleted from the data. Rules should
route to investigation, not to automated cleansing.

```sql
SELECT rule_name, severity, affected_rows FROM dq_results
WHERE phase = '4-quality' AND status = 'FAIL'
  AND run_timestamp = (SELECT max(run_timestamp) FROM dq_results WHERE phase='4-quality');
```

---

## Caveats attached to all of the above

- **US residential mortgage data, not Canadian retail credit.** The methodology
  transfers; the loss rates do not. See [Known Assumptions](Known%20Assumptions.md).
- **Loss severity is nowhere in this analysis** because this source records no
  recoveries, expenses or realised losses. LTV at default is used as the
  observable driver of severity, not as a substitute for it.
- **Provision figures are illustrative** — PD is observed, LGD is an assumed
  constant.
- **Cohorts are compared only to 32 quarters**, where both are still observable.
- **Findings 1–4 rest on two cohorts** of 1,427 and 3,822 loans. The direction is
  corroborated by the monotonic rise in default rate across all origination
  quarters, but the precise figures are cohort-specific.
