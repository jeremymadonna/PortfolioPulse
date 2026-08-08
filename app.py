"""ArrearsIQ dashboard.

Run:  streamlit run app.py

Four pages via the sidebar. Every number shown here comes from a SQL view --
this file queries and lays out, it does not calculate. If a figure looks wrong,
the fix belongs in sql/, not here.
"""

import os

import duckdb
import pandas as pd
import streamlit as st

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "data", "portfoliopulse.duckdb")

st.set_page_config(page_title="ArrearsIQ", page_icon="•", layout="wide")


@st.cache_resource
def connect():
    return duckdb.connect(DB_PATH, read_only=True)


@st.cache_data
def q(sql, params=None):
    return connect().execute(sql, params or []).df()


def money(x):
    if x is None or pd.isna(x):
        return "n/a"
    for unit, div in (("bn", 1e9), ("m", 1e6), ("k", 1e3)):
        if abs(x) >= div:
            return "$%.2f%s" % (x / div, unit)
    return "$%.0f" % x


if not os.path.exists(DB_PATH):
    st.error("No database found. Run `python src/ingest.py` then `python src/views.py`.")
    st.stop()

# --- sidebar: slicers --------------------------------------------------------
st.sidebar.title("ArrearsIQ")
st.sidebar.caption("Credit portfolio monitoring")
page = st.sidebar.radio("Page", ["Executive Summary", "Portfolio and Delinquency",
                                 "Vintage and Loss", "Data Quality"])
st.sidebar.markdown("---")

periods = q("SELECT period, reporting_quarter FROM dim_date ORDER BY period")
labels = dict(zip(periods["period"], periods["reporting_quarter"]))
sel_period = st.sidebar.select_slider(
    "Reporting quarter", options=list(periods["period"]),
    value=int(periods["period"].max()), format_func=lambda p: labels[p])

vintages = q("SELECT DISTINCT origination_vintage FROM dim_loan ORDER BY 1")["origination_vintage"].tolist()
sel_vintages = st.sidebar.multiselect("Origination vintage", vintages, default=[])

bands = q("SELECT DISTINCT credit_score_band FROM dim_loan ORDER BY 1")["credit_score_band"].tolist()
sel_bands = st.sidebar.multiselect("Credit score band", bands, default=[])

st.sidebar.markdown("---")
st.sidebar.caption("Provision figures are ILLUSTRATIVE, not an accounting "
                   "allowance. This dataset has no delinquency buckets and no "
                   "realised loss amounts — see DATA.md.")

# =============================================================================
if page == "Executive Summary":
    st.title("Executive Summary")
    st.caption("Reporting quarter %s" % labels[sel_period])

    cur = q("SELECT * FROM vw_portfolio_summary WHERE period = ?", [sel_period]).iloc[0]
    prov = q("SELECT * FROM vw_provision_movement WHERE period = ?", [sel_period])

    c = st.columns(5)
    c[0].metric("Active balance", money(cur["active_balance"]),
                None if pd.isna(cur["balance_growth_pct"]) else "%.1f%%" % cur["balance_growth_pct"])
    c[1].metric("Active loans", "{:,}".format(int(cur["active_loans"])))
    c[2].metric("Quarterly default rate",
                "%.2f%%" % (cur["quarterly_default_rate_pct"] or 0))
    c[3].metric("Defaults this quarter", "{:,}".format(int(cur["defaults"])))
    if not prov.empty:
        c[4].metric("Coverage ratio (illustrative)",
                    "%.2f%%" % prov.iloc[0]["coverage_ratio_pct"])

    st.markdown("### Balance and default rate over time")
    ts = q("""SELECT reporting_quarter, active_balance, quarterly_default_rate_pct,
                     unemployment_rate FROM vw_portfolio_summary ORDER BY period""")
    a, b = st.columns(2)
    a.line_chart(ts.set_index("reporting_quarter")[["active_balance"]])
    b.line_chart(ts.set_index("reporting_quarter")
                 [["quarterly_default_rate_pct", "unemployment_rate"]])

    st.markdown("### Commentary")
    path = os.path.join(os.path.dirname(DB_PATH), "..", "output",
                        "commentary_%s.txt" % labels[sel_period])
    if os.path.exists(path):
        st.code(open(path).read(), language=None)
    else:
        st.info("No commentary generated for %s. Run "
                "`python src/commentary.py %d`." % (labels[sel_period], sel_period))

# =============================================================================
elif page == "Portfolio and Delinquency":
    st.title("Portfolio and Delinquency")
    st.caption("Reporting quarter %s" % labels[sel_period])
    st.warning("This dataset has no delinquency buckets — a loan is only active, "
               "defaulted or paid off. No 30+/60+/90+ arrears rate can be shown.")

    st.markdown("### Mix by segment")
    seg = q("""SELECT segment_type, segment_value, active_balance, active_loans,
                      pct_of_portfolio_balance, quarterly_default_rate_pct
               FROM vw_segment_performance WHERE period = ? ORDER BY segment_type, segment_value""",
            [sel_period])
    if sel_bands:
        seg = seg[(seg["segment_type"] != "Credit score band")
                  | (seg["segment_value"].isin(sel_bands))]
    for stype in seg["segment_type"].unique():
        sub = seg[seg["segment_type"] == stype]
        st.markdown("**%s**" % stype)
        a, b = st.columns([1, 1])
        a.bar_chart(sub.set_index("segment_value")[["active_balance"]])
        b.dataframe(sub[["segment_value", "active_loans", "active_balance",
                         "pct_of_portfolio_balance", "quarterly_default_rate_pct"]],
                    hide_index=True, use_container_width=True)

    st.markdown("### Status distribution over time")
    dist = q("""SELECT reporting_quarter, status_bucket, balance FROM vw_delinquency
                WHERE segment_type = 'Portfolio' ORDER BY period""")
    st.line_chart(dist.pivot(index="reporting_quarter", columns="status_bucket",
                             values="balance"))

    st.markdown("### Roll rates — status transition matrix")
    st.caption("Default and payoff are terminal in this dataset, so there are no "
               "cures. Forward-filled rows are excluded from both sides.")
    roll = q("""SELECT from_status, to_status, loans_moved, balance_moved,
                       roll_rate_pct_by_count FROM vw_roll_rates WHERE from_period = ?""",
             [sel_period])
    if roll.empty:
        st.info("No transitions out of %s." % labels[sel_period])
    else:
        st.dataframe(roll.pivot(index="from_status", columns="to_status",
                                values="roll_rate_pct_by_count"),
                     use_container_width=True)

# =============================================================================
elif page == "Vintage and Loss":
    st.title("Vintage and Loss")

    st.markdown("### Cumulative default rate by cohort, indexed on quarters on book")
    st.caption("Cohorts are only comparable where both are fully seasoned — use "
               "the coverage filter below.")
    min_cov = st.slider("Minimum % of cohort still observed", 0, 100, 0, 5)
    show = sel_vintages or ["2003Q3", "2006Q4"]
    vint = q("""SELECT origination_vintage, quarters_on_book,
                       cumulative_default_rate_by_balance_pct, pct_cohort_still_observed
                FROM vw_vintage_performance
                WHERE origination_vintage IN ({}) AND pct_cohort_still_observed >= ?
                ORDER BY quarters_on_book""".format(",".join("?" * len(show))),
             show + [min_cov])
    if vint.empty:
        st.info("No cohorts match. Loosen the coverage filter or pick a vintage.")
    else:
        st.line_chart(vint.pivot(index="quarters_on_book",
                                 columns="origination_vintage",
                                 values="cumulative_default_rate_by_balance_pct"))

    st.markdown("### Exposure and collateral position at default")
    st.info("This dataset records no recoveries, expenses or realised losses, so "
            "loss severity cannot be computed. Exposure at default and LTV at "
            "default are shown instead — LTV above 100 means the borrower owed "
            "more than the property was worth.")
    loss = q("""SELECT segment_type, segment_value, defaults, total_exposure_at_default,
                       avg_ltv_at_default, pct_underwater_at_default,
                       avg_quarters_on_book_at_default
                FROM vw_loss_recovery ORDER BY segment_type, segment_value""")
    st.dataframe(loss, hide_index=True, use_container_width=True)

    st.markdown("### Provision movement (illustrative)")
    mv = q("""SELECT reporting_quarter, opening_provision, increase, decrease,
                     closing_provision, coverage_ratio_pct FROM vw_provision_movement
              ORDER BY period""")
    a, b = st.columns([2, 1])
    a.line_chart(mv.set_index("reporting_quarter")[["closing_provision"]])
    b.line_chart(mv.set_index("reporting_quarter")[["coverage_ratio_pct"]])
    st.dataframe(mv, hide_index=True, use_container_width=True)

# =============================================================================
elif page == "Data Quality":
    st.title("Data Quality")
    st.caption("Findings are reported, never silently cleaned.")

    latest = q("""SELECT rule_name, severity, status, affected_rows FROM dq_results
                  WHERE phase = '4-quality'
                    AND run_timestamp = (SELECT max(run_timestamp) FROM dq_results
                                         WHERE phase = '4-quality')
                  ORDER BY status, severity""")
    if latest.empty:
        st.info("No quality run recorded. Run `python src/quality.py`.")
    else:
        weight = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        total = latest["severity"].map(weight).sum()
        passed = latest[latest["status"] == "PASS"]["severity"].map(weight).sum()
        c = st.columns(3)
        c[0].metric("Data Quality Score", "%.1f / 100" % (100.0 * passed / total))
        c[1].metric("Rules passed", "%d of %d" % ((latest["status"] == "PASS").sum(), len(latest)))
        c[2].metric("Rows affected", "{:,}".format(int(latest["affected_rows"].sum())))
        st.dataframe(latest, hide_index=True, use_container_width=True)

    st.markdown("### Issue register — all runs")
    st.dataframe(q("""SELECT run_timestamp, phase, rule_name, severity, status,
                             affected_rows, detail FROM dq_results
                      ORDER BY run_timestamp DESC, rule_name"""),
                 hide_index=True, use_container_width=True)

    st.markdown("### Reconciliation")
    rec = q("""SELECT s.segment_type,
                      max(abs(s.seg_total - p.active_balance)) AS max_abs_difference
               FROM (SELECT segment_type, period, sum(active_balance) AS seg_total
                     FROM vw_segment_performance GROUP BY 1,2) s
               JOIN vw_portfolio_summary p USING (period) GROUP BY 1 ORDER BY 1""")
    st.caption("Every segmentation must add back to the portfolio total.")
    st.dataframe(rec, hide_index=True, use_container_width=True)
