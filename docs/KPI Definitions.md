# KPI Definitions

Every metric below is computed in a `.sql` file under `sql/`. Nothing is
calculated in Pandas or in the dashboard.

## Balance and volume

| Metric | Definition | Source |
|---|---|---|
| **Active balance** | Sum of `current_balance` for loans with status Active. Excludes defaulted and paid-off loans, which are exits. | `vw_portfolio_summary` |
| **Active loans** | Count of loans with status Active in the quarter. | `vw_portfolio_summary` |
| **Average balance** | Active balance / active loans. | `vw_portfolio_summary` |
| **Balance growth %** | `(balance / prior quarter balance) - 1`, via `LAG`. | `vw_portfolio_summary` |
| **% of portfolio balance** | Segment balance / total balance in the same quarter. Shows mix shift. | `vw_segment_performance` |

## Credit performance

| Metric | Definition | Source |
|---|---|---|
| **Quarterly default rate** | Loans defaulting this quarter / loans active at the *end of the prior quarter*. A flow rate, not a stock. | `vw_portfolio_summary` |
| **Lifetime default rate** | Share of a cohort that ever defaulted. | `vw_vintage_performance` |
| **Cumulative default rate (by balance)** | Running sum of originally-lent balance that has defaulted by a given age, over the cohort's total original balance. **The headline vintage curve.** | `vw_vintage_performance` |
| **Roll rate** | Of loans in state X at quarter *t*, the share in state Y at *t+1*. Computed on reported rows only. | `vw_roll_rates` |
| **Exposure at default** | Balance still outstanding when the loan defaulted. | `vw_loss_recovery` |
| **LTV at default** | Current loan-to-value at the moment of default. Above 100 = borrower owed more than the property was worth. | `vw_loss_recovery` |
| **% underwater at default** | Share of defaults where LTV at default exceeded 100. | `vw_loss_recovery` |

## Provisioning — all illustrative

| Metric | Definition | Source |
|---|---|---|
| **IFRS 9 stage** | Stage 3 = defaulted. Stage 2 = current LTV > 100 (negative equity). Stage 1 = everything else. | `vw_provision` |
| **Probability of default (PD)** | **Observed** from this panel, per credit score band. 4-quarter horizon for Stage 1, lifetime for Stages 2 and 3. | `vw_provision` |
| **Loss given default (LGD)** | **Assumed constant** in `src/config.py`. Cannot be observed — this source records no recoveries or realised losses. | `src/config.py` |
| **Provision (ECL)** | Exposure x PD x LGD. | `vw_provision` |
| **Coverage ratio** | Provision / exposure. | `vw_provision`, `vw_provision_movement` |
| **Provision movement** | Opening + increase − decrease = closing. Reconciliation carried as a column. | `vw_provision_movement` |

## Data quality

| Metric | Definition | Source |
|---|---|---|
| **Data Quality Score** | Share of total severity weight that passed. HIGH=3, MEDIUM=2, LOW=1. | `src/quality.py` |

## Metrics deliberately NOT reported

Not omissions — this source cannot produce them, and a stand-in would be worse
than a gap:

- **30+ / 60+ / 90+ arrears rates.** No days-past-due or delinquency field.
- **Loss severity (LGD as an observed figure), recoveries, net loss.** No
  recovery, expense or realised-loss amounts.
- **Cure rate.** Default and payoff are terminal, so no loan returns to
  performing.
