-- BUSINESS QUESTION: How did the provision change from one quarter to the next,
-- and was the move an increase or a release?
--
-- ILLUSTRATIVE ONLY -- see vw_provision.sql for what is observed and what is
-- assumed. Opening plus increase minus decrease must equal closing exactly on
-- every row; that reconciliation is the point of the table.
CREATE OR REPLACE VIEW vw_provision_movement AS
WITH by_quarter AS (
    SELECT period, reporting_quarter, sum(provision) AS closing_provision,
           sum(exposure) AS exposure
    FROM vw_provision
    GROUP BY period, reporting_quarter
),
with_opening AS (
    SELECT period, reporting_quarter, exposure, closing_provision,
           coalesce(LAG(closing_provision) OVER (ORDER BY period), 0) AS opening_provision
    FROM by_quarter
)
SELECT
    period,
    reporting_quarter,
    opening_provision,
    -- Split the movement into a charge and a release so the direction is
    -- explicit rather than hidden in the sign of a single column.
    greatest(closing_provision - opening_provision, 0) AS increase,
    greatest(opening_provision - closing_provision, 0) AS decrease,
    closing_provision,
    closing_provision - opening_provision               AS net_movement,
    exposure,
    100.0 * closing_provision / nullif(exposure, 0)     AS coverage_ratio_pct,
    -- Reconciliation check: must be 0 on every row.
    round(opening_provision
          + greatest(closing_provision - opening_provision, 0)
          - greatest(opening_provision - closing_provision, 0)
          - closing_provision, 6)                       AS reconciliation_error
FROM with_opening
ORDER BY period;
