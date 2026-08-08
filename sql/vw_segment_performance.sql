-- BUSINESS QUESTION: The same size and growth picture as the portfolio summary,
-- but cut by each risk dimension -- so a movement in the total can be traced to
-- the segment that caused it.
--
-- Output is long, not wide: one row per segment_type / segment_value / quarter.
-- That shape lets the dashboard slice on any dimension without a new view, and
-- lets Phase 5 rank segment contributions with a single ORDER BY.
--
-- This dataset carries no property state, loan purpose or origination channel,
-- so the dimensions are credit score band, LTV band, property type, occupancy
-- and origination vintage. See DATA.md.
CREATE OR REPLACE VIEW vw_segment_performance AS
WITH unpivoted AS (
    SELECT period, reporting_quarter, 'Credit score band' AS segment_type,
           credit_score_band AS segment_value, current_balance, status_code
    FROM fact_loan_quarter
    UNION ALL SELECT period, reporting_quarter, 'LTV band (at origination)',
           ltv_band, current_balance, status_code FROM fact_loan_quarter
    UNION ALL SELECT period, reporting_quarter, 'Property type',
           property_type, current_balance, status_code FROM fact_loan_quarter
    UNION ALL SELECT period, reporting_quarter, 'Occupancy',
           occupancy, current_balance, status_code FROM fact_loan_quarter
    UNION ALL SELECT period, reporting_quarter, 'Origination vintage',
           origination_vintage, current_balance, status_code FROM fact_loan_quarter
),
by_segment AS (
    SELECT segment_type, segment_value, period, reporting_quarter,
           sum(current_balance) FILTER (WHERE status_code = 0) AS active_balance,
           count(*)             FILTER (WHERE status_code = 0) AS active_loans,
           count(*)             FILTER (WHERE status_code = 1) AS defaults,
           sum(current_balance) FILTER (WHERE status_code = 1) AS defaulted_balance
    FROM unpivoted
    GROUP BY 1, 2, 3, 4
)
SELECT
    segment_type, segment_value, period, reporting_quarter,
    active_balance, active_loans, defaults, defaulted_balance,
    active_balance / nullif(active_loans, 0) AS average_balance,
    -- Share of the whole book, so a segment's growth can be read as mix shift.
    100.0 * active_balance
        / nullif(sum(active_balance) OVER (PARTITION BY segment_type, period), 0)
                                             AS pct_of_portfolio_balance,
    LAG(active_balance) OVER (PARTITION BY segment_type, segment_value ORDER BY period)
                                             AS prior_active_balance,
    100.0 * (active_balance / nullif(
        LAG(active_balance) OVER (PARTITION BY segment_type, segment_value ORDER BY period), 0) - 1)
                                             AS balance_growth_pct,
    100.0 * defaults / nullif(
        LAG(active_loans) OVER (PARTITION BY segment_type, segment_value ORDER BY period), 0)
                                             AS quarterly_default_rate_pct
FROM by_segment
ORDER BY segment_type, segment_value, period;
