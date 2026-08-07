# PortfolioPulse

Credit portfolio monitoring and risk analytics over the Freddie Mac Single-Family
Loan-Level Dataset.

> **Status: in build.** Phase 1 (ingestion) is in progress. This README is a stub;
> the full version lands in Phase 7.

## The data is not in this repo

Freddie Mac's terms restrict the Single-Family Loan-Level Dataset to internal
analysis and require a licensing agreement for redistribution, so `data/` is
gitignored from the first commit. This is deliberate.

**See [DATA.md](DATA.md) for how to register and download it.** Nothing runs until
you do.

## Stack

Python, Pandas, DuckDB, Streamlit. Every reporting metric is computed in a `.sql`
file, never in Pandas.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
