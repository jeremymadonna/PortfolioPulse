"""Export the reporting views to flat CSVs for Power BI / Tableau.

Run:  python export.py

Writes one CSV per view into powerbi/. Those files are gitignored: they are
derived from data this repo does not redistribute, so they are rebuilt rather
than committed.
"""

import os

import duckdb

REPO = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(REPO, "data", "portfoliopulse.duckdb")
OUT_DIR = os.path.join(REPO, "powerbi")

# The dimensions go too, so the BI tool can build its own relationships rather
# than relying on everything being pre-joined into one wide table.
EXPORTS = [
    "vw_portfolio_summary", "vw_segment_performance", "vw_delinquency",
    "vw_roll_rates", "vw_vintage_performance", "vw_loss_recovery",
    "vw_provision", "vw_provision_movement",
    "dim_loan", "dim_date", "fact_credit_event", "dq_results",
]


def main():
    if not os.path.exists(DB_PATH):
        raise SystemExit("No database at %s -- run python src/ingest.py first." % DB_PATH)
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    con = duckdb.connect(DB_PATH, read_only=True)
    print("exporting to %s" % OUT_DIR)
    for name in EXPORTS:
        path = os.path.join(OUT_DIR, name + ".csv")
        con.execute("COPY (SELECT * FROM %s) TO '%s' (HEADER, DELIMITER ',')" % (name, path))
        rows = con.execute("SELECT count(*) FROM %s" % name).fetchone()[0]
        print("  %-28s %10s rows  %6.1f KB"
              % (name, "{:,}".format(rows), os.path.getsize(path) / 1024))
    con.close()
    print("\ndone")


if __name__ == "__main__":
    main()
