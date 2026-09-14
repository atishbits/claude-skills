# Phase 6b — US equity playbook (RSU/ESPP and self-bought US stock)

US equity is where most ITR-2 filings go wrong. There are **two separate tracks** and a user may
have both — two different accounts, needing separate Schedule FA rows.

Read `05_foreign_assets_and_income.md` first; the calendar-year rule and the FX rules there apply
throughout.

---

## Track A — employer RSU / ESPP / stock options

Typical plan administrators: Fidelity (Stock Plan Services / National Financial Services), Charles
Schwab (Equity Award Center), E*Trade (Morgan Stanley at Work), Morgan Stanley Shareworks,
Computershare.

| Event | Tax treatment | Where it appears |
|-------|---------------|------------------|
| **Grant** | Nothing | — |
| **Vest** | Perquisite u/s 17(2) = FMV on vest date × shares vested, converted at the TT buying rate. Employer withholds TDS, usually by withholding shares. | Form 16 Part B line 1b + Form 12BA item 17 — **already inside gross salary; do not report again** |
| **Holding** | No income, but the holding must be disclosed | Schedule FA **A3** (and the account in **A2**) |
| **Dividend received** | Taxable in India at slab rates. US withholds 25% by default, **15% with a valid W-8BEN** on file (India–US DTAA Article 10) | Schedule OS 1a + FSI + TR + Form 67 |
| **Sale** | Capital gain = sale proceeds − FMV on vest date. Held > 24 months → LTCG 12.5% without indexation; else slab | Schedule CG + FSI |
| **Sell-to-cover at vest** | Usually shares *withheld by the employer*, not a sale by the employee — verify against the vest report | **Ask before assuming** |

**Documents to request:** the year-end (**calendar**) account statement showing closing market value
and cash balance; the full vest/grant history with per-vest FMV; Form 1042-S; any trade
confirmations.

**Common errors to check:**

- Reporting the RSU perquisite a **second** time under Other Sources — it is already in salary.
- Using ₹0 or the grant price as the cost basis on sale.
- Leaving Schedule FA peak/closing at ₹0 for an account that clearly holds shares. **A prefilled FA
  row with zero balances is wrong, not empty.** Replace the zeros; keep the row.
- Putting the account's cash / money-market income on the equity **A3** row instead of the **A2**
  account row.
- Copying the same rupee figure into initial / peak / closing / credited / proceeds.
  *Peak = closing = proceeds is internally impossible — you cannot both sell and still hold.* Use
  precise, distinct values.
- ZIP misparses in prefill (a PO Box number appearing as the ZIP). Cosmetic, but note it.

---

## Track B — self-bought US stocks via an Indian app

Typical routes: INDmoney (executing through Alpaca Securities LLC), Vested (DriveWealth), Groww US,
apps routing to Interactive Brokers.

- **The broker of record is the US entity** — e.g. Alpaca Securities LLC, San Mateo CA. That is the
  name, address and account number that go into Schedule FA **A2**, *not* the Indian app's name.
- These apps generate both a "Schedule FA report" and a "Tax P&L". **Verify the period on both
  before use.** Ask for the **calendar-year (Jan–Dec)** FA report and the **financial-year
  (Apr–Mar)** income/CG report — they are different reports.
- Each US stock held becomes an **A3 row** (aggregate lots per company).
- Non-US companies listed in the US as **ADRs** are conventionally reported with country = United
  States, because the instrument is US-listed. Note the convention in the conclusions file.
- **Country code for the United States in ITR schedules is 002.**
- Money remitted abroad under **LRS** attracts **TCS u/s 206CQ**, collected by the remitting bank. It
  is **not income** — it is a tax credit, claimed in the TCS schedule. Reconcile the amount against
  26AS.
- **Fractional shares are common.** Carry the decimals into the initial / peak / closing values.
- Dividends are small but real: aggregate per company, and note the US tax withheld per company for
  FTC.

---

## Entity addresses

Schedule FA **A3 requires the address and ZIP of the entity whose shares are held** — the issuer, not
the broker. Ask the user to confirm each issuer's registered address, or look it up, and **record it
once in the conclusions file so it is reusable next year.**

## Questions to ask

1. Which plan administrator holds your employer shares, and which app/broker holds any self-bought
   US stock? *(Two different accounts — both need separate FA rows.)*
2. Do you have the **31 December** statement from each?
3. Did you sell anything? Was any "sell to cover" an actual sale in your name?
4. Is a W-8BEN on file? *(It sets the US withholding rate — 15% vs 25%.)*
5. How much did you remit under LRS this year, and what TCS was collected?
