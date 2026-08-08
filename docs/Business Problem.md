# Business Problem

## What a credit portfolio monitoring function actually does

A lender holding a book of loans needs to answer, every reporting period:

1. **How big is the book, and which way is it moving?** Balance, loan count and
   growth, split by the dimensions that carry risk.
2. **How much of it is going bad, and where?** Default rates by segment, and
   whether deterioration is broad or concentrated.
3. **How much money should be set aside against expected losses?** Provision by
   IFRS 9 stage, and whether the movement is a charge or a release.
4. **Can the numbers be trusted?** Reconciliation, validation, and a register of
   known defects.
5. **Why did the numbers move?** Not just that they moved — attribution to the
   segment responsible, written down.

Portfolio Pulse answers all five on a real loan-level panel.

## Why a panel matters

Most publicly available credit datasets are **snapshots**: one row per loan with
a final outcome. From a snapshot you can build a scorecard, but you cannot build
portfolio monitoring, because the questions above are all about *change over
time*:

- **Roll rates** need a loan's state in consecutive periods.
- **Vintage curves** need each cohort tracked from origination across its life.
- **Provision movement** needs an opening and a closing position.
- **Commentary** needs a prior period to compare against.

This project uses a genuine panel — one row per loan per quarter, 623,732 rows
across 50,000 loans — so none of those had to be faked or dropped.

## Why this particular window

The data spans 2000Q2 to 2015Q1: the housing boom, the crash and the recovery.
That window contains a real stress event, which means the reporting is exercised
against something that actually happened rather than a placid book where every
chart is a flat line. Default rates, staging, provisions and the commentary
generator all have something to say.

## How it is built

Design choices favour the obvious over the clever. Every metric lives in a SQL
file that states the question it answers, assumptions are collected in one
place rather than scattered through the code, and nothing is computed twice in
two languages. The test is whether any number on the dashboard can be traced to
a query and defended out loud.
