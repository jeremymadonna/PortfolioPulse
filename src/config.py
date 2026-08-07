"""Dataset schema, banding and analysis choices for PortfolioPulse.

SOURCE: the `mortgage` panel from Credit Risk Analytics (Baesens, Roesch &
Scheule, Wiley 2016), distributed at creditriskanalytics.net. It is a randomised
selection of loan-level data from US residential mortgage-backed securities
portfolios, provided by International Financial Research.

SHAPE: 622,489 rows, 50,000 loans, one row per loan per period. This is a
genuine panel, which is what makes vintage curves and transition analysis
possible at all.

GRAIN IS QUARTERLY, NOT MONTHLY. A 30-year loan shows mat_time - orig_time =
120, i.e. 120 quarters. Every "period" in this project is therefore a calendar
quarter, and the fact table is named fact_loan_quarter rather than
fact_loan_month so the grain cannot be misread.
"""

# --- Columns we expect in mortgage.csv ---------------------------------------
# The file HAS a header row, unlike the Freddie Mac files, so columns are read
# by name. verify_schema() still checks they are all present and in range,
# because a renamed or missing column should fail loudly, not silently.

EXPECTED_COLUMNS = [
    "id", "time", "orig_time", "first_time", "mat_time",
    "balance_time", "LTV_time", "interest_rate_time",
    "hpi_time", "gdp_time", "uer_time",
    "REtype_CO_orig_time", "REtype_PU_orig_time", "REtype_SF_orig_time",
    "investor_orig_time", "balance_orig_time", "FICO_orig_time",
    "LTV_orig_time", "Interest_Rate_orig_time", "hpi_orig_time",
    "default_time", "payoff_time", "status_time",
]

# --- Recovering the calendar -------------------------------------------------
# The periods are deliberately deidentified: `time` is an integer 1..60 with no
# stated calendar meaning. But the file carries the US unemployment rate and a
# house price index per period, and those anchor it. Unemployment peaks at 10.0
# in period 39 (US: 2009Q4), the house price index peaks in period 25 (US
# housing peaked 2006Q2), and period 1 shows 3.8 (US 2000Q2: 3.9). All four
# checkpoints agree within 0.1pp, so:
#
#     period 1 == 2000Q2,  period 60 == 2015Q1
#
# This is a DERIVED INFERENCE, not a fact stated by the data provider. It is
# used only for labelling. Every metric is computed on the raw integer period,
# so setting CALENDAR_ANCHOR to None below removes the calendar entirely
# without changing a single number.
CALENDAR_ANCHOR = (2000, 2)          # (year, quarter) of period 1
CALENDAR_ANCHOR_EVIDENCE = (
    "uer peaks 10.0 at t=39 (US 2009Q4); hpi peaks at t=25 (US 2006Q2); "
    "t=1 uer 3.8 (US 2000Q2 3.9); t=60 uer 5.7 (US 2015Q1 5.6)"
)

# --- The two cohorts to contrast ---------------------------------------------
# Chosen from the data, not assumed. Lifetime default rate by origination
# cohort rises monotonically from 9.3% at orig_time 14 to 53.2% at orig_time 27,
# which is the underwriting cycle running into the housing peak.
#   orig_time 14 == 2003Q3, 1,427 loans,  9.3% lifetime default  (benign)
#   orig_time 27 == 2006Q4, 3,822 loans, 53.2% lifetime default  (stressed)
BENIGN_VINTAGE = 14
STRESSED_VINTAGE = 27

# Loans originated before the observation window (orig_time < 1) are never seen
# from origination, so their early periods are missing and any loan that had
# already defaulted is absent altogether. Including them would bias vintage
# curves downward. They are 1,129 loans, 2.3% of the file.
MIN_OBSERVABLE_ORIG_TIME = 1

# --- Banding ------------------------------------------------------------------
# Credit score bands are as specified in the project brief.
FICO_BANDS = [(0, 619, "1. <620"), (620, 659, "2. 620-659"), (660, 699, "3. 660-699"),
              (700, 739, "4. 700-739"), (740, 779, "5. 740-779"), (780, 900, "6. 780+")]

# LTV bands: conventional mortgage cuts. 80 is the mortgage-insurance threshold;
# above 100 the borrower owes more than the property is worth, which this
# dataset does contain (original LTV runs to 218).
LTV_BANDS = [(0, 60, "1. <=60"), (61, 70, "2. 61-70"), (71, 80, "3. 71-80"),
             (81, 90, "4. 81-90"), (91, 100, "5. 91-100"), (101, 1000, "6. >100")]

# status_time is the loan's state in that period.
STATUS_MEANING = {0: "1. Active", 1: "2. Default", 2: "3. Payoff"}
