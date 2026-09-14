# Phase 6 — Foreign assets & income (Schedule FA, FSI, TR, Form 67)

Read this first, then `06_us_equity_rsu_playbook.md` for the US-equity specifics.

This phase runs **before** set-off and tax computation, because FSI/TR relief changes the liability.

## 1. Who must file Schedule FA

Every **Resident and Ordinarily Resident** who, at any time during the reporting period, held a
foreign asset, was the beneficial owner of one, or had signing authority over a foreign account —
**regardless of income, and regardless of whether the asset generated any income at all.**

RNOR and Non-Residents do not file Schedule FA.

## 2. The reporting period — the single most common error

**Schedule FA is reported on a calendar year basis, not the Indian financial year.**

For AY 2026-27, Schedule FA covers **1 January 2025 to 31 December 2025**: peak value *during*
CY 2025, closing value *as on* 31 December 2025.

Consequences to check every single time:

- Assets acquired in 2026 are **not** reportable in AY 2026-27 — they belong to AY 2027-28.
- Broker "tax reports" are often produced on the financial year, or on some other shifted window. A
  report headed "as on 31 Dec 2026", or containing 2026-dated acquisitions, **cannot** be used to
  fill CY 2025 peak/closing values. Request the correct-period report and say so plainly.
- Meanwhile, **foreign income** (dividends, interest, capital gains) for Schedules OS / CG / FSI is on
  the **Indian financial year** (1 Apr – 31 Mar). The two periods differ. Never mix them.

## 3. Schedule FA tables

| Table | Covers | Key fields |
|-------|--------|-----------|
| **A1** | Foreign depository (bank) accounts | Country & code, institution name & address, ZIP, account number, status (owner / beneficial owner / beneficiary), opening date, **peak balance during the period**, closing balance, gross interest paid/credited |
| **A2** | Foreign custodial accounts (brokerage) | Same fields; "gross amount paid/credited" = interest / dividend / other credited **to the account** (the cash side) |
| **A3** | Foreign equity & debt interest | Entity name & address, ZIP, nature of entity, date of acquiring the interest, initial value of investment, peak value during the period, closing value, gross amount paid/credited (dividends), total gross proceeds on sale/redemption |
| **A4** | Foreign cash-value insurance / annuity contracts | |
| **B** | Immovable property outside India | |
| **C** | Other capital assets outside India | Includes foreign crypto holdings in practice |
| **D** | Accounts where you have signing authority | |
| **E** | Trusts outside India where you are trustee / beneficiary / settlor | |
| **F** | Any other income derived from a source outside India not already reported | |

## 4. A2 vs A3 — how not to double-count

- Many brokers report the cash/settlement balance in **A2** and the securities separately in **A3**.
  A2 being far smaller than the A3 total is therefore **normal and correct** — say so in the
  conclusions file so it does not later look like an error.
- **A dividend is reported once.** If money-market / cash income sits on the A2 account line, it must
  not be repeated on an A3 equity row for a company that pays no dividend. Check each A3 row's
  "gross amount paid/credited" against the actual dividend history of *that specific security*.
- **Aggregate multiple lots of the same security into one A3 row per company**, using the earliest
  acquisition date, the summed initial value, the summed peak and the summed closing.

## 5. Currency conversion

- **Schedule FA values:** convert at the **SBI TT buying rate**. Standard practice is the rate on
  **31 December of the reporting calendar year** for closing values, and the rate on the relevant
  date for peak/initial values. Using the 31-Dec rate throughout is common and defensible **if stated
  consistently** — record in the file which convention was used.
- **Foreign income (Rule 115):** TT buying rate on the **last day of the month immediately preceding**
  the month in which the income accrued or arose.
- **Foreign tax credit (Rule 128):** TT buying rate on the **last day of the month immediately
  preceding** the month in which the tax was paid or deducted.

Use `scripts/fx.py`. It will tell you which date's rate is required for a given basis, and it will
**not** invent a rate: ask the user to supply or confirm the SBI TT buying rate from a published
source.

## 6. Foreign income → Schedule OS / CG / FSI / TR / Form 67

**Report the income.** Foreign dividends and interest are taxable for a resident at slab rates,
whether or not repatriated to India. Dividends → Schedule OS 1a; interest → OS 1b(iii); foreign
capital gains → Schedule CG.

- **Schedule FSI** — per country: country code, taxpayer identification number, head of income,
  income from outside India, tax paid outside India, tax payable in India on that income, relief
  claimed, and the DTAA article. *India–US: Article 10 dividends, Article 11 interest, Article 13
  gains, Article 25 for relief.*
- **Schedule TR** — summary of tax relief claimed, by country, distinguishing relief u/s 90/90A
  (DTAA) from relief u/s 91 (no DTAA).
- **Form 67** — must be filed **online before or along with the return** (and in any case before the
  end of the AY) to claim FTC. A return claiming FTC without Form 67 invites disallowance. **Flag
  this as a hard blocker in the pre-submission checklist.**

**Consistency check to run every time:** if Schedule FA discloses a dividend-paying foreign holding
but Schedule OS shows no foreign dividend, that is a visible internal mismatch *within the same
return* — a common trigger for a notice, and for a 270A under-reporting penalty. Surface it. If the
user still chooses to omit it, record a `DECISION LOG` entry with the date, the amount, the risk you
stated, and their instruction.

## 7. Penalty exposure — state this once, plainly

- Non-disclosure or inaccurate disclosure of foreign assets/income attracts a penalty of
  **₹10,00,000 per year** under the Black Money (Undisclosed Foreign Income and Assets) Act,
  **independent of the tax involved**.
- Relief: since **1 October 2024**, that penalty does not apply where the aggregate value of the
  undisclosed foreign asset(s) — other than immovable property — does not exceed **₹20,00,000**.
- Therefore: **a low-value foreign account is not a reason to skip Schedule FA.** Disclose everything.
- If a prior year's FA disclosure was missed, a revised return for that AY (if still within time)
  closes the gap. Recommend it, and record the revised acknowledgement number.

## 8. Questions to ask

1. Do you hold any foreign bank account, brokerage account, stock, RSU/ESPP, foreign crypto, foreign
   insurance policy, foreign property, or signing authority over a foreign account — **at any point
   during the calendar year**?
2. For each account: institution name, full address with ZIP, account number, date opened, and your
   status (owner / beneficial owner / beneficiary).
3. Do you have the **31 December** year-end statement for each — not the FY statement?
4. Any dividends, interest, or sale proceeds during the Indian FY? Any foreign tax withheld?
5. Have you filed Form 67 before? Do you intend to claim FTC this year?
6. Were foreign assets disclosed in prior years' returns? *(If not, raise the revised-return option.)*

## 9. Output

`ITR2_Schedule_FA_conclusions.md`, in the structure required by `10_output_templates.md`. State
explicitly, in the file: the calendar-year window used, the FX convention used, and the A2-vs-A3
split reasoning.
