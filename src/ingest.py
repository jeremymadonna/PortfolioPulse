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

import datetime
import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO, "data")
CSV_PATH = os.path.join(DATA_DIR, "mortgage.csv")
DB_PATH = os.path.join(DATA_DIR, "arrearsiq.duckdb")

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
        -- Origination attributes SHOULD be constant across a loan's rows, but in
        -- this source they are not: 49 loans report more than one orig_time and
        -- 381 report more than one FICO. any_value() would pick arbitrarily and
        -- make the whole pipeline non-deterministic, so take the value reported
        -- at the loan's EARLIEST period and log the inconsistency.
        SELECT id,
               arg_min(orig_time, time)               AS orig_time,
               arg_min(first_time, time)              AS first_time,
               arg_min(mat_time, time)                AS mat_time,
               arg_min(FICO_orig_time, time)          AS fico,
               arg_min(LTV_orig_time, time)           AS original_ltv,
               arg_min(balance_orig_time, time)       AS original_balance,
               arg_min(Interest_Rate_orig_time, time) AS original_interest_rate,
               arg_min(investor_orig_time, time)      AS investor_flag,
               arg_min(REtype_CO_orig_time, time)     AS re_co,
               arg_min(REtype_PU_orig_time, time)     AS re_pu,
               arg_min(REtype_SF_orig_time, time)     AS re_sf
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


def build_dq_results(con):
    """The data quality register. Phase 1 seeds it; Phase 4 appends to it.

    Findings are recorded, never hidden. Where a defect IS corrected, the
    correction is logged here with its row count so the number can be traced.
    """
    con.execute("""
    CREATE TABLE IF NOT EXISTS dq_results (
        run_timestamp TIMESTAMP, phase VARCHAR, rule_name VARCHAR,
        severity VARCHAR, status VARCHAR, affected_rows BIGINT, detail VARCHAR)
    """)


# One timestamp for the whole run, set in main(). DuckDB's now() is per
# statement, which would give each finding a different run id and break any
# "show me this run's findings" query.
RUN_TS = None


def log_dq(con, phase, rule, severity, status, rows, detail):
    con.execute("INSERT INTO dq_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                [RUN_TS, phase, rule, severity, status, rows, detail])


def build_fact_loan_quarter(con):
    """The quarterly panel, one row per loan per period.

    Two defects in the source are handled here, both logged to dq_results:

    1. DUPLICATE LOAN-PERIODS. 339 loan-period pairs appear twice, 27 of them
       with conflicting balances. One row is kept per loan-period, choosing the
       LOWER balance as the conservative reading, and the drop is logged.

    2. PANEL GAPS. Around 1,485 loans are missing one or two periods mid-panel.
       These are forward-filled: the last reported balance, LTV, rate and status
       are carried into the gap. Every filled row is marked is_forward_filled so
       it can be excluded from any analysis that should only see reported data.
       The macro variables are NOT carried forward -- they are properties of the
       period, not the loan, so filled rows take the true value for that period.
    """
    # --- raw panel, deduplicated -------------------------------------------
    con.execute("""
    CREATE OR REPLACE TABLE stg_panel AS
    SELECT id AS loan_id, time AS period,
           balance_time, LTV_time, interest_rate_time, status_time,
           default_time, payoff_time
    FROM {src}
    -- Keep one row per loan-period, lowest balance first (conservative).
    QUALIFY row_number() OVER (PARTITION BY id, time ORDER BY balance_time ASC) = 1
    """.format(src=SRC))

    raw_rows = con.execute("SELECT count(*) FROM %s" % SRC).fetchone()[0]
    kept = con.execute("SELECT count(*) FROM stg_panel").fetchone()[0]
    dropped = raw_rows - kept
    log_dq(con, "1-ingest", "duplicate_loan_period", "HIGH",
           "FAIL" if dropped else "PASS", dropped,
           "Duplicate loan-period rows in source; kept the lower balance of each pair")

    inconsistent = con.execute("""
        SELECT count(*) FROM (
            SELECT id FROM %s GROUP BY id
            HAVING count(DISTINCT orig_time) > 1 OR count(DISTINCT FICO_orig_time) > 1
                OR count(DISTINCT LTV_orig_time) > 1 OR count(DISTINCT balance_orig_time) > 1)
    """ % SRC).fetchone()[0]
    log_dq(con, "1-ingest", "inconsistent_origination_attributes", "MEDIUM",
           "FAIL" if inconsistent else "PASS", inconsistent,
           "Loans whose origination attributes vary across their own rows; the "
           "value at the earliest period is used")

    # --- macro variables are period-level facts, held once ------------------
    con.execute("""
    CREATE OR REPLACE TABLE dim_period_macro AS
    SELECT time AS period, max(hpi_time) AS house_price_index,
           max(gdp_time) AS gdp_growth, max(uer_time) AS unemployment_rate
    FROM {src} GROUP BY time
    """.format(src=SRC))

    # --- forward-fill the gaps ---------------------------------------------
    con.execute("""
    CREATE OR REPLACE TABLE stg_panel_filled AS
    WITH bounds AS (
        SELECT loan_id, min(period) AS mn, max(period) AS mx
        FROM stg_panel GROUP BY loan_id
    ),
    spine AS (   -- every period between a loan's first and last report
        SELECT loan_id, unnest(generate_series(mn, mx)) AS period FROM bounds
    ),
    joined AS (
        SELECT s.loan_id, s.period,
               p.balance_time, p.LTV_time, p.interest_rate_time,
               p.status_time, p.default_time, p.payoff_time,
               p.loan_id IS NULL AS is_forward_filled
        FROM spine s LEFT JOIN stg_panel p USING (loan_id, period)
    )
    SELECT loan_id, period, is_forward_filled,
           last_value(balance_time      IGNORE NULLS) OVER w AS balance_time,
           last_value(LTV_time          IGNORE NULLS) OVER w AS LTV_time,
           last_value(interest_rate_time IGNORE NULLS) OVER w AS interest_rate_time,
           last_value(status_time       IGNORE NULLS) OVER w AS status_time,
           last_value(default_time      IGNORE NULLS) OVER w AS default_time,
           last_value(payoff_time       IGNORE NULLS) OVER w AS payoff_time
    FROM joined
    WINDOW w AS (PARTITION BY loan_id ORDER BY period
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    """)

    filled = con.execute(
        "SELECT count(*) FROM stg_panel_filled WHERE is_forward_filled").fetchone()[0]
    filled_loans = con.execute(
        "SELECT count(DISTINCT loan_id) FROM stg_panel_filled WHERE is_forward_filled").fetchone()[0]
    log_dq(con, "1-ingest", "panel_period_gap", "MEDIUM",
           "FAIL" if filled else "PASS", filled,
           "Missing mid-panel periods forward-filled across %d loans; rows marked "
           "is_forward_filled" % filled_loans)

    con.execute("""
    CREATE OR REPLACE TABLE fact_loan_quarter AS
    SELECT
        p.loan_id,
        p.period,
        {reporting}                               AS reporting_quarter,
        -- Quarters on book: the analogue of months on book.
        p.period - l.orig_time                    AS quarters_on_book,
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
        -- TRUE for rows synthesised to close a reporting gap. Exclude these
        -- from anything that must only see reported observations.
        p.is_forward_filled,
        m.house_price_index, m.gdp_growth, m.unemployment_rate,
        l.origination_vintage, l.credit_score_band, l.ltv_band,
        l.property_type, l.occupancy, l.focus_cohort, l.observed_from_origination
    FROM stg_panel_filled p
    JOIN dim_loan l        ON l.loan_id = p.loan_id
    LEFT JOIN dim_period_macro m ON m.period = p.period
    """.format(reporting=calendar("p.period"),
               cur_ltv_band=band_case("CAST(p.LTV_time AS INTEGER)", config.LTV_BANDS)))

    con.execute("DROP TABLE IF EXISTS stg_panel")
    con.execute("DROP TABLE IF EXISTS stg_panel_filled")


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

    print("\n--- data quality findings recorded at ingestion ---")
    print(con.execute("""SELECT rule_name, severity, status, affected_rows, detail
                         FROM dq_results WHERE phase='1-ingest'
                         AND run_timestamp=(SELECT max(run_timestamp) FROM dq_results)
                         ORDER BY rule_name
                      """).df().to_string(index=False))

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

    global RUN_TS
    RUN_TS = datetime.datetime.now()
    con = duckdb.connect(DB_PATH)
    print("building %s" % DB_PATH)
    verify_schema(con)
    build_dq_results(con)
    build_dim_loan(con)
    build_fact_loan_quarter(con)
    build_fact_credit_event(con)
    build_dim_date(con)
    report(con)
    con.close()
    print("\ndone")


if __name__ == "__main__":
    main()
