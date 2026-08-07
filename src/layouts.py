"""Column layouts for the Freddie Mac Single-Family Loan-Level Dataset.

The source files are pipe-delimited with NO header row, so a column only means
what its POSITION says it means. Getting an offset wrong does not raise an
error -- it silently produces wrong numbers. That is why the layout lives here,
in one declarative place, instead of being scattered through the loader.

SOURCE: Single-Family Loan-Level Dataset General User Guide, August 2018,
sections "Origination Data File" (27 fields) and "Monthly Performance Data
File" (25 fields).

VERSION TOLERANCE: later editions of the User Guide APPEND new fields to the
end of each file (Program Indicator, HARP Indicator, ELTV, Interest Bearing
UPB, and so on). Every field this project needs falls inside the positions
listed below, so the loader reads these by position and ignores any extra
trailing columns. verify_layout() in ingest.py then proves the mapping is
right from the file contents rather than trusting this table blindly.
"""

# Position -> column name. Position is 1-based to match the User Guide tables.
# Names are snake_case versions of the guide's formal names.
ORIGINATION_FIELDS = [
    "credit_score",                    # 1  borrower creditworthiness at origination, 301-850, 9999 = missing
    "first_payment_date",              # 2  YYYYMM, the month months-on-book counts from
    "first_time_homebuyer_flag",       # 3
    "maturity_date",                   # 4  YYYYMM
    "msa",                             # 5  metropolitan statistical area code
    "mi_percent",                      # 6  mortgage insurance coverage percentage
    "number_of_units",                 # 7
    "occupancy_status",                # 8  P = primary, S = second home, I = investment
    "original_cltv",                   # 9  combined loan-to-value, includes subordinate liens
    "original_dti",                    # 10 debt-to-income: monthly debt payments / monthly gross income
    "original_upb",                    # 11 unpaid principal balance: the amount owed at origination
    "original_ltv",                    # 12 loan-to-value: loan amount / property value, the collateral cushion
    "original_interest_rate",          # 13
    "channel",                         # 14 R = retail, B = broker, C = correspondent, T = TPO not specified
    "ppm_flag",                        # 15 prepayment penalty mortgage
    "product_type",                    # 16 always FRM in this dataset (renamed Amortization Type in later guides)
    "property_state",                  # 17 two-letter US state code
    "property_type",                   # 18 SF, CO, PU, MH, CP
    "postal_code",                     # 19
    "loan_sequence_number",            # 20 the loan's unique id, format F1YYQnXXXXXX
    "loan_purpose",                    # 21 P = purchase, C = cash-out refi, N = no cash-out refi
    "original_loan_term",              # 22 months
    "number_of_borrowers",             # 23
    "seller_name",                     # 24
    "servicer_name",                   # 25
    "super_conforming_flag",           # 26
    "pre_harp_loan_sequence_number",   # 27
]

PERFORMANCE_FIELDS = [
    "loan_sequence_number",            # 1  joins to the origination file
    "monthly_reporting_period",        # 2  YYYYMM, the as-of month for this row
    "current_actual_upb",              # 3  outstanding balance this month
    "current_loan_delinquency_status", # 4  MONTHS delinquent (MBA method), not days. 0 = current, R = REO
    "loan_age",                        # 5  months since note origination
    "remaining_months_to_legal_maturity",  # 6
    "repurchase_flag",                 # 7  loan repurchased / made whole; actual loss is forced to zero when Y
    "modification_flag",               # 8  Y = loan terms were modified
    "zero_balance_code",               # 9  why the balance went to zero. 01 prepaid, 03 short sale/3rd party/charge off, 09 REO disposition
    "zero_balance_effective_date",     # 10 YYYYMM the zero balance event happened
    "current_interest_rate",           # 11
    "current_deferred_upb",            # 12 non-interest-bearing balance on modified loans
    "ddlpi",                           # 13 due date of last paid installment, YYYYMM
    "mi_recoveries",                   # 14 recovery: cash recovered after default, here from the mortgage insurer
    "net_sales_proceeds",              # 15 proceeds from selling the property; C = covered, U = unknown
    "non_mi_recoveries",               # 16 recoveries from any other source
    "expenses",                        # 17 costs of acquiring/maintaining/disposing the property
    "legal_costs",                     # 18
    "maintenance_and_preservation_costs",  # 19
    "taxes_and_insurance",             # 20
    "miscellaneous_expenses",          # 21
    "actual_loss_calculation",         # 22 the realised loss, net of recoveries and expenses
    "modification_cost",               # 23
    "step_modification_flag",          # 24
    "deferred_payment_modification",   # 25
]

# --- Code meanings, from the User Guide "Zero Balance Codes" section ----------

# A credit event is a default that ended in a loss: the loan did not simply pay
# off, it went through a distressed disposition. These are the codes that count.
CREDIT_EVENT_ZERO_BALANCE_CODES = ("03", "09")

# 01 = voluntary payoff, a good outcome; the loan leaves the book without loss.
PREPAID_ZERO_BALANCE_CODES = ("01",)

ZERO_BALANCE_CODE_MEANING = {
    "01": "Prepaid or Matured",
    "03": "Short Sale, Third Party Sale or Charge Off",
    "06": "Repurchase prior to Property Disposition",
    "09": "REO Disposition",
    "15": "Note Sale / Reperforming Sale",
}

# Delinquency status is reported in WHOLE MONTHS past due under the Mortgage
# Bankers Association method, which is cleaner than a days-past-due field.
# 0 = current, 1 = one payment missed (30-59 days), and so on. R = real estate
# owned, meaning the lender has taken the property.
VALID_DELINQUENCY_STATUS = set(
    [str(n) for n in range(0, 100)] + ["%02d" % n for n in range(0, 100)] + ["R", "RA", "XX", ""]
)

# --- Banding ------------------------------------------------------------------
# Credit score bands are specified in the project brief.
# LTV and DTI bands are NOT specified in the brief; these are conventional
# mortgage cuts (80% is the MI threshold, 43% is the qualified-mortgage limit).
# Change them here if you want different breaks -- nothing else hard-codes them.

CREDIT_SCORE_BANDS = [(0, 619, "1. <620"), (620, 659, "2. 620-659"), (660, 699, "3. 660-699"),
                      (700, 739, "4. 700-739"), (740, 779, "5. 740-779"), (780, 850, "6. 780+")]

LTV_BANDS = [(0, 60, "1. <=60"), (61, 70, "2. 61-70"), (71, 80, "3. 71-80"),
             (81, 90, "4. 81-90"), (91, 95, "5. 91-95"), (96, 200, "6. >95")]

DTI_BANDS = [(0, 20, "1. <=20"), (21, 30, "2. 21-30"), (31, 36, "3. 31-36"),
             (37, 43, "4. 37-43"), (44, 50, "5. 44-50"), (51, 100, "6. >50")]

# Vintages to load, and how much of each to keep.
VINTAGES = (2007, 2021)
LOANS_PER_VINTAGE = 20000
MAX_MONTHS_ON_BOOK = 48
