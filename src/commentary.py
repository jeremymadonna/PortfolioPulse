"""Phase 5: rule-based portfolio commentary.

Run:  python src/commentary.py [period]

Compares the latest reporting quarter to the one before it. Where a headline
indicator has moved by more than its threshold in config.py, a templated
sentence is emitted and the segment that contributed most to the move is named.

There is no language model here and there should not be one. Every sentence is
a template filled from a number that came out of a SQL view, which means the
commentary can be audited line by line against the warehouse. That is the point
of it: a reviewer can ask "where does that sentence come from" and be shown a
query.
"""

import datetime
import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO, "data", "portfoliopulse.duckdb")
OUT_DIR = os.path.join(REPO, "output")
T = config.COMMENTARY_THRESHOLDS


def money(x):
    """Format a balance the way a report would, not the way SQL returns it."""
    if x is None:
        return "n/a"
    for unit, div in (("bn", 1e9), ("m", 1e6), ("k", 1e3)):
        if abs(x) >= div:
            return "$%.2f%s" % (x / div, unit)
    return "$%.0f" % x


def direction(x):
    return "rose" if x > 0 else "fell"


def biggest_mover(con, period, column, ascending=False):
    """Name the segment that moved most on a given measure this quarter.

    Ranking contributions is what turns "the number moved" into "the number
    moved because of this", which is the difference between a chart and a
    piece of analysis.
    """
    row = con.execute("""
        SELECT segment_type, segment_value, {col} AS value
        FROM vw_segment_performance
        WHERE period = ? AND {col} IS NOT NULL AND active_loans > 50
        ORDER BY value {dir} LIMIT 1
    """.format(col=column, dir="ASC" if ascending else "DESC"), [period]).fetchone()
    return row


def build(con, period):
    lines = []
    add = lines.append

    cur = con.execute("SELECT * FROM vw_portfolio_summary WHERE period = ?", [period]).df()
    if cur.empty:
        raise SystemExit("No data for period %s" % period)
    c = cur.iloc[0]
    quarter = c["reporting_quarter"]

    add("PORTFOLIO PULSE - PORTFOLIO COMMENTARY")
    add("=" * 70)
    add("Reporting quarter : %s (period %d)" % (quarter, period))
    add("Generated         : %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    add("Basis             : rule-based, generated from the reporting views.")
    add("                    Provision figures are ILLUSTRATIVE, not an")
    add("                    accounting allowance. See docs/Known Assumptions.md.")
    add("")

    # --- balance -----------------------------------------------------------
    add("PORTFOLIO BALANCE")
    add("-" * 70)
    growth = c["balance_growth_pct"]
    add("Active balance stood at %s across %s loans, an average of %s per loan."
        % (money(c["active_balance"]), "{:,}".format(int(c["active_loans"])),
           money(c["average_balance"])))
    if growth is not None and abs(growth) >= T["balance_growth_pct"]:
        add("The book %s %.1f%% on the quarter, from %s."
            % (direction(growth), abs(growth), money(c["prior_active_balance"])))
        mover = biggest_mover(con, period, "balance_growth_pct", ascending=growth < 0)
        if mover:
            add("The largest single contributor was %s '%s', which %s %.1f%%."
                % (mover[0].lower(), mover[1], direction(mover[2]), abs(mover[2])))
    else:
        add("Balance was broadly flat on the quarter.")
    add("%s loans paid off (%s) and %s defaulted (%s)."
        % ("{:,}".format(int(c["payoffs"])), money(c["paid_off_balance"]),
           "{:,}".format(int(c["defaults"])), money(c["defaulted_balance"])))
    add("")

    # --- credit performance -------------------------------------------------
    add("CREDIT PERFORMANCE")
    add("-" * 70)
    prev = con.execute("SELECT * FROM vw_portfolio_summary WHERE period = ?",
                       [period - 1]).df()
    dr = c["quarterly_default_rate_pct"]
    add("The quarterly default rate was %.2f%% of loans active at the prior "
        "quarter end." % (dr or 0))
    if not prev.empty and prev.iloc[0]["quarterly_default_rate_pct"] is not None:
        move = (dr or 0) - prev.iloc[0]["quarterly_default_rate_pct"]
        if abs(move) >= T["default_rate_pct_points"]:
            add("That is %.2f percentage points %s than the prior quarter's %.2f%%."
                % (abs(move), "higher" if move > 0 else "lower",
                   prev.iloc[0]["quarterly_default_rate_pct"]))
            worst = biggest_mover(con, period, "quarterly_default_rate_pct")
            if worst and worst[2]:
                add("The highest default rate this quarter was in %s '%s' at %.2f%%."
                    % (worst[0].lower(), worst[1], worst[2]))
        else:
            add("The default rate was broadly stable on the quarter.")
    add("Unemployment stood at %.1f%% and the house price index at %.1f."
        % (c["unemployment_rate"], c["house_price_index"]))
    add("NOTE: this dataset carries no delinquency buckets, so no 30+ or 90+")
    add("arrears rate can be reported. See DATA.md.")
    add("")

    # --- provision ----------------------------------------------------------
    add("PROVISION MOVEMENT (ILLUSTRATIVE)")
    add("-" * 70)
    pm = con.execute("SELECT * FROM vw_provision_movement WHERE period = ?", [period]).df()
    if not pm.empty:
        p = pm.iloc[0]
        add("Provision closed at %s against exposure of %s, a coverage ratio "
            "of %.2f%%." % (money(p["closing_provision"]), money(p["exposure"]),
                            p["coverage_ratio_pct"]))
        if p["increase"] > 0:
            add("The quarter carried a charge of %s (opening %s)."
                % (money(p["increase"]), money(p["opening_provision"])))
        elif p["decrease"] > 0:
            add("The quarter carried a release of %s (opening %s)."
                % (money(p["decrease"]), money(p["opening_provision"])))
        else:
            add("Provision was unchanged on the quarter.")
        stage2 = con.execute("""
            SELECT 100.0 * sum(exposure) FILTER (WHERE ifrs9_stage = 'Stage 2')
                   / nullif(sum(exposure), 0) FROM vw_provision WHERE period = ?""",
            [period]).fetchone()[0]
        add("Stage 2 accounted for %.1f%% of exposure, staged on negative equity."
            % (stage2 or 0))
    add("")

    # --- data quality -------------------------------------------------------
    add("DATA QUALITY")
    add("-" * 70)
    dq = con.execute("""
        SELECT rule_name, severity, affected_rows FROM dq_results
        WHERE status = 'FAIL' AND run_timestamp = (SELECT max(run_timestamp)
              FROM dq_results WHERE phase = '4-quality')
        ORDER BY affected_rows DESC""").df()
    if dq.empty:
        add("All data quality rules passed on the most recent run.")
    else:
        add("%d rule(s) failed on the most recent run. Nothing has been cleaned."
            % len(dq))
        for _, r in dq.iterrows():
            add("  - %s (%s): %s rows"
                % (r["rule_name"], r["severity"], "{:,}".format(int(r["affected_rows"]))))
    add("")
    add("=" * 70)
    add("End of commentary. Every figure above is a value from a reporting view;")
    add("no narrative has been inferred beyond the thresholds in config.py.")
    return quarter, lines


def main():
    if not os.path.exists(DB_PATH):
        raise SystemExit("No database at %s -- run python src/ingest.py first." % DB_PATH)
    con = duckdb.connect(DB_PATH)
    period = int(sys.argv[1]) if len(sys.argv) > 1 else \
        con.execute("SELECT max(period) FROM vw_portfolio_summary").fetchone()[0]

    quarter, lines = build(con, period)
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    path = os.path.join(OUT_DIR, "commentary_%s.txt" % quarter)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwritten to %s (%d lines)" % (path, len(lines)))
    con.close()


if __name__ == "__main__":
    main()
