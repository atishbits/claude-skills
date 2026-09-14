# Phase 4 — Schedule CG (Capital Gains)

Runs **before** Other Sources: what lands here must not be repeated there.

## 1. Regime of rates — AY 2026-27, post 23-Jul-2024 law

| Asset | Long-term after | STCG | LTCG |
|-------|-----------------|------|------|
| Listed equity shares / equity MF / business trust (STT paid) | 12 months | **20% u/s 111A** | **12.5% u/s 112A** above the ₹1,25,000 annual exemption |
| Listed bonds / debentures | 12 months | slab | 12.5% without indexation |
| Unlisted shares, foreign shares | 24 months | slab | 12.5% without indexation |
| Immovable property | 24 months | slab | 12.5% without indexation; a resident individual may instead opt for **20% with indexation if acquired before 23-Jul-2024** — compute both and take the lower |
| Debt mutual funds bought on/after 1-Apr-2023 | — | always short-term at slab | no LTCG |
| Gold / unlisted assets / others | 24 months (36 for some) | slab | 12.5% without indexation |

**Sub-period split.** For assets sold in FY 2024-25 the schedule splits at 23-Jul-2024. From
FY 2025-26 onwards the new rates apply to the whole year — but the utility still asks for the
quarterly breakup (for 234C). Fill it.

## 2. Schedule 112A procedure

- The utility accepts either scrip-wise rows or a single consolidated row. **Consolidated row
  convention:** ISIN `INNOTREQUIRD`, name `CONSOLIDATED`.
- Columns: (6) full value of consideration · (7) cost of acquisition without indexation · (8) cost of
  acquisition · (9–11) FMV as on 31-Jan-2018 and the grandfathering computation · (12) expenditure on
  transfer · (13) total deductions · (14) balance = LTCG.
- **Grandfathering (Sec 55(2)(ac)) applies only to shares acquired on or before 31-Jan-2018.** For
  anything acquired later the FMV columns are 0 and AIS's FMV figure is irrelevant — do not let a
  prefilled FMV inflate or deflate the gain.
- If the consolidated row triggers a zero-quantity validation warning, enter the actual share count
  to clear it.
- **AIS frequently reports Cost of Acquisition as 0** for share sales. If so: submit AIS feedback
  ("Information is not fully correct") with the correct cost **before filing**, and keep the
  Consolidated Feedback PDF as the audit trail. Record the feedback date in the conclusions file.

## 3. Foreign / US shares

- A sale of US-listed shares by a resident is **not** 111A/112A — no STT. Long-term if held
  > 24 months → 12.5% without indexation; otherwise slab rates.
- **Cost basis of RSU shares = FMV on the vesting date** — the same value already taxed as a
  perquisite in Form 12BA. Never ₹0, never the grant price.
- **Rule 115 conversion:** SBI TT buying rate on the last day of the month *immediately preceding*
  the month of transfer for the sale consideration, and the corresponding rate for the acquisition
  month for the cost. Use `scripts/fx.py`; ask the user for the rate rather than guessing one.
- Foreign CG also goes into **Schedule FSI**, and into **Schedule TR + Form 67** if foreign tax was
  paid.
- **Sell-to-cover / shares withheld at vest:** in the common Indian treatment, shares withheld by the
  employer to meet its TDS obligation are not a sale by the employee for CG purposes — the perquisite
  is already taxed. But if the broker actually sold shares **in the employee's name**, it is a sale
  and needs CG treatment. Check the vest report; **always ask** rather than assuming.

## 4. Losses

- STCL sets off against STCG **and** LTCG. LTCL sets off **only** against LTCG.
- Unabsorbed capital losses carry forward **8 assessment years** and set off only against capital
  gains.
- **Carry-forward is disallowed if the return is filed after the due date.** Say this to the user
  explicitly whenever there is a loss.
- A loss must appear in **Schedule CFL**, not merely in Schedule CG. Verify it in the preview PDF.
- Even where an LTCG would have fallen within the ₹1.25L exemption, a loss still deserves to be
  carried forward properly.

## 5. Questions to ask

1. Did you sell any listed Indian shares or mutual fund units this FY? Do you have the broker's
   Tax P&L / Capital Gains statement?
2. Any property, gold, unlisted shares, or crypto sold?
   *(VDAs go in **Schedule VDA at 30%**, not normal CG — no deductions, no loss set-off.)*
3. Any US or other foreign shares sold, **including RSU shares**?
4. Were any shares acquired on or before 31-Jan-2018 (grandfathering)?
5. Any brought-forward capital losses from earlier years?
6. Did AIS report cost of acquisition as zero anywhere?

## 6. Output

`ITR2_Schedule_CG_conclusions.md`, in the structure required by `10_output_templates.md`. Break out
111A / 112A / other-LTCG totals separately — Phase 8 feeds them to `tax_calc.py` as distinct inputs.
