-- BUSINESS QUESTION: How big is the book each quarter, how fast is it growing
-- or shrinking, and what is leaving it -- paid off, or defaulted?
--
-- Outstanding balance counts ACTIVE loans only (status 0). Default and payoff
-- rows are always a loan's last row in this dataset, so they are exits from the
-- book in that quarter, not part of the balance carried forward.
CREATE OR REPLACE VIEW vw_portfolio_summary AS
WITH by_quarter AS (
    SELECT
        period,
        reporting_quarter,
        -- UPB: unpaid principal balance, the amount still owed.
        sum(current_balance)  FILTER (WHERE status_code = 0) AS active_balance,
        count(*)              FILTER (WHERE status_code = 0) AS active_loans,
        sum(current_balance)  FILTER (WHERE status_code = 1) AS defaulted_balance,
        count(*)              FILTER (WHERE status_code = 1) AS defaults,
        sum(current_balance)  FILTER (WHERE status_code = 2) AS paid_off_balance,
        count(*)              FILTER (WHERE status_code = 2) AS payoffs,
        count(*)              FILTER (WHERE is_forward_filled) AS forward_filled_rows,
        max(unemployment_rate)                               AS unemployment_rate,
        max(house_price_index)                               AS house_price_index
    FROM fact_loan_quarter
    GROUP BY period, reporting_quarter
)
SELECT
    period,
    reporting_quarter,
    active_balance,
    active_loans,
    active_balance / nullif(active_loans, 0)                  AS average_balance,
    defaults,
    defaulted_balance,
    payoffs,
    paid_off_balance,
    forward_filled_rows,
    unemployment_rate,
    house_price_index,
    -- LAG gives the prior quarter on the same row, which is what makes a
    -- quarter-over-quarter movement expressible in one pass.
    LAG(active_balance) OVER (ORDER BY period)                AS prior_active_balance,
    active_balance - LAG(active_balance) OVER (ORDER BY period) AS balance_movement,
    100.0 * (active_balance / nullif(LAG(active_balance) OVER (ORDER BY period), 0) - 1)
                                                              AS balance_growth_pct,
    -- Default rate here is a FLOW: loans defaulting this quarter as a share of
    -- the loans that were still active at the end of the previous quarter.
    100.0 * defaults / nullif(LAG(active_loans) OVER (ORDER BY period), 0)
                                                              AS quarterly_default_rate_pct
FROM by_quarter
ORDER BY period;
