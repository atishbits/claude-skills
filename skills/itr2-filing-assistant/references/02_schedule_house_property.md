# Phase 3 — Schedule HP (House Property)

## 1. Computation template — per property, per co-owner

| Line | Field | Rule |
|------|-------|------|
| a | Gross rent received / receivable / lettable value | **Full property value, not the share** |
| b | Rent that cannot be realised | Conditions of Rule 4 must be met |
| c | Tax paid to local authorities | Full property; deductible only if **actually paid** during the FY |
| d | Total (b + c) | |
| e | Annual value (a − d) | Full property |
| f | Annual value of share owned | ownership % × e |
| g | 30% standard deduction u/s 24(a) | **30% of f**, not of e |
| h | Interest on borrowed capital u/s 24(b) | The co-owner's **own share** of the interest |
| i | Total (g + h) | |
| j | Arrears / unrealised rent received, less 30% | |
| k | **Income from house property** | f − i + j |

## 2. Rules that matter

- **Co-ownership.** Each co-owner enters the *same full-property* gross rent and municipal tax, then
  applies their own ownership %. The utility does the apportionment at line f. Both returns must
  mirror each other exactly and the shares must sum to 100%. Each co-owner's return must name the
  other co-owner(s) with PAN and share %.
- **Self-occupied.** Annual value nil; interest deduction capped at ₹2,00,000 — but under the **new
  regime, interest on a self-occupied property is not deductible at all**. Up to two properties may
  be treated as self-occupied.
- **Let out.** The interest deduction itself is uncapped, but the *house-property loss set off
  against other heads* is capped at **₹2,00,000 per person per year**; the excess carries forward 8
  years and can then be set off only against house-property income.
- **Rent is usually self-declared.** It rarely appears in AIS unless TDS u/s 194-I / 194-IB was
  deducted. Verify against the rent agreement, not against AIS silence.
- **If the tenant deducted TDS**, the tenant's TAN/PAN and the TDS amount must be claimed in the TDS
  schedule — and must appear in 26AS.
- **Vacant let-out property.** The annual value can be reduced for the vacancy period.

## 3. Questions to ask

1. How many properties? For each: address, and let out / self-occupied / deemed let out?
2. Co-owned? With whom, what %, and is the co-owner filing their own return?
   *(If yes, offer to prepare the mirror computation — in a separate folder, clearly labelled a
   mirror.)*
3. Actual annual rent received; was there any vacancy?
4. Municipal / property tax **actually paid** during the FY — is the receipt available?
5. Home loan on this property? Interest paid this FY (certificate), in whose name, and what share?
6. Did the tenant deduct TDS?

## 4. Output

`ITR2_Schedule_HP_conclusions.md`, in the structure required by `10_output_templates.md`. If there
is a house-property loss, state in the file whether it exceeds the ₹2,00,000 set-off cap and how much
carries forward — and verify in Phase 7 that the carry-forward lands in Schedule CFL.
