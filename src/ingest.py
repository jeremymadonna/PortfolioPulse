"""Phase 1: read mortgage.csv and build the star schema in DuckDB.

Run:  python src/ingest.py

Builds four tables:
  dim_loan           one row per loan, characteristics at origination
  fact_loan_quarter  one row per loan per period, the quarterly panel
  fact_credit_event  one row per loan that defaulted
  dim_date           one row per period

The grain is QUARTERLY. See src/config.py for why, and for the evidence behind
the calendar mapping.
"""

import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO, "data")
CSV_PATH = os.path.join(DATA_DIR, "mortgage.csv")
DB_PATH = os.path.join(DATA_DIR, "portfoliopulse.duckdb")

SRC = "read_csv('%s', header=true)" % CSV_PATH


def verify_schema(con):
    """Fail loudly if the file is not the dataset this project was built for.

    Cheaper than debugging a metric that is quietly wrong because a column was
    renamed or a code value changed meaning.
    """
    found = [r[0] for r in con.execute("DESCRIBE SELECT * FROM %s" % SRC).fetchall()]
    missing = [c for c in config.EXPECTED_COLUMNS if c not in found]
    if missing:
        raise SystemExit(
            "Schema mismatch in %s\n  missing columns: %s\n  found: %s\n"
            "This does not look like the Credit Risk Analytics mortgage panel. "
            "See DATA.md." % (CSV_PATH, ", ".join(missing), ", ".join(found))
        )

    checks = con.execute("""
        SELECT count(*)                                              AS rows,
               count(DISTINCT id)                                    AS loans,
               min(time) AS min_t, max(time) AS max_t,
               sum(CASE WHEN status_time NOT IN (0,1,2) THEN 1 ELSE 0 END) AS bad_status,
               sum(CASE WHEN FICO_orig_time NOT BETWEEN 300 AND 900 THEN 1 ELSE 0 END) AS bad_fico,
               sum(CASE WHEN balance_time < 0 THEN 1 ELSE 0 END)     AS negative_balance
        FROM %s""" % SRC).fetchone()
    rows, loans, min_t, max_t, bad_status, bad_fico, neg_bal = checks
    print("  schema check: %s" % os.path.basename(CSV_PATH))
    print("    %s rows, %s loans, periods %d..%d" % ("{:,}".format(rows), "{:,}".format(loans), min_t, max_t))
    for label, bad in (("status_time not in (0,1,2)", bad_status),
                       ("FICO outside 300-900", bad_fico),
                       ("negative balance", neg_bal)):
        print("    %-30s %s  %s" % (label, "{:,}".format(bad), "ok" if bad == 0 else "SEE DATA QUALITY"))


def band_case(column, bands):
    """CASE expression putting a numeric column into named bands."""
    whens = "\n        ".join("WHEN %s BETWEEN %d AND %d THEN '%s'" % (column, lo, hi, n)
                              for lo, hi, n in bands)
    return "CASE\n        %s\n        ELSE '9. Unknown'\n    END" % whens


def calendar(period_expr):
    """Map an integer period to a calendar quarter label.

    Derived, not given: see CALENDAR_ANCHOR in config.py. Metrics are always
    computed on the raw integer period, so this only ever affects labels.
    """
    if config.CALENDAR_ANCHOR is None:
        return "'P' || CAST(%s AS VARCHAR)" % period_expr
    y, q = config.CALENDAR_ANCHOR
    base = y * 4 + (q - 1)
    total = "(%d + (%s) - 1)" % (base, period_expr)
    # Single %, because this string is built with .format(), not %-formatting;
    # and // because DuckDB's / is float division and the year must stay integral.
    return "printf('%dQ%d', {t} // 4, {t} % 4 + 1)".format(t=total)


def build_dim_loan(con):
    con.execute("""
    CREATE OR REPLACE TABLE dim_loan AS
    WITH one_row_per_loan AS (
        -- Origination attributes repeat on every panel row; take them once.
        SELECT id,
               any_value(orig_time)               AS orig_time,
               any_value(first_time)              AS first_time,
               any_value(mat_time)                AS mat_time,
               any_value(FICO_orig_time)          AS fico,
               any_value(LTV_orig_time)           AS original_ltv,
               any_value(balance_orig_time)       AS original_balance,
               any_value(Interest_Rate_orig_time) AS original_interest_rate,
               any_value(investor_orig_time)      AS investor_flag,
               any_value(REtype_CO_orig_time)     AS re_co,
               any_value(REtype_PU_orig_time)     AS re_pu,
               any_value(REtype_SF_orig_time)     AS re_sf
        FROM {src} GROUP BY id
    )
    SELECT
        id                                        AS loan_id,
        orig_time, first_time, mat_time,
        mat_time - orig_time                      AS original_term_quarters,
        {vintage}                                 AS origination_vintage,
        fico                                      AS credit_score,
        original_ltv, original_balance, original_interest_rate,
        -- Property type arrives as three one-hot flags; all-zero is a real
        -- category in this file (9,822 loans), not a defect.
        CASE WHEN re_sf = 1 THEN 'Single family'
             WHEN re_pu = 1 THEN 'Planned urban'
             WHEN re_co = 1 THEN 'Condominium'
             ELSE 'Other / not stated' END        AS property_type,
        CASE WHEN investor_flag = 1 THEN 'Investor'
             ELSE 'Owner occupied' END            AS occupancy,
        {fico_band}                               AS credit_score_band,
        {ltv_band}                                AS ltv_band,
        -- Cohorts originated before the observation window are left censored.
        orig_time >= {min_orig}                   AS observed_from_origination,
        CASE WHEN orig_time = {benign}   THEN 'Benign cohort'
             WHEN orig_time = {stressed} THEN 'Stressed cohort'
             ELSE NULL END                        AS focus_cohort
    FROM one_row_per_loan
    """.format(src=SRC,
               vintage=calendar("orig_time"),
               fico_band=band_case("fico", config.FICO_BANDS),
               ltv_band=band_case("CAST(original_ltv AS INTEGER)", config.LTV_BANDS),
               min_orig=config.MIN_OBSERVABLE_ORIG_TIME,
               benign=config.BENIGN_VINTAGE, stressed=config.STRESSED_VINTAGE))


def build_fact_loan_quarter(con):
    con.execute("""
    CREATE OR REPLACE TABLE fact_loan_quarter AS
    SELECT
        p.id                                      AS loan_id,
        p.time                                    AS period,
        {reporting}                               AS reporting_quarter,
        -- Quarters on book: the analogue of months on book. Period 1 of a
        -- loan's life is the quarter after origination.
        p.time - p.orig_time                      AS quarters_on_book,
        p.balance_time                            AS current_balance,
        p.LTV_time                                AS current_ltv,
        {cur_ltv_band}                            AS current_ltv_band,
        p.interest_rate_time                      AS current_interest_rate,
        p.status_time                             AS status_code,
        CASE p.status_time WHEN 0 THEN '1. Active'
                           WHEN 1 THEN '2. Default'
                           WHEN 2 THEN '3. Payoff'
                           ELSE '9. Unknown' END  AS status_bucket,
        p.default_time, p.payoff_time,
        -- Macro covariates travel with the panel, so commentary can name the
        -- cycle rather than just report that a number moved.
        p.hpi_time                                AS house_price_index,
        p.gdp_time                                AS gdp_growth,
        p.uer_time                                AS unemployment_rate,
        l.origination_vintage, l.credit_score_band, l.ltv_band,
        l.property_type, l.occupancy, l.focus_cohort, l.observed_from_origination
    FROM {src} p
    JOIN dim_loan l ON l.loan_id = p.id
    """.format(src=SRC, reporting=calendar("p.time"),
               cur_ltv_band=band_case("CAST(p.LTV_time AS INTEGER)", config.LTV_BANDS)))


def build_fact_credit_event(con):
    """One row per loan that defaulted.

    A credit event here is a default: status_time = 1. This dataset carries NO
    recovery, expense or realised-loss amounts, so loss severity (loss given
    default) CANNOT be computed and is deliberately absent rather than guessed.
    What is observable is exposure at default -- the balance still outstanding
    when the loan defaulted -- and the current loan-to-value at that moment,
    which is the collateral position that would drive severity.
    """
    con.execute("""
    CREATE OR REPLACE TABLE fact_credit_event AS
    WITH first_default AS (
        SELECT loan_id, min(period) AS default_period
        FROM fact_loan_quarter WHERE status_code = 1 GROUP BY loan_id
    )
    SELECT
        f.loan_id,
        f.default_period,
        q.reporting_quarter                       AS default_quarter,
        q.quarters_on_book                        AS quarters_on_book_at_default,
        q.current_balance                         AS exposure_at_default,
        q.current_ltv                             AS ltv_at_default,
        q.current_ltv_band                        AS ltv_band_at_default,
        l.original_balance,
        l.credit_score, l.credit_score_band, l.ltv_band, l.origination_vintage,
        l.property_type, l.occupancy, l.focus_cohort,
        q.house_price_index, q.unemployment_rate
    FROM first_default f
    JOIN fact_loan_quarter q ON q.loan_id = f.loan_id AND q.period = f.default_period
    JOIN dim_loan l          ON l.loan_id = f.loan_id
    """)


def build_dim_date(con):
    con.execute("""
    CREATE OR REPLACE TABLE dim_date AS
    SELECT DISTINCT
        period,
        reporting_quarter,
        CAST(split_part(reporting_quarter, 'Q', 1) AS INTEGER) AS year,
        CAST(split_part(reporting_quarter, 'Q', 2) AS INTEGER) AS quarter
    FROM fact_loan_quarter ORDER BY period
    """)


def report(con):
    print("\n--- row counts ---")
    for t in ("dim_loan", "fact_loan_quarter", "fact_credit_event", "dim_date"):
        n = con.execute("SELECT count(*) FROM " + t).fetchone()[0]
        print("  %-20s %12s" % (t, "{:,}".format(n)))

    print("\n--- period range check (no gaps expected) ---")
    r = con.execute("""SELECT min(period), max(period), count(*),
                              max(period)-min(period)+1 AS expected FROM dim_date""").fetchone()
    print("  periods %d..%d present=%d expected=%d  %s"
          % (r[0], r[1], r[2], r[3], "ok" if r[2] == r[3] else "GAPS PRESENT"))
    print("  calendar: period %d = %s, period %d = %s"
          % (r[0], con.execute("SELECT reporting_quarter FROM dim_date WHERE period=?", [r[0]]).fetchone()[0],
             r[1], con.execute("SELECT reporting_quarter FROM dim_date WHERE period=?", [r[1]]).fetchone()[0]))

    print("\n--- the two focus cohorts ---")
    print(con.execute("""
        SELECT l.focus_cohort, l.origination_vintage, count(*) AS loans,
               round(avg(l.credit_score))                       AS avg_fico,
               round(avg(l.original_ltv), 1)                    AS avg_ltv,
               round(100.0 * sum(CASE WHEN e.loan_id IS NOT NULL THEN 1 ELSE 0 END)
                     / count(*), 1)                             AS lifetime_default_pct
        FROM dim_loan l LEFT JOIN fact_credit_event e USING (loan_id)
        WHERE l.focus_cohort IS NOT NULL
        GROUP BY 1, 2 ORDER BY 1
    """).df().to_string(index=False))

    print("\n--- exposure at default (loss severity is NOT available in this source) ---")
    print(con.execute("""
        SELECT origination_vintage, count(*) AS defaults,
               round(sum(exposure_at_default)/1e6, 1) AS exposure_at_default_m,
               round(avg(ltv_at_default), 1)          AS avg_ltv_at_default,
               round(avg(quarters_on_book_at_default), 1) AS avg_qob_at_default
        FROM fact_credit_event WHERE focus_cohort IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """).df().to_string(index=False))


def main():
    if not os.path.exists(CSV_PATH):
        raise SystemExit(
            "Missing %s\n\nThe data is not committed to this repo. See DATA.md "
            "for where to download it." % CSV_PATH)

    con = duckdb.connect(DB_PATH)
    print("building %s" % DB_PATH)
    verify_schema(con)
    build_dim_loan(con)
    build_fact_loan_quarter(con)
    build_fact_credit_event(con)
    build_dim_date(con)
    report(con)
    con.close()
    print("\ndone")


if __name__ == "__main__":
    main()
