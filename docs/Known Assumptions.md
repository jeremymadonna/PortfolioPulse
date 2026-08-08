# Known Assumptions

Everything here is a choice that affects the numbers. Writing these down is
worth more than any chart in the dashboard.

## About the data itself

**This is US residential mortgage data, not Canadian retail credit.** A
randomised selection from US residential mortgage-backed securities portfolios,
2000Q2–2015Q1. The methodology transfers directly to a retail book; **the loss
rates do not**. Default rates here reach levels driven by a US housing collapse
and subprime underwriting.

**Single product.** All mortgages. There is no product-mix analysis, because
there is no product mix. Segmentation is credit score band, LTV band, property
type, occupancy and origination vintage.

**The grain is quarterly, not monthly.** A 30-year loan shows
`mat_time - orig_time = 120` — 120 quarters. The fact table is named
`fact_loan_quarter`, deviating from the brief's `fact_loan_month`, so the grain
cannot be misread.

**The sample is not the whole market.** A randomised selection from RMBS
portfolios, which skews toward securitised and therefore riskier lending. The
30% lifetime default rate across the whole file is not a market-wide figure.

## Derived, not given

**The calendar is inferred.** The source's `time` column is deliberately
deidentified — an integer 1..60 with no stated calendar meaning. It was anchored
using the embedded unemployment and house price series:

| Period | Dataset UER | Implied quarter | Actual US UER |
|---|---|---|---|
| 1 | 3.8 | 2000Q2 | 3.9 |
| 14 | 6.2 | 2003Q3 | 6.1 |
| 25 | 4.7 (HPI peaks) | 2006Q2 | 4.6 |
| 39 | 10.0 (UER peaks) | 2009Q4 | 9.9 |
| 60 | 5.7 | 2015Q1 | 5.6 |

Five checkpoints agree within 0.1pp. **This is an inference, not a fact stated
by the provider.** It is used only for labelling — every metric is computed on
the raw integer period. Setting `CALENDAR_ANCHOR = None` in `src/config.py`
removes it without changing a single number.

**Band cuts are choices.** Credit score bands follow the brief. LTV bands are
conventional mortgage cuts (80 is the mortgage-insurance threshold, above 100 is
negative equity). All in `src/config.py`; nothing else hard-codes them.

**The two contrast cohorts were chosen from the data, not assumed.** Lifetime
default rate rises monotonically across origination quarters; 2003Q3 and 2006Q4
are the ends of that range with enough loans to be meaningful.

## Provisioning — illustrative, not an accounting allowance

**Nothing in `vw_provision` is a real provision.** The dataset carries no
accounting allowance. This reconstructs the reporting mechanics only.

**Staging deviates from the brief because it has to.** The brief stages on
months delinquent (Stage 3 at 3+, Stage 2 at 1–2). This dataset has no
delinquency field at all. The Stage 2 trigger is therefore **negative equity** —
current LTV above 100 — as the observable proxy for a significant increase in
credit risk. Defensible for a mortgage book, but it is a proxy, and a real bank
would stage on far more.

**PD is observed. LGD is assumed.** PD is measured from this panel per credit
score band, at a 4-quarter horizon for Stage 1 and lifetime for Stages 2 and 3.
**LGD is a fixed constant** in `src/config.py`, because this source records no
recovery, expense or realised-loss amounts. Every provision figure scales
linearly with it. The brief asked for observed loss severity; it is not
obtainable here.

## Data handling decisions

**Duplicate loan-periods were deduplicated.** 339 pairs, 27 with conflicting
balances. One row kept per loan-period, taking the lower balance as the
conservative reading. Logged to `dq_results` as HIGH severity.

**Panel gaps were forward-filled.** ⚠️ **This synthesises observations that were
never reported.** 1,582 rows across 1,168 loans carry the last reported balance,
LTV, rate and status into a gap. Declared here because inventing observations in
a project whose premise is real rather than generated data is exactly the kind
of thing that must be stated rather than found.

Three things limit it: every filled row carries `is_forward_filled = true` and
can be excluded with one predicate; they are excluded from roll rates entirely;
and macro variables are **not** carried forward — unemployment, GDP and the
house price index belong to the period, not the loan, so filled rows take the
true value for their quarter.

Filled rows are 0.24% of portfolio balance. The headline cohort comparison is
unchanged by both this and the deduplication.

**Origination attributes are taken from the loan's earliest period.** 439 loans
report origination attributes that change across their own rows — 49 with more
than one `orig_time`, 381 with more than one FICO. Collapsing these with an
arbitrary pick made the pipeline non-deterministic, so the value reported at the
earliest period is used (`arg_min(col, time)`). The panel reads `orig_time` from
`dim_loan` rather than deriving it separately, so the two cannot disagree. Two
consecutive rebuilds now produce identical tables.

**Left-censored loans are excluded from vintage curves.** 1,126 loans predate
the observation window, so their early life is missing and any that had already
defaulted are absent entirely. Including them would bias every cohort curve
downward.

**Known defects were left in place.** Three quality rules fail and are not
corrected — see [Data Quality Rules](Data%20Quality%20Rules.md). In particular
the 21,290 rows where balance rises on a repaying loan are **real negative-
amortisation behaviour**, not a defect to be cleaned.

## What cannot be produced from this source

Gaps, not omissions. A stand-in would be worse:

- **30+ / 60+ / 90+ arrears rates** — no days-past-due or delinquency field.
- **Loss severity, recoveries, net loss, true coverage** — no recovery, expense
  or realised-loss amounts.
- **Cure rates** — default and payoff are terminal; no loan returns to
  performing, so roll rates show no backward moves.
- **Geographic, purpose or channel analysis** — no property state, loan purpose
  or origination channel in the source.
