# PortfolioPulse

Credit portfolio monitoring and risk analytics over the Freddie Mac
Single-Family Loan-Level Dataset.

> **Status: in build.** Phase 1 (ingestion and star schema) is complete.
> This README is a stub; the full version lands in Phase 7.

## Data source and attribution

This project is built on the **Freddie Mac Single-Family Loan-Level Dataset
(SFLLD)**, published by the Federal Home Loan Mortgage Corporation (Freddie Mac).
All loan performance data, field definitions and code values originate with
Freddie Mac. This project claims no ownership of the data and redistributes
none of it.

| Source | Used for |
|---|---|
| [Single-Family Loan-Level Dataset](https://www.freddiemac.com/research/datasets/sf-loanlevel-dataset) | The dataset itself: origination and monthly performance files |
| [Clarity Data Intelligence download portal](https://claritydownload.fmapps.freddiemac.com/CRT/#/sflld) | Where the sample files are obtained, after free registration |
| Single-Family Loan-Level Dataset **General User Guide** | Column order for both pipe-delimited files, zero balance code meanings, delinquency status values, and the actual-loss formula. Transcribed into `src/layouts.py` |
| [SFLLD Terms and Conditions](https://capitalmarkets.freddiemac.com/crt/docs/pdfs/fre_terms_conditions_sflld.pdf) | The licensing constraint that keeps `data/` out of this repository |

The column layout in `src/layouts.py` is transcribed from the **August 2018**
edition of the General User Guide (27 origination fields, 25 monthly performance
fields). Later editions append fields to the end of each file, so the loader
reads by position and ignores trailing extras. `verify_layout()` in
`src/ingest.py` re-proves the mapping against the file contents on every run, so
a layout change fails loudly rather than silently producing wrong numbers.

Freddie Mac is not affiliated with this project and does not endorse it. Any
errors in derivation, banding or interpretation here are mine, not theirs.

## The data is not in this repo

Freddie Mac's terms restrict the dataset to internal analysis and require a
licensing agreement for commercial use or redistribution, so `data/` is
gitignored from the first commit. This is a deliberate choice, not an oversight.

**See [DATA.md](DATA.md) for how to register and download it.** Nothing runs
until you do — the loader exits with instructions if the files are absent.

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
