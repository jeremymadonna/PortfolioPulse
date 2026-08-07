# PortfolioPulse

Credit portfolio monitoring and risk analytics over the Freddie Mac
Single-Family Loan-Level Dataset.

> **Status: in build.** Phase 1 (ingestion and star schema) is complete.
> This README is a stub; the full version lands in Phase 7.

## Data source and attribution

This project is built on the **`mortgage` panel dataset**, companion data to
*Credit Risk Analytics: Measurement Techniques, Applications, and Examples in
SAS* by Bart Baesens, Daniel Roesch and Harald Scheule (John Wiley & Sons,
2016), originally provided by **International Financial Research**. It is a
randomised selection of loan-level data from US residential mortgage-backed
securities portfolios: 622,489 rows, 50,000 loans, one row per loan per quarter.

All data originates with those authors and International Financial Research.
This project claims no ownership of it and redistributes none of it.

| Source | Used for |
|---|---|
| [creditriskanalytics.net](http://www.creditriskanalytics.net/datasets-downloads.html) | The dataset itself (`mortgage_csv.rar`) |
| *Credit Risk Analytics* (Baesens, Roesch & Scheule, Wiley 2016) | The book this data accompanies; source of the column definitions |
| US Bureau of Labor Statistics unemployment series | Independent check used to recover the calendar from the deidentified periods |

The authors are not affiliated with this project and do not endorse it. Any
errors in derivation, banding or interpretation here are mine, not theirs.

### A note on the periods

The dataset's `time` column is deliberately deidentified. The embedded
unemployment and house price series let it be anchored to calendar quarters
(period 1 = 2000Q2, period 60 = 2015Q1), verified against actual US
unemployment at five checkpoints to within 0.1pp. **This is a derived
inference, not a stated fact**, it is used only for labelling, and it can be
switched off in `src/config.py` without changing any metric. See
[DATA.md](DATA.md).

## The data is not in this repo

`data/` is gitignored. The file is freely downloadable, so this is not a hard
legal restriction, but it is third-party companion data to a copyrighted
textbook with no stated redistribution licence. The repository stays
reproducible from instructions rather than by carrying someone else's data.

**See [DATA.md](DATA.md) for the one-line download.** Nothing runs until you do
— the loader exits with instructions if the file is absent.

## Stack

Python, Pandas, DuckDB, Streamlit. Every reporting metric is computed in a
`.sql` file, never in Pandas.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/ingest.py
```

## Licence

Project code: MIT. The Freddie Mac data it reads is governed by Freddie Mac's
own terms, linked above, and is not covered by this licence.
