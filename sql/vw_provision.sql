-- BUSINESS QUESTION: How much should be set aside against expected credit
-- losses, by IFRS 9 stage and segment, and how well covered is the book?
--
-- ILLUSTRATIVE ONLY -- THIS IS NOT AN ACCOUNTING ALLOWANCE. The dataset carries
-- no accounting provision, so this reconstructs the reporting mechanics rather
-- than reproducing a real balance sheet number.
--
-- IFRS 9 splits a book into three stages and provides differently for each:
--   Stage 1  performing            -> 12-month expected credit loss
--   Stage 2  risk increased since origination -> LIFETIME expected credit loss
--   Stage 3  credit-impaired       -> lifetime loss, default already happened
--
-- ECL = exposure x probability of default x loss given default.
--
-- WHAT IS OBSERVED AND WHAT IS ASSUMED, stated plainly because it is the whole
-- credibility of this view:
--   * Exposure     OBSERVED -- current balance
--   * PD           OBSERVED -- measured from this panel, per segment, at a
--                  4-quarter horizon for Stage 1 and lifetime for Stages 2/3
--   * LGD          ASSUMED  -- fixed at ASSUMED_LOSS_GIVEN_DEFAULT in
--                  src/config.py, because this source records no recovery or
--                  realised loss amounts. Every number here scales linearly
--                  with it.
--
-- Staging deviates from the brief by necessity: with no delinquency field, the
-- Stage 2 trigger is negative equity (current LTV above threshold) rather than
-- 1-2 months in arrears. See src/config.py.
CREATE OR REPLACE VIEW vw_provision AS
WITH staged AS (
    SELECT
        f.*,
        CASE WHEN f.status_code = 1                       THEN 'Stage 3'
             WHEN f.current_ltv > {sicr_ltv}              THEN 'Stage 2'
             ELSE 'Stage 1'
        END AS ifrs9_stage
    FROM fact_loan_quarter f
),
-- OBSERVED lifetime PD: of the loans in a segment, what share ever defaulted.
pd_lifetime AS (
    SELECT l.credit_score_band,
           count(*) FILTER (WHERE e.loan_id IS NOT NULL) * 1.0 / nullif(count(*), 0) AS pd_lifetime
    FROM dim_loan l LEFT JOIN fact_credit_event e USING (loan_id)
    GROUP BY l.credit_score_band
),
-- OBSERVED 12-month PD: of the loan-quarters active in a segment, what share
-- defaulted within the next {horizon} quarters. This is the forward-looking
-- window IFRS 9 asks for on Stage 1, measured rather than assumed.
pd_12m AS (
    SELECT f.credit_score_band,
           count(*) FILTER (WHERE e.default_period IS NOT NULL
                              AND e.default_period <= f.period + {horizon}) * 1.0
               / nullif(count(*), 0) AS pd_12m
    FROM fact_loan_quarter f
    LEFT JOIN fact_credit_event e ON e.loan_id = f.loan_id
    WHERE f.status_code = 0
    GROUP BY f.credit_score_band
)
SELECT
    s.period,
    s.reporting_quarter,
    s.ifrs9_stage,
    s.credit_score_band,
    count(*)                     AS loans,
    sum(s.current_balance)       AS exposure,
    -- Stage 1 provides 12 months of loss, Stages 2 and 3 provide lifetime.
    -- Stage 3 has already defaulted, so its PD is 1.
    CASE s.ifrs9_stage WHEN 'Stage 1' THEN max(p12.pd_12m)
                       WHEN 'Stage 2' THEN max(pl.pd_lifetime)
                       ELSE 1.0 END  AS probability_of_default,
    {lgd}                        AS loss_given_default_assumed,
    sum(s.current_balance) *
        CASE s.ifrs9_stage WHEN 'Stage 1' THEN max(p12.pd_12m)
                           WHEN 'Stage 2' THEN max(pl.pd_lifetime)
                           ELSE 1.0 END * {lgd}  AS provision,
    -- Coverage ratio: provision as a share of the exposure it stands against.
    100.0 * (sum(s.current_balance) *
        CASE s.ifrs9_stage WHEN 'Stage 1' THEN max(p12.pd_12m)
                           WHEN 'Stage 2' THEN max(pl.pd_lifetime)
                           ELSE 1.0 END * {lgd})
        / nullif(sum(s.current_balance), 0)      AS coverage_ratio_pct
FROM staged s
LEFT JOIN pd_lifetime pl ON pl.credit_score_band = s.credit_score_band
LEFT JOIN pd_12m      p12 ON p12.credit_score_band = s.credit_score_band
GROUP BY s.period, s.reporting_quarter, s.ifrs9_stage, s.credit_score_band
ORDER BY s.period, s.ifrs9_stage, s.credit_score_band;
