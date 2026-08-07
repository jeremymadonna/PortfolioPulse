"""Phase 1: read the raw Freddie Mac files and build the star schema in DuckDB.

Run:  python src/ingest.py

Builds four tables:
  dim_loan          one row per loan, characteristics at origination
  fact_loan_month   one row per loan per reporting month, the monthly panel
  fact_credit_event one row per loan that defaulted into a loss
  dim_date          one row per reporting month

The raw files are pipe-delimited with no header row, so every column is read by
POSITION using the layout in layouts.py. verify_layout() proves that mapping is
correct from the file contents before any table is built.
"""

import os
import re
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layouts

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO, "data")
DB_PATH = os.path.join(DATA_DIR, "portfoliopulse.duckdb")


def raw_csv(path, fields):
    """A DuckDB read_csv() call that names the first len(fields) columns.

    Everything is read as text and cast explicitly later. Later editions of the
    User Guide append extra columns; those are simply not referenced.
    """
    cols = ",\n           ".join(
        '"column%02d" AS %s' % (i, name) for i, name in enumerate(fields)
    )
    return (
        "SELECT %s\n    FROM read_csv('%s', delim='|', header=false, quote='',\n"
        "                  all_varchar=true, null_padding=true, ignore_errors=false)"
        % (cols, path)
    )


# --- Layout verification -----------------------------------------------------
# A wrong column offset does not raise an error, it silently produces wrong
# numbers. These probes check that each key column actually contains what its
# name claims, so a layout change in a newer User Guide fails loudly here
# instead of quietly corrupting every metric downstream.

ORIGINATION_PROBES = [
    ("loan_sequence_number", r'^F\d{3}Q\d{7}$', 0.99),
    ("first_payment_date", r'^\d{6}$', 0.99),
    ("maturity_date", r'^\d{6}$', 0.99),
    ("property_state", r'^[A-Z]{2}$', 0.99),
    ("credit_score", r'^\d{1,4}$', 0.95),
    ("original_upb", r'^\d+$', 0.99),
    ("loan_purpose", r'^[PCN]$', 0.95),
    ("occupancy_status", r'^[PSI]$', 0.95),
    ("channel", r'^[RBCT]$', 0.95),
]

PERFORMANCE_PROBES = [
    ("loan_sequence_number", r'^F\d{3}Q\d{7}$', 0.99),
    ("monthly_reporting_period", r'^\d{6}$', 0.99),
    ("current_loan_delinquency_status", r'^(\d{1,2}|R|RA|XX)?$', 0.99),
    ("current_actual_upb", r'^-?\d*\.?\d*$', 0.99),
    ("zero_balance_code", r'^(0[13569]|15|96|97|98)?$', 0.99),
]


def verify_layout(con, path, fields, probes, label):
    """Prove the positional mapping from the data itself. Raises on mismatch."""
    src = raw_csv(path, fields)
    checks = ", ".join(
        "avg(CASE WHEN regexp_matches(coalesce(trim(%s),''), '%s') THEN 1 ELSE 0 END) AS %s"
        % (col, rx, col)
        for col, rx, _ in probes
    )
    row = con.execute(
        "SELECT %s FROM (%s) USING SAMPLE 200000 ROWS (reservoir, 7)" % (checks, src)
    ).fetchone()

    print("  layout check: %s" % label)
    failures = []
    for (col, rx, threshold), rate in zip(probes, row):
        ok = rate is not None and rate >= threshold
        print("    %-34s %6.2f%% match  %s" % (col, 100 * (rate or 0), "ok" if ok else "FAIL"))
        if not ok:
            failures.append((col, rx, rate))
    if failures:
        raise SystemExit(
            "\nLAYOUT MISMATCH in %s\n"
            "  %s\n"
            "The column positions in src/layouts.py do not match this file. That layout\n"
            "was transcribed from the August 2018 General User Guide; your download is\n"
            "probably a newer edition that inserted or reordered a field.\n"
            "Fix: open your User Guide's file layout table and correct src/layouts.py.\n"
            % (path, "\n  ".join("%s matched only %.2f%% of rows" % (c, 100 * (r or 0))
                                 for c, _, r in failures))
        )


# --- SQL fragments -----------------------------------------------------------

def band_case(column, bands):
    """Build a CASE expression that puts a numeric column into named bands."""
    whens = "\n        ".join(
        "WHEN %s BETWEEN %d AND %d THEN '%s'" % (column, lo, hi, name)
        for lo, hi, name in bands
    )
    return "CASE\n        %s\n        ELSE '9. Unknown'\n    END" % whens


# Months on book: month 1 is the first scheduled payment month, so a loan is at
# month-on-book 1 in the month its first payment was due.
MONTHS_ON_BOOK = """
    (CAST(substr(p.monthly_reporting_period, 1, 4) AS INTEGER) * 12
       + CAST(substr(p.monthly_reporting_period, 5, 2) AS INTEGER))
  - (CAST(substr(l.first_payment_date, 1, 4) AS INTEGER) * 12
       + CAST(substr(l.first_payment_date, 5, 2) AS INTEGER)) + 1
"""

# Delinquency status is whole MONTHS past due under the MBA method.
# Terminal states come from the zero balance code and take precedence, because
# on the month a loan terminates the delinquency status is no longer the story.
DELINQUENCY_BUCKET = """
CASE
    WHEN p.zero_balance_code IN ('03', '09')            THEN '8. Credit event'
    WHEN p.zero_balance_code = '01'                     THEN '7. Prepaid'
    WHEN p.current_loan_delinquency_status = 'R'        THEN '6. REO'
    WHEN TRY_CAST(p.current_loan_delinquency_status AS INTEGER) = 0 THEN '0. Current'
    WHEN TRY_CAST(p.current_loan_delinquency_status AS INTEGER) = 1 THEN '1. 30 days'
    WHEN TRY_CAST(p.current_loan_delinquency_status AS INTEGER) = 2 THEN '2. 60 days'
    WHEN TRY_CAST(p.current_loan_delinquency_status AS INTEGER) = 3 THEN '3. 90 days'
    WHEN TRY_CAST(p.current_loan_delinquency_status AS INTEGER) BETWEEN 4 AND 5
                                                        THEN '4. 120-150 days'
    WHEN TRY_CAST(p.current_loan_delinquency_status AS INTEGER) >= 6
                                                        THEN '5. Seriously delinquent'
    ELSE '9. Unknown'
END
"""


def build_dim_loan(con, vintages):
    """One row per loan, sampled down to LOANS_PER_VINTAGE per vintage."""
    parts = []
    for vintage in vintages:
        path = os.path.join(DATA_DIR, "sample_orig_%d.txt" % vintage)
        verify_layout(con, path, layouts.ORIGINATION_FIELDS, ORIGINATION_PROBES,
                      "sample_orig_%d.txt" % vintage)
        # Wrapped in an outer SELECT because a UNION ALL branch cannot carry
        # its own ORDER BY / LIMIT directly.
        parts.append("""
        SELECT * FROM (
            SELECT * FROM (%s)
            -- The last 6 characters of the loan sequence number are randomly
            -- assigned by Freddie Mac, so ordering by them and taking the first
            -- N is a reproducible random sample that does not favour any
            -- origination quarter (ordering by the whole id over-weights Q1).
            ORDER BY substr(loan_sequence_number, 7, 6)
            LIMIT %d
        )
        """ % (raw_csv(path, layouts.ORIGINATION_FIELDS), layouts.LOANS_PER_VINTAGE))

    con.execute("CREATE OR REPLACE TABLE stg_origination AS " + "\nUNION ALL\n".join(parts))

    con.execute("""
    CREATE OR REPLACE TABLE dim_loan AS
    SELECT
        loan_sequence_number,
        first_payment_date,
        -- Vintage is encoded in the id itself: F1 YY Q n. '99' means 1999.
        CASE WHEN CAST(substr(loan_sequence_number, 3, 2) AS INTEGER) >= 99
             THEN 1900 + CAST(substr(loan_sequence_number, 3, 2) AS INTEGER)
             ELSE 2000 + CAST(substr(loan_sequence_number, 3, 2) AS INTEGER)
        END                                             AS origination_year,
        CAST(substr(loan_sequence_number, 6, 1) AS INTEGER) AS origination_quarter,
        NULLIF(TRY_CAST(credit_score AS INTEGER), 9999)  AS credit_score,
        NULLIF(TRY_CAST(original_ltv AS INTEGER), 999)   AS original_ltv,
        NULLIF(TRY_CAST(original_cltv AS INTEGER), 999)  AS original_cltv,
        NULLIF(TRY_CAST(original_dti AS INTEGER), 999)   AS original_dti,
        TRY_CAST(original_upb AS BIGINT)                 AS original_upb,
        TRY_CAST(original_interest_rate AS DOUBLE)       AS original_interest_rate,
        loan_purpose, occupancy_status, property_type, property_state, channel,
        TRY_CAST(number_of_borrowers AS INTEGER)         AS number_of_borrowers,
        TRY_CAST(original_loan_term AS INTEGER)          AS original_loan_term,
        TRY_CAST(mi_percent AS INTEGER)                  AS mi_percent
    FROM stg_origination
    """)

    # Bands are added as a second step so the CASE expressions can reference the
    # already-cleaned numeric columns rather than the raw text.
    con.execute("""
    CREATE OR REPLACE TABLE dim_loan AS
    SELECT *,
        printf('%dQ%d', origination_year, origination_quarter) AS origination_vintage,
        {score} AS credit_score_band,
        {ltv}   AS ltv_band,
        {dti}   AS dti_band
    FROM dim_loan
    """.format(
        score=band_case("credit_score", layouts.CREDIT_SCORE_BANDS),
        ltv=band_case("original_ltv", layouts.LTV_BANDS),
        dti=band_case("original_dti", layouts.DTI_BANDS),
    ))


def build_fact_loan_month(con, vintages):
    """The monthly panel: one row per loan per reporting month, capped at 48 MOB."""
    parts = []
    for vintage in vintages:
        path = os.path.join(DATA_DIR, "sample_svcg_%d.txt" % vintage)
        verify_layout(con, path, layouts.PERFORMANCE_FIELDS, PERFORMANCE_PROBES,
                      "sample_svcg_%d.txt" % vintage)
        parts.append("SELECT * FROM (%s)" % raw_csv(path, layouts.PERFORMANCE_FIELDS))

    con.execute("CREATE OR REPLACE TABLE stg_performance AS " + "\nUNION ALL\n".join(parts))

    con.execute("""
    CREATE OR REPLACE TABLE fact_loan_month AS
    SELECT
        p.loan_sequence_number,
        p.monthly_reporting_period,
        TRY_CAST(p.current_actual_upb AS DOUBLE)                    AS current_actual_upb,
        trim(p.current_loan_delinquency_status)                     AS current_loan_delinquency_status,
        {bucket}                                                    AS delinquency_bucket,
        {mob}                                                       AS months_on_book,
        TRY_CAST(p.loan_age AS INTEGER)                             AS loan_age,
        TRY_CAST(p.remaining_months_to_legal_maturity AS INTEGER)   AS remaining_months_to_maturity,
        nullif(trim(p.modification_flag), '')                       AS modification_flag,
        nullif(trim(p.zero_balance_code), '')                       AS zero_balance_code,
        nullif(trim(p.zero_balance_effective_date), '')             AS zero_balance_effective_date,
        TRY_CAST(p.current_interest_rate AS DOUBLE)                 AS current_interest_rate,
        l.origination_vintage,
        l.origination_year
    FROM stg_performance p
    -- Inner join restricts the panel to the sampled loans only.
    JOIN dim_loan l USING (loan_sequence_number)
    WHERE {mob} BETWEEN 1 AND {cap}
    """.format(bucket=DELINQUENCY_BUCKET, mob=MONTHS_ON_BOOK, cap=layouts.MAX_MONTHS_ON_BOOK))


def build_fact_credit_event(con):
    """One row per loan that defaulted into a loss.

    Loss severity is the mortgage industry's term for loss given default: the
    share of the defaulted balance that was actually lost after recoveries and
    expenses. It is only meaningful where Freddie Mac actually computed a loss,
    so the User Guide's zero-by-rule cases are carried through as flags rather
    than silently averaged in.
    """
    con.execute("""
    CREATE OR REPLACE TABLE fact_credit_event AS
    WITH events AS (
        -- Zero balance codes 03 and 09 are the distressed dispositions:
        -- short sale / third party sale / charge off, and REO disposition.
        SELECT p.*
        FROM stg_performance p
        JOIN dim_loan USING (loan_sequence_number)
        WHERE trim(p.zero_balance_code) IN ('03', '09')
    ),
    last_positive_upb AS (
        -- UPB at default: on the disposition row the balance is already zero,
        -- so the defaulted balance is the last positive balance observed.
        SELECT loan_sequence_number,
               argMax(TRY_CAST(current_actual_upb AS DOUBLE), monthly_reporting_period)
                   AS upb_at_default
        FROM stg_performance
        WHERE TRY_CAST(current_actual_upb AS DOUBLE) > 0
        GROUP BY loan_sequence_number
    )
    SELECT
        e.loan_sequence_number,
        nullif(trim(e.zero_balance_effective_date), '')      AS disposition_date,
        trim(e.zero_balance_code)                            AS zero_balance_code,
        u.upb_at_default,
        TRY_CAST(e.net_sales_proceeds AS DOUBLE)             AS net_sales_proceeds,
        -- 'C' = Freddie Mac was covered in full, 'U' = unknown. In both cases the
        -- User Guide says actual loss is forced to zero, so they are not real
        -- zero-loss defaults and must be excluded from severity averages.
        trim(e.net_sales_proceeds)                           AS net_sales_proceeds_code,
        nullif(trim(e.repurchase_flag), '')                  AS repurchase_flag,
        TRY_CAST(e.mi_recoveries AS DOUBLE)                  AS mi_recoveries,
        TRY_CAST(e.non_mi_recoveries AS DOUBLE)              AS non_mi_recoveries,
        TRY_CAST(e.expenses AS DOUBLE)                       AS expenses,
        TRY_CAST(e.actual_loss_calculation AS DOUBLE)        AS actual_loss,
        CASE WHEN trim(e.repurchase_flag) = 'Y'              THEN false
             WHEN trim(e.net_sales_proceeds) IN ('C', 'U')   THEN false
             WHEN TRY_CAST(e.actual_loss_calculation AS DOUBLE) IS NULL THEN false
             ELSE true
        END                                                  AS loss_is_measurable,
        CASE WHEN u.upb_at_default > 0
                  AND trim(e.repurchase_flag) IS DISTINCT FROM 'Y'
                  AND trim(e.net_sales_proceeds) NOT IN ('C', 'U')
             THEN TRY_CAST(e.actual_loss_calculation AS DOUBLE) / u.upb_at_default
        END                                                  AS loss_severity
    FROM events e
    LEFT JOIN last_positive_upb u USING (loan_sequence_number)
    """)


def build_dim_date(con):
    con.execute("""
    CREATE OR REPLACE TABLE dim_date AS
    SELECT DISTINCT
        monthly_reporting_period                                   AS reporting_month,
        CAST(substr(monthly_reporting_period, 1, 4) AS INTEGER)    AS year,
        CAST(substr(monthly_reporting_period, 5, 2) AS INTEGER)    AS month,
        'Q' || CAST((CAST(substr(monthly_reporting_period, 5, 2) AS INTEGER) - 1) / 3 + 1
                    AS INTEGER)                                    AS quarter
    FROM fact_loan_month
    ORDER BY reporting_month
    """)


def report(con):
    print("\n--- row counts ---")
    for t in ("dim_loan", "fact_loan_month", "fact_credit_event", "dim_date"):
        print("  %-20s %12s" % (t, "{:,}".format(con.execute("SELECT count(*) FROM " + t).fetchone()[0])))

    print("\n--- loans and date range by vintage ---")
    for row in con.execute("""
        SELECT origination_year,
               count(DISTINCT origination_vintage) AS vintage_quarters,
               count(DISTINCT loan_sequence_number) AS loans,
               min(monthly_reporting_period) AS first_month,
               max(monthly_reporting_period) AS last_month,
               min(months_on_book) AS min_mob,
               max(months_on_book) AS max_mob
        FROM fact_loan_month GROUP BY 1 ORDER BY 1
    """).fetchall():
        print("  %s  %dQ  loans=%-7s %s..%s  mob %s..%s" % row)

    print("\n--- date range check: every month present, no gaps ---")
    for row in con.execute("""
        SELECT substr(reporting_month, 1, 4) AS yr, count(*) AS months
        FROM dim_date GROUP BY 1 ORDER BY 1
    """).fetchall():
        print("  %s  %2d months" % row)

    print("\n--- credit events ---")
    print(con.execute("""
        SELECT zero_balance_code,
               count(*) AS events,
               CAST(sum(CASE WHEN loss_is_measurable THEN 1 ELSE 0 END) AS INTEGER) AS with_measurable_loss,
               round(avg(loss_severity), 4) AS avg_loss_severity
        FROM fact_credit_event GROUP BY 1 ORDER BY 1
    """).df().to_string(index=False))


def main():
    missing = [f for v in layouts.VINTAGES
               for f in (os.path.join(DATA_DIR, "sample_orig_%d.txt" % v),
                         os.path.join(DATA_DIR, "sample_svcg_%d.txt" % v))
               if not os.path.exists(f)]
    if missing:
        raise SystemExit(
            "Missing raw data files:\n  " + "\n  ".join(missing) +
            "\n\nThe data is not committed to this repo. See DATA.md for how to "
            "register with Clarity Data Intelligence and download the sample files."
        )

    con = duckdb.connect(DB_PATH)
    print("building %s" % DB_PATH)
    build_dim_loan(con, layouts.VINTAGES)
    build_fact_loan_month(con, layouts.VINTAGES)
    build_fact_credit_event(con)
    build_dim_date(con)
    con.execute("DROP TABLE IF EXISTS stg_origination")
    con.execute("DROP TABLE IF EXISTS stg_performance")
    report(con)
    con.close()
    print("\ndone")


if __name__ == "__main__":
    main()
