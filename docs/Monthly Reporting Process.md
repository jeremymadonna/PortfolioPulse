# Reporting Process

The dataset is **quarterly**, so this is a quarterly cycle. The brief called it
monthly; the grain of the source decides, not the plan.

## The run

```bash
source .venv/bin/activate

python src/ingest.py      # 1. rebuild the star schema from mortgage.csv
python src/views.py       # 2. (re)create the eight reporting views
python src/quality.py     # 3. run the ten data quality rules
python src/commentary.py  # 4. write commentary for the latest quarter
python export.py          # 5. refresh the Power BI CSVs
streamlit run app.py      # 6. serve the dashboard
```

Each step is independent and re-runnable. `src/views.py` uses
`CREATE OR REPLACE`, so re-running never leaves a stale view behind.

## Order matters, and why

1. **Ingest** rebuilds the tables and seeds `dq_results` with anything found and
   corrected in the source.
2. **Views** must follow ingest — they read the tables it builds.
3. **Quality** must follow views — rule 9 reconciles `vw_segment_performance`
   against `vw_portfolio_summary`.
4. **Commentary** must follow quality — it reports the current failing rules.
5. **Export** and **dashboard** are consumers and come last.

## Reading the output

Work through it in this order, because a number is only worth interpreting once
you know it reconciles.

1. **Data quality first.** `python src/quality.py`. If a HIGH rule has started
   failing, stop and understand why before quoting any figure.
2. **Reconciliation.** Segment balances must tie to the portfolio total, and
   provision movement must reconcile to zero error. Both are enforced as rules.
3. **The commentary.** `output/commentary_<quarter>.txt`. It names what moved
   and which segment drove it.
4. **The dashboard** for the shape of it.

## Adding a metric

1. Write or edit the `.sql` file in `sql/`. Open it with the business question.
2. If it needs a new view, add the name to `VIEWS` in `src/views.py`.
3. If it needs a tunable value, put it in `src/config.py` and reference it as a
   `{placeholder}` — never hard-code an assumption in SQL.
4. Re-run `src/views.py` and `src/quality.py`.

Never add a calculation to `app.py`. The dashboard queries and lays out; it does
not compute. A metric that exists only in the dashboard cannot be reconciled,
exported or audited.

## Re-running against updated data

`dq_results` appends rather than overwrites, so the quality register builds a
history across runs and a rule that starts failing is visible as a change rather
than just a state.
