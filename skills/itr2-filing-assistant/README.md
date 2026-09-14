# itr2-filing-assistant

Prepares a complete, cross-verified **ITR-2 worksheet** for an Indian resident individual —
schedule by schedule, reconciled against AIS/TIS/26AS, with a validation sweep before submission.

It captures the method from two real ITR-2 filings under the new regime covering salary, co-owned
let-out house property, capital gains, other sources, foreign assets (US brokerage + employer RSU
plan), FSI/TR/Form 67 and AIS/TIS reconciliation. **Only the method is here.** Every figure,
identifier and document from those filings was left behind.

## What it does not do

It does **not** file your return, does **not** log into or automate incometax.gov.in, and does
**not** replace a CA. It produces a worksheet you type into the portal yourself.

## How it works

Eleven phases, run in order. `SKILL.md` is only the router and the guardrails; each phase's detail
lives in `references/` and is read **when that phase starts**, so a short session never pays for the
long ones.

| Phase | | Phase | |
|---|---|---|---|
| 0 | Applicability & regime | 6 | Foreign assets & income |
| 1 | Document intake | 7 | Set-off, CFL, AL, taxes paid |
| 2 | Salary | 8 | Tax computation & regime comparison |
| 3 | House property | 9 | Reconciliation & validation sweep |
| 4 | Capital gains | 10 | Final worksheet + pre-submission checklist |
| 5 | Other sources | | |

Capital gains runs before other sources (CG output determines what to exclude from OS), and foreign
assets runs before the tax computation (FSI/TR relief changes the liability).

Each phase writes a conclusions file — computation, cross-checks, flags, a `PENDING` list and a
`DECISION LOG` — so a dead session resumes from the files rather than starting over.

## Your documents stay yours

This repo holds statutory rates, procedure and templates. **Nothing personal is ever written here.**

Point the skill at a working folder of your own — `~/Documents/itr/AY2026-27/`, say — and every
conclusions file, worksheet and rate lookup lands there. Your Form 16, AIS, 26AS and broker
statements stay where they are and are read locally; nothing is uploaded anywhere.

The skill will not echo a PAN, Aadhaar, bank account or full broker account number into chat unless
you ask it to, and will not carry any of it into memory.

## Scripts

```
python3 scripts/tax_calc.py --regime new --ay 2026-27 --normal-income N \
  --ltcg-112a N --stcg-111a N --tds N --advance-tax N [--compare]
python3 scripts/tax_calc.py --selftest

python3 scripts/fx.py --amount 1200 --currency USD --date 2025-11-14 --basis rule115
```

`tax_calc.py` is a dependency-free slab / rebate / surcharge / cess calculator with the awkward bits
implemented rather than approximated: 87A marginal relief, surcharge marginal relief at each band
floor, the 15% surcharge cap on 111A/112/112A/dividend tax, unused basic exemption set against
capital gains, and 234B/234C estimates. Rate tables are keyed by AY, so a new year is one edit —
in `RATES` and in `references/08_rates_and_thresholds.md`, which must stay in step. `--selftest`
covers the rebate cliff, every surcharge band boundary and the cap case.

`fx.py` deals with the conversion date, which is where foreign figures go wrong quietly: Rule 115
(income), Rule 128 (foreign tax credit) and Schedule FA each want a different date, and none of them
is the transaction date. Give it the event date and it tells you which date's SBI TT buying rate to
look up. **It never guesses a rate** — you supply it, or keep looked-up rates in a JSON file in your
own folder.

## Three things this catches that are easy to miss

- **Schedule FA runs on the calendar year** (1 Jan – 31 Dec), while foreign *income* runs on the
  financial year. Broker "tax reports" are frequently produced on the wrong window and cannot be
  used for peak/closing values.
- **Portal prefill is a suspect, not a source** — deduction u/s 16 showing ₹50,000 under the new
  regime, the whole year's dividend dumped into the "Upto 15/6" bucket, AIS reporting cost of
  acquisition as zero, FA rows prefilled with zero balances. The reconciliation ladder is *primary
  document > TIS > AIS > prefill*.
- **A disclosed foreign asset with undisclosed income** is a visible internal mismatch inside the
  same return. Check #8 of the validation sweep exists for it.

---

*General help, not formal tax advice — CA review advised before filing.*
