-- BUSINESS QUESTION: Of the loans in a given state this quarter, what share are
-- in each state next quarter, and how much balance moved with them?
--
-- TWO LIMITATIONS, both from the source rather than the method.
--
-- 1. No delinquency buckets exist, so this is a status transition matrix
--    (active -> active / default / payoff), not a 30-60-90 bucket migration.
--    Default and payoff are terminal -- they are always a loan's last row -- so
--    there are no backward moves and NO CURES to observe. The brief asks for
--    cures to be visible; on this dataset there are none to make visible.
--
-- 2. Forward-filled rows are excluded from BOTH sides of the join. A filled row
--    is a carried-forward copy of the previous quarter, so pairing it with a
--    real one would manufacture a "stayed in the same state" transition that
--    was never reported. Roll rates must be built from reported data only.
CREATE OR REPLACE VIEW vw_roll_rates AS
WITH reported AS (
    SELECT loan_id, period, reporting_quarter, status_bucket, current_balance,
           credit_score_band, ltv_band, origination_vintage
    FROM fact_loan_quarter
    WHERE NOT is_forward_filled
),
transitions AS (
    -- Self-join on the loan across consecutive reporting periods.
    SELECT
        this_q.period                AS from_period,
        this_q.reporting_quarter     AS from_quarter,
        this_q.status_bucket         AS from_status,
        next_q.status_bucket         AS to_status,
        this_q.credit_score_band,
        this_q.ltv_band,
        this_q.origination_vintage,
        this_q.current_balance
    FROM reported AS this_q
    JOIN reported AS next_q
      ON next_q.loan_id = this_q.loan_id
     AND next_q.period  = this_q.period + 1
)
SELECT
    from_period, from_quarter, from_status, to_status,
    count(*)             AS loans_moved,
    sum(current_balance) AS balance_moved,
    -- The roll rate: share of loans in from_status that landed in to_status.
    100.0 * count(*)
        / nullif(sum(count(*)) OVER (PARTITION BY from_period, from_status), 0)
                         AS roll_rate_pct_by_count,
    100.0 * sum(current_balance)
        / nullif(sum(sum(current_balance)) OVER (PARTITION BY from_period, from_status), 0)
                         AS roll_rate_pct_by_balance
FROM transitions
GROUP BY from_period, from_quarter, from_status, to_status
ORDER BY from_period, from_status, to_status;
