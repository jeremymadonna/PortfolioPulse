-- BUSINESS QUESTION: How much of the book is performing, and how much is going
-- bad each quarter -- overall and by segment?
--
-- IMPORTANT LIMITATION. The brief asks for balance and count by delinquency
-- bucket with 30+, 60+ and 90+ rates. This dataset has NO days-past-due field
-- and no delinquency buckets: a loan is only ever active, defaulted or paid
-- off. So the bucket distribution is a status distribution, and the arrears
-- rates are replaced by a default rate. Nothing here is a stand-in for a 30+
-- rate; that metric simply cannot be produced from this source. See DATA.md.
CREATE OR REPLACE VIEW vw_delinquency AS
WITH by_segment AS (
    SELECT period, reporting_quarter, segment_type, segment_value,
           status_bucket, current_balance, status_code
    FROM (
        SELECT period, reporting_quarter, 'Portfolio' AS segment_type,
               'Total' AS segment_value, status_bucket, current_balance, status_code
        FROM fact_loan_quarter
        UNION ALL SELECT period, reporting_quarter, 'Credit score band',
               credit_score_band, status_bucket, current_balance, status_code
        FROM fact_loan_quarter
        UNION ALL SELECT period, reporting_quarter, 'LTV band (at origination)',
               ltv_band, status_bucket, current_balance, status_code
        FROM fact_loan_quarter
        UNION ALL SELECT period, reporting_quarter, 'Origination vintage',
               origination_vintage, status_bucket, current_balance, status_code
        FROM fact_loan_quarter
    )
)
SELECT
    segment_type, segment_value, period, reporting_quarter, status_bucket,
    count(*)             AS loans,
    sum(current_balance) AS balance,
    -- Share of that segment's loans sitting in this status this quarter.
    100.0 * count(*)
        / nullif(sum(count(*)) OVER (PARTITION BY segment_type, segment_value, period), 0)
                         AS pct_of_segment_loans,
    100.0 * sum(current_balance)
        / nullif(sum(sum(current_balance)) OVER (PARTITION BY segment_type, segment_value, period), 0)
                         AS pct_of_segment_balance
FROM by_segment
GROUP BY segment_type, segment_value, period, reporting_quarter, status_bucket
ORDER BY segment_type, segment_value, period, status_bucket;
