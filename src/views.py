"""Phase 2: create the six reporting views in DuckDB.

Run:  python src/views.py

Every reporting metric lives in a .sql file under sql/, never in Pandas. This
module only reads those files and executes them, so the SQL stays the single
source of truth for what each number means.
"""

import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(REPO, "sql")
DB_PATH = os.path.join(REPO, "data", "portfoliopulse.duckdb")

# Order matters only in that each view is independent; listed explicitly so a
# stray .sql file in the directory cannot silently become part of the pipeline.
VIEWS = [
    "vw_portfolio_summary",
    "vw_segment_performance",
    "vw_delinquency",
    "vw_roll_rates",
    "vw_vintage_performance",
    "vw_loss_recovery",
    "vw_provision",            # Phase 3
    "vw_provision_movement",   # Phase 3
]

# Values the SQL needs but should not hard-code, so an assumption lives in
# exactly one place. Files without these placeholders are unaffected.
SQL_PARAMS = {
    "sicr_ltv": config.SICR_LTV_THRESHOLD,
    "lgd": config.ASSUMED_LOSS_GIVEN_DEFAULT,
    "horizon": config.PD_HORIZON_QUARTERS,
}


def create_views(con):
    for name in VIEWS:
        path = os.path.join(SQL_DIR, name + ".sql")
        with open(path) as f:
            sql = f.read()
        # Only .format() files that actually use placeholders, so SQL containing
        # literal braces is never mangled.
        if any("{%s}" % k in sql for k in SQL_PARAMS):
            sql = sql.format(**SQL_PARAMS)
        con.execute(sql)
        rows = con.execute("SELECT count(*) FROM %s" % name).fetchone()[0]
        print("  %-28s %10s rows" % (name, "{:,}".format(rows)))


def main():
    if not os.path.exists(DB_PATH):
        raise SystemExit("No database at %s -- run python src/ingest.py first." % DB_PATH)
    con = duckdb.connect(DB_PATH)
    print("creating views in %s" % DB_PATH)
    create_views(con)
    con.close()
    print("\ndone")


if __name__ == "__main__":
    main()
