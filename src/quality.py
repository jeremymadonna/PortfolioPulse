"""Phase 4: data quality checks against the built warehouse.

Run:  python src/quality.py

Ten rules. Each returns a name, severity, pass/fail and an affected row count,
and every result is appended to dq_results with a run timestamp so the register
builds up a history across runs rather than being overwritten.

Two things worth knowing about how this is scoped.

First, these rules check the WAREHOUSE -- the tables downstream reporting
actually reads. Defects found and corrected during ingestion are logged
separately under phase '1-ingest', so the register shows both what was wrong in
the source and what remains in the model.

Second, nothing here cleans anything. A failing rule is reported and left
failing. Deciding what to do about it is a judgement call for the person who
owns the numbers, not something a script should make silently.
"""

import datetime
import os
import sys

import duckdb

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO, "data", "arrearsiq.duckdb")

# Severity drives the weighted score. A wrong balance matters more than a
# missing descriptive attribute, and the score should say so.
SEVERITY_WEIGHT = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

# Each rule is (name, severity, SQL returning a single count of BAD rows).
# A rule passes when that count is zero.
RULES = [
    ("duplicate_loan_period", "HIGH", """
        SELECT count(*) FROM (
            SELECT loan_id, period FROM fact_loan_quarter
            GROUP BY 1, 2 HAVING count(*) > 1)"""),

    ("negative_balance", "HIGH", """
        SELECT count(*) FROM fact_loan_quarter WHERE current_balance < 0"""),

    # A repaying loan's balance should fall. A rise means either a modification
    # that capitalised arrears, or a reporting error.
    ("balance_increased_on_amortising_loan", "MEDIUM", """
        SELECT count(*) FROM (
            SELECT current_balance - LAG(current_balance)
                       OVER (PARTITION BY loan_id ORDER BY period) AS delta,
                   status_code
            FROM fact_loan_quarter)
        WHERE delta > 1.0 AND status_code = 0"""),

    # Rows dated before the loan's own stated origination period.
    ("row_dated_before_origination", "MEDIUM", """
        SELECT count(*) FROM fact_loan_quarter WHERE quarters_on_book < 0"""),

    # Default and payoff are terminal in this dataset. A loan leaving a terminal
    # state would mean the panel contradicts itself.
    ("loan_left_terminal_status", "HIGH", """
        SELECT count(*) FROM (
            SELECT loan_id, period, status_code,
                   LAG(status_code) OVER (PARTITION BY loan_id ORDER BY period) AS prev
            FROM fact_loan_quarter)
        WHERE prev IN (1, 2) AND status_code <> prev"""),

    ("missing_credit_score", "MEDIUM", """
        SELECT count(*) FROM dim_loan WHERE credit_score IS NULL"""),

    ("missing_property_type", "LOW", """
        SELECT count(*) FROM dim_loan
        WHERE property_type IS NULL OR property_type = 'Other / not stated'"""),

    ("invalid_status_code", "HIGH", """
        SELECT count(*) FROM fact_loan_quarter WHERE status_code NOT IN (0, 1, 2)"""),

    # Every segmentation must add back to the same portfolio total. If one does
    # not, a loan is being double counted or dropped by that dimension.
    ("segment_balance_reconciliation", "HIGH", """
        SELECT count(*) FROM (
            SELECT s.segment_type, s.period, sum(s.active_balance) AS seg_total,
                   max(p.active_balance) AS portfolio_total
            FROM vw_segment_performance s
            JOIN vw_portfolio_summary p USING (period)
            GROUP BY 1, 2)
        WHERE abs(seg_total - portfolio_total) > 0.01"""),

    # Every period between the first and last must exist, with no holes.
    ("reporting_period_continuity", "MEDIUM", """
        SELECT CASE WHEN count(*) = max(period) - min(period) + 1 THEN 0 ELSE 1 END
        FROM dim_date"""),
]


def run_rules(con, run_ts):
    results = []
    for name, severity, sql in RULES:
        affected = con.execute(sql).fetchone()[0]
        status = "PASS" if affected == 0 else "FAIL"
        con.execute("INSERT INTO dq_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [run_ts, "4-quality", name, severity, status, affected, ""])
        results.append((name, severity, status, affected))
    return results


def quality_score(results):
    """Weighted score: the share of severity weight that passed.

    Weighting by severity rather than counting rules equally means a HIGH
    failure moves the score three times as far as a LOW one.
    """
    total = sum(SEVERITY_WEIGHT[s] for _, s, _, _ in results)
    passed = sum(SEVERITY_WEIGHT[s] for _, s, st, _ in results if st == "PASS")
    return 100.0 * passed / total if total else 100.0


def main():
    if not os.path.exists(DB_PATH):
        raise SystemExit("No database at %s -- run python src/ingest.py first." % DB_PATH)
    con = duckdb.connect(DB_PATH)
    run_ts = datetime.datetime.now()

    results = run_rules(con, run_ts)

    print("Data quality run %s" % run_ts.strftime("%Y-%m-%d %H:%M:%S"))
    print("-" * 74)
    print("  %-38s %-8s %-6s %12s" % ("RULE", "SEVERITY", "RESULT", "AFFECTED"))
    for name, severity, status, affected in results:
        print("  %-38s %-8s %-6s %12s" % (name, severity, status, "{:,}".format(affected)))

    score = quality_score(results)
    failed = [r for r in results if r[2] == "FAIL"]
    print("-" * 74)
    print("  Data Quality Score: %.1f / 100   (%d of %d rules passed)"
          % (score, len(results) - len(failed), len(results)))

    if failed:
        print("\n  %d rule(s) FAILED. Nothing has been cleaned or corrected." % len(failed))
        for name, severity, _, affected in failed:
            print("    - %s (%s): %s rows" % (name, severity, "{:,}".format(affected)))
        print("\n  Review these and decide how each should be handled before the"
              "\n  numbers are used. See docs/Data Quality Rules.md.")

    print("\n--- register history (all runs) ---")
    print(con.execute("""
        SELECT phase, status, count(*) AS rules, sum(affected_rows) AS affected_rows
        FROM dq_results GROUP BY 1, 2 ORDER BY 1, 2""").df().to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
