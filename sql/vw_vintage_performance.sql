-- BUSINESS QUESTION: For each origination cohort, what share of the money lent
-- had defaulted by each point in the loan's life -- and which cohorts were
-- worse, judged on equal terms?
--
-- This is the view the whole project turns on, so three things are deliberate.
--
-- 1. INDEXED ON QUARTERS ON BOOK, NOT CALENDAR TIME. Cohorts originated in
--    different quarters are compared at the same AGE, otherwise a young cohort
--    always looks better simply for having had less time to go bad.
--
-- 2. NORMALISED BY THE ORIGINAL COHORT BALANCE. The denominator is the balance
--    the cohort started with and never changes as loans leave, so the curve is
--    genuinely cumulative and two cohorts of different size are comparable.
--
-- 3. COHORTS ARE ONLY COMPARABLE WHERE BOTH ARE SEASONED. loans_observed and
--    pct_cohort_still_observed are carried on every row so a curve can be
--    truncated where its cohort stops being fully observed. The 2006Q4 cohort
--    can only be followed to 36 quarters on book while 2003Q3 reaches 46;
--    comparing them at quarter 46 would be comparing a full cohort against a
--    partial one. Filter on pct_cohort_still_observed or cap quarters_on_book.
--
-- Loans originated before the observation window opened are excluded entirely
-- (observed_from_origination): their early life is missing, and any that had
-- already defaulted are absent, which would bias every curve downward.
CREATE OR REPLACE VIEW vw_vintage_performance AS
WITH cohort AS (
    SELECT origination_vintage,
           count(*)              AS cohort_loans,
           sum(original_balance) AS cohort_original_balance
    FROM dim_loan
    WHERE observed_from_origination
    GROUP BY origination_vintage
),
observed AS (
    -- How much of the cohort is still being reported on at each age.
    SELECT origination_vintage, quarters_on_book,
           count(DISTINCT loan_id) AS loans_observed
    FROM fact_loan_quarter
    WHERE observed_from_origination
      -- A handful of rows are dated before their loan's stated origination
      -- period, which is a source defect; they are excluded rather than
      -- allowed to create negative ages. Reported in the data quality register.
      AND quarters_on_book >= 0
    GROUP BY origination_vintage, quarters_on_book
),
defaults_at_age AS (
    SELECT l.origination_vintage,
           e.quarters_on_book_at_default AS quarters_on_book,
           count(*)                      AS defaults_in_quarter,
           sum(l.original_balance)       AS defaulted_original_balance
    FROM fact_credit_event e
    JOIN dim_loan l USING (loan_id)
    WHERE l.observed_from_origination
      AND e.quarters_on_book_at_default >= 0
    GROUP BY l.origination_vintage, e.quarters_on_book_at_default
)
SELECT
    o.origination_vintage,
    o.quarters_on_book,
    c.cohort_loans,
    c.cohort_original_balance,
    o.loans_observed,
    100.0 * o.loans_observed / nullif(c.cohort_loans, 0) AS pct_cohort_still_observed,
    coalesce(d.defaults_in_quarter, 0)                   AS defaults_in_quarter,
    sum(coalesce(d.defaults_in_quarter, 0)) OVER w       AS cumulative_defaults,
    100.0 * sum(coalesce(d.defaults_in_quarter, 0)) OVER w
        / nullif(c.cohort_loans, 0)                      AS cumulative_default_rate_pct,
    -- The headline curve: cumulative defaulted balance as a share of the money
    -- the cohort was originally lent.
    100.0 * sum(coalesce(d.defaulted_original_balance, 0)) OVER w
        / nullif(c.cohort_original_balance, 0)           AS cumulative_default_rate_by_balance_pct
FROM observed o
JOIN cohort c USING (origination_vintage)
LEFT JOIN defaults_at_age d USING (origination_vintage, quarters_on_book)
WINDOW w AS (
    PARTITION BY o.origination_vintage
    ORDER BY o.quarters_on_book
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY o.origination_vintage, o.quarters_on_book;
