# Getting the Data

This project runs on the **Freddie Mac Single-Family Loan-Level Dataset (SFLLD)**.
The data is free but requires registration, and **it is not committed to this
repository**. You must download it yourself before any of the pipeline will run.

## Why the data is not in this repo

Freddie Mac's terms for the SFLLD restrict use to internal analysis and require a
separate licensing agreement for commercial use or redistribution. Committing the
raw files to a public GitHub repository would be redistribution.

`data/` is therefore in `.gitignore` from the first commit. This is a deliberate
choice, not an oversight — see the note in the README. The authoritative terms are
published at
<https://capitalmarkets.freddiemac.com/crt/docs/pdfs/fre_terms_conditions_sflld.pdf>;
read them yourself rather than relying on this summary.

## Registration and download

1. Go to the dataset home page:
   <https://www.freddiemac.com/research/datasets/sf-loanlevel-dataset>
2. Downloads have moved to **Clarity Data Intelligence**. Go to the SFLLD download
   page: <https://claritydownload.fmapps.freddiemac.com/CRT/#/sflld>
3. Register for a free Clarity account and accept the terms and conditions. Approval
   is normally immediate, but budget an evening for this step — first-time
   registration and finding your way around the portal is the slow part.
4. On the SFLLD download page choose the **Sample Dataset** (not the Standard or
   Non-Standard full dataset). The sample is a random selection of 50,000 loans per
   vintage year, which is the right size to work with on a laptop.
5. Download the sample files for the two vintages this project uses:
   - **2007** — the stressed cohort, deteriorates sharply through the financial crisis
   - **2021** — the recent benign cohort, for contrast

## What you should end up with

Each vintage ships as a zip containing two pipe-delimited files with **no header row**:

| File | Contents |
|------|----------|
| `sample_orig_YYYY.txt` | Origination file — one row per loan, characteristics at origination |
| `sample_svcg_YYYY.txt` | Monthly performance file — one row per loan per month |

Unzip them into `data/` so the layout is:

```
data/
  sample_orig_2007.txt
  sample_svcg_2007.txt
  sample_orig_2021.txt
  sample_svcg_2021.txt
```

The loader reads exactly these paths. Nothing else in `data/` is touched.

## The User Guide — download this too

Also download the **Single-Family Loan-Level Dataset General User Guide** (PDF) from
the same page. It defines the column order for both files.

This matters more than it sounds. The files have no header row, so column meaning is
positional. A wrong offset does not throw an error — it silently produces wrong
numbers that look plausible. The layout in `src/layouts.py` is transcribed from that
guide, and the guide is the reference to check it against.

## Sanity check before running the pipeline

```bash
# Should print pipe-delimited rows with no header
head -2 data/sample_orig_2007.txt

# Row counts: origination ~50,000 per vintage; performance is much larger
wc -l data/sample_orig_2007.txt data/sample_svcg_2007.txt
```

## Coverage note

The dataset covers 1999 through September 2025 and includes only fully amortising,
fixed-rate, conventional single-family mortgages. Adjustable-rate, balloon and
government-insured (FHA/VA) loans are excluded, so this is not the whole Freddie Mac
book. See `docs/Known Assumptions.md`.
