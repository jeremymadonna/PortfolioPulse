-- BUSINESS QUESTION: When loans default, how much money is exposed, and what is
-- the collateral position at that moment?
--
-- IMPORTANT LIMITATION. The brief asks for recoveries, net loss, loss severity
-- and a coverage ratio. This dataset records NO recovery amounts, NO expenses
-- and NO realised loss. Loss severity (loss given default -- the share of the
-- defaulted balance not recovered) therefore CANNOT be computed, and is absent
-- rather than guessed at.
--
-- What is observable, and reported here instead:
--   * exposure at default -- the balance still owed when the loan defaulted
--   * loan-to-value at default -- the collateral position at that moment, which
--     is the single biggest driver of how severe a loss turns out to be
--
-- LTV above 100 means the borrower owed more than the property was worth. That
-- is the honest proxy for severity risk available here: a default at 60 LTV and
-- a default at 130 LTV are not remotely the same exposure, even though this
-- source cannot tell us the realised loss on either.
-- Provision and coverage ratio are added in Phase 3.
CREATE OR REPLACE VIEW vw_loss_recovery AS
WITH events AS (
    SELECT 'Credit score band' AS segment_type, credit_score_band AS segment_value, *
    FROM fact_credit_event
    UNION ALL SELECT 'LTV band (at origination)', ltv_band, * FROM fact_credit_event
    UNION ALL SELECT 'Property type', property_type, * FROM fact_credit_event
    UNION ALL SELECT 'Occupancy', occupancy, * FROM fact_credit_event
    UNION ALL SELECT 'Origination vintage', origination_vintage, * FROM fact_credit_event
    UNION ALL SELECT 'Portfolio', 'Total', * FROM fact_credit_event
)
SELECT
    segment_type,
    segment_value,
    count(*)                            AS defaults,
    sum(exposure_at_default)            AS total_exposure_at_default,
    avg(exposure_at_default)            AS avg_exposure_at_default,
    avg(ltv_at_default)                 AS avg_ltv_at_default,
    -- Share of defaults where the loan was underwater at the point of default.
    100.0 * count(*) FILTER (WHERE ltv_at_default > 100) / nullif(count(*), 0)
                                        AS pct_underwater_at_default,
    avg(quarters_on_book_at_default)    AS avg_quarters_on_book_at_default,
    -- How much of the originally lent balance was still outstanding at default.
    100.0 * sum(exposure_at_default) / nullif(sum(original_balance), 0)
                                        AS exposure_as_pct_of_original,
    NULL::DOUBLE                        AS loss_severity_pct  -- not computable, see above
FROM events
GROUP BY segment_type, segment_value
ORDER BY segment_type, segment_value;
