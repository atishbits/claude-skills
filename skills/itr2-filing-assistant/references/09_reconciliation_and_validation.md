# Phase 9 — Reconciliation & validation sweep

Nothing here is optional. Run every check, record the result of each in the conclusions file, and
mark any waived check as **WAIVED** with the user's reason.

## 1. The reconciliation ladder

> **Primary document > TIS "Processed by System" > AIS line items > portal prefill**

Prefill is the weakest link. Where prefill disagrees with a primary document, **the primary document
wins**, and the deviation is recorded with its reason.

## 2. Cross-check matrix — run all of these

| # | Check | Fails when |
|---|-------|-----------|
| 1 | Gross salary: Form 16 = AIS (TDS-Annexure II SAL) = 26AS s.192 | Any mismatch |
| 2 | Every TDS/TCS credit claimed exists in 26AS with matching TAN and amount | Claimed > 26AS |
| 3 | Total of Schedule OS 1a ties to the TIS dividend total | ≠ |
| 4 | Total of Schedule OS 1b ties to the sum of per-bank certificates and TIS interest | ≠ |
| 5 | Quarterly dividend breakup (OS §10) sums **exactly** to line 1a | ≠ |
| 6 | Schedule CG sale consideration ties to AIS SFT-17 / the broker statement | ≠ |
| 7 | Co-owned HP: the co-owners' shares sum to 100% and their gross-rent halves sum to the full rent | ≠ |
| 8 | Every foreign holding in Schedule FA that paid income has that income in OS/CG/FSI | Disclosed asset, undisclosed income |
| 9 | Schedule FA A3 rows: initial ≠ peak ≠ closing where they logically must differ; proceeds = 0 unless a sale occurred | Identical values across all fields |
| 10 | The FA period is Jan–Dec of the right calendar year; no next-year acquisitions included | Period mismatch |
| 11 | FTC claimed in TR ≤ foreign tax paid in FSI, **and Form 67 is filed** | Missing Form 67 |
| 12 | The current-year loss appears in Schedule CFL | Present in CG but absent from CFL |
| 13 | Brought-forward losses match the prior-year CFL | ≠ |
| 14 | The regime is consistent across the whole return (standard deduction, Ch VI-A, HP interest) | Mixed signals |
| 15 | Part B-TI head totals equal the sum of each schedule | ≠ |
| 16 | Part B-TTI tax computation matches `tax_calc.py` independently | ≠ |
| 17 | The refund bank account is pre-validated and is in the return | Not validated |
| 18 | Schedule AL present if total income > ₹50L | Missing |
| 19 | Nothing informational (SFT-005/006, LRS TCS) has been reported as income | Present in OS |
| 20 | The return is being filed on or before the due date, if any loss is being carried forward | Late |

## 3. Preview-PDF review pass — do not skip

After the user has filled the utility, ask them to download the **preview / draft PDF** and
re-verify **every schedule against the conclusions files, line by line**. Budget a full pass for it.

Transcription errors are the realistic failure mode at this stage — a value copied from one A3 row
into an adjacent row, a dividend duplicated onto an equity row. These are invisible in the utility
and obvious in the PDF.

## 4. Known portal prefill bugs — check every time

- Deduction u/s 16 showing **₹50,000 under the new regime** (should be ₹75,000).
- The **entire annual dividend dumped into the "Upto 15/6"** quarter bucket.
- **AIS reporting cost of acquisition as ₹0** for share sales.
- **Schedule FA rows prefilled with the correct account identity but zero peak/closing balances.**
- **PO-Box numbers parsed into the ZIP field.**
- **AIS SFT and TDS entries double-counting the same dividend** — TIS resolves this; AIS alone does
  not.

## 5. Output

Add a `Validation sweep` section to
`ITR2_Final_Worksheet_and_Prefiling_Checklist.md` recording each of the 20 checks as
**PASS / FAIL / WAIVED**, with a one-line note on every FAIL and WAIVED.
