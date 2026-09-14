# Phase 1 — Document intake & inventory

Goal: know exactly what the user has, what is missing, and where each missing thing comes from —
before computing anything.

## 1. Document intake table

Ask which of these the user has and where the file is. Mark each **Have / Missing / N/A**.

| # | Document | Where to get it | Needed for |
|---|----------|-----------------|------------|
| 1 | Form 16 (Part A + Part B) | Employer | Salary, TDS u/s 192 |
| 2 | Form 12BA (annexed to Form 16) | Employer | Perquisites, ESOP/RSU perquisite value |
| 3 | Form 26AS (Annual Tax Statement) | Portal → e-File → Income Tax Returns → View Form 26AS (TRACES) | All TDS/TCS credits, advance tax, self-assessment tax, refunds |
| 4 | AIS (Annual Information Statement) — PDF **and** JSON | Portal → AIS → Download. PDF password = PAN in lowercase + DOB DDMMYYYY | Line-item income cross-check, SFT entries |
| 5 | TIS (Taxpayer Information Summary) | Same AIS module | **Primary reconciliation source** — the "Processed by System" column drives prefill |
| 6 | AIS feedback / Consolidated Feedback PDF (if any submitted) | AIS module | Audit trail for corrections |
| 7 | Bank interest certificates (each bank, savings + FD) | Net banking | Schedule OS 1b |
| 8 | EPF passbook / UAN statement | EPFO member portal | Taxable EPF interest |
| 9 | Demat / broker capital gains statement (Indian) | Broker — "Tax P&L" or "Capital Gains Statement" for the FY | Schedule CG, 112A/111A |
| 10 | Demat dividend statement | Broker / RTA | Quarterly dividend split (Schedule OS §10) |
| 11 | Employer stock plan year-end statement | Plan portal → Statements → year-end (**calendar** year) | Schedule FA, foreign dividend |
| 12 | RSU vest report / grant & vest history | Same plan portal | CG cost basis, perquisite cross-check |
| 13 | Form 1042-S (if US-source income) | Plan portal / broker | Foreign income + US tax withheld → FSI/TR |
| 14 | Indian-app US investing reports — Tax P&L **and** Schedule FA report | App → Reports/Tax | Schedule FA A2/A3, foreign dividend, US CG |
| 15 | Other foreign bank/brokerage statements | Institution | Schedule FA |
| 16 | LRS remittance advice / TCS certificate (206CQ) | Remitting bank | TCS credit claim |
| 17 | Rent agreement + rent receipts (if let out) | Self | Schedule HP gross rent |
| 18 | Municipal tax paid receipt | Municipal body | Schedule HP deduction |
| 19 | Home loan interest certificate | Lender | Sec 24(b) |
| 20 | **Prior year ITR — the full PDF, not the acknowledgement** | Portal → View Filed Returns | Brought-forward losses (Schedule CFL), FA continuity, regime consistency |
| 21 | Advance / self-assessment tax challans | Bank / AIS Part B | Taxes paid |
| 22 | Chapter VI-A proofs (**only if old regime**) | Self | 80C/80D/80G etc. |

## 2. Interview questions — ask these, batched (~6 at a time)

**Identity & status**

1. Which Assessment Year are you filing for, and what is your residential status — Resident &
   Ordinarily Resident (ROR), RNOR, or Non-Resident?
   *Schedule FA applies only to ROR. If not ROR, stop and re-scope: almost everything changes.*
2. Were you outside India for any part of the FY? (Ask for days present in India this FY and in the
   preceding 4 FYs **only** if residential status is genuinely uncertain.)
3. Are you a director in any company, or do you hold unlisted equity shares? *Either forces ITR-2 and
   needs its own disclosure table.*
4. Is your total income likely above ₹50 lakh? *Triggers mandatory Schedule AL.*

**Income heads present this year** (yes/no each)

5. Salary or pension · house property (how many, let out or self-occupied) · capital gains · other
   sources · foreign assets or income · agricultural income · clubbed income (spouse/minor) · any
   income from a business or profession.
   *Business/professional income → ITR-3. Wrong form. Stop.*

**Regime**

6. Which regime did you file under last year, and which one does your Form 16 use? Do you want a
   side-by-side comparison this year?

**Foreign specifics**

7. Do you hold any foreign bank account, brokerage account, stock, ESOP/RSU, crypto on a foreign
   exchange, immovable property abroad, or signing authority over any foreign account?
   *Any yes → Schedule FA is mandatory, and the Black Money Act penalty regime applies.*
8. If RSUs: which plan administrator, and did you sell any shares this FY?
9. Any foreign remittance under LRS this FY?

**Prior year**

10. Do you have brought-forward losses from earlier years? Was last year's return filed on time?

## 3. Output of this phase

Write `00_Document_Review_and_Data_Inventory.md` in the user's working folder, containing:

- **Assessee block** — name, PAN (full in the file, masked in chat), AY/FY, regime, employer.
- **Documents on file** — the table above with Have/Missing/N/A and the local path of each file.
- **Per-head first-pass figures** — whatever is already legible from the documents, each with its
  source.
- **Gaps / still needed** — numbered, each naming exactly where to get the item.
- **Questions for the user** — numbered, the ones still unanswered.

Follow the mandatory conclusions-file structure in `10_output_templates.md`.
