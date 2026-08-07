# Getting the Data

This project runs on the **`mortgage` panel dataset** from *Credit Risk
Analytics* (Baesens, Roesch & Scheule, Wiley 2016), companion data to the book
and originally provided by International Financial Research. It is a randomised
selection of loan-level data drawn from US residential mortgage-backed
securities portfolios.

## Download

No registration is required.

```bash
cd data
curl -O http://www.creditriskanalytics.net/uploads/1/9/5/1/19511601/mortgage_csv.rar
bsdtar -xvf mortgage_csv.rar      # bsdtar ships with macOS; unrar/7z also work
rm mortgage_csv.rar
```

You should end up with `data/mortgage.csv`, roughly 68 MB. That is the only file
the pipeline reads.

```bash
head -1 data/mortgage.csv     # header row: id,time,orig_time,...
wc -l data/mortgage.csv       # 622,490 lines (622,489 rows plus header)
```

## Why it is still not committed

The file is freely downloadable, so this is not the hard legal restriction that
applies to the Freddie Mac dataset. But it is third-party data published as
companion material to a copyrighted textbook, and the authors state no
redistribution licence. Keeping `data/` gitignored is the correct default: the
repository stays reproducible from instructions rather than by carrying someone
else's data.

## Shape of the data

622,489 rows, 50,000 loans, **one row per loan per period** — a genuine panel,
which is what makes vintage curves and transition analysis possible.

**The grain is quarterly, not monthly.** A 30-year loan shows
`mat_time - orig_time = 120`, i.e. 120 quarters. The fact table is named
`fact_loan_quarter` for this reason.

| Column group | Columns |
|---|---|
| Keys | `id`, `time`, `orig_time`, `first_time`, `mat_time` |
| Monthly state | `balance_time`, `LTV_time`, `interest_rate_time` |
| Macro | `hpi_time`, `gdp_time`, `uer_time` |
| At origination | `balance_orig_time`, `FICO_orig_time`, `LTV_orig_time`, `Interest_Rate_orig_time`, `hpi_orig_time`, `investor_orig_time`, `REtype_CO/PU/SF_orig_time` |
| Outcome | `default_time`, `payoff_time`, `status_time` (0 active, 1 default, 2 payoff) |

## The periods are deidentified — and the calendar is recoverable

`time` is an integer 1..60 with no stated calendar meaning. The embedded US
unemployment rate and house price index anchor it:

| Period | Dataset UER | Implied quarter | Actual US UER |
|---|---|---|---|
| 1 | 3.8 | 2000Q2 | 3.9 |
| 14 | 6.2 | 2003Q3 | 6.1 |
| 25 | 4.7 (HPI peaks) | 2006Q2 | 4.6 |
| 39 | 10.0 (UER peaks) | 2009Q4 | 9.9 |
| 60 | 5.7 | 2015Q1 | 5.6 |

So **period 1 = 2000Q2** and **period 60 = 2015Q1**.

This is a **derived inference, not a fact stated by the provider**. It is used
only for labelling — every metric is computed on the raw integer period. Set
`CALENDAR_ANCHOR = None` in `src/config.py` to drop the calendar entirely
without changing a single number.

## What this dataset does not have

Recorded here because it changes what the project can report:

- **No delinquency buckets.** There is no 30/60/90-day status, only active /
  default / payoff. Roll rates are therefore status transitions, not bucket
  migration, and there are no cures to observe.
- **No recovery, expense or realised-loss amounts.** Loss severity (loss given
  default) cannot be computed and is deliberately absent rather than guessed.
  Exposure at default and loan-to-value at default are observable and are
  reported instead.
- **No property state, loan purpose, channel or DTI.** Segmentation is credit
  score band, LTV band, property type and occupancy.
