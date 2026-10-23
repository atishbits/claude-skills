# Realised gains from the broker (normalised CSV)

The broker's tax P&L report is converted into this shape on the laptop by the model, then passed to
`python3 scripts/gains_log.py reconcile PATH`. Which report to download, and where, is in your
`data/notes.md`. One row per matched buy lot of a sale, so a sale that consumed three lots is three rows.

```csv
account,symbol,sell_date,qty,sell_price,buy_date,buy_price,gain,term,charges
brokera,STOCKA,2026-10-20,6,150.00,2026-01-15,100.00,295.00,ST,5.00
brokera,STOCKA,2026-10-20,4,150.00,2020-01-01,50.00,395.00,LT,3.00
brokera,STOCKB,2026-10-21,5,200.00,2025-02-01,180.00,95.00,ST,5.00
```

| Column | Meaning |
|---|---|
| `account` | The demat account (broker) name, the same label used when logging a sale. |
| `symbol` | The ticker as it appears in the portfolio. |
| `sell_date` | Sale date, `YYYY-MM-DD`. |
| `qty` | Shares of this lot sold. |
| `sell_price` | Price per share at which they sold. |
| `buy_date` | Date this lot was bought, `YYYY-MM-DD`. |
| `buy_price` | Cost per share of this lot. |
| `gain` | Realised gain on this row, as the broker reports it, already net of deductible charges. |
| `term` | `ST` (held 12 months or less) or `LT` (held longer). |
| `charges` | Deductible sale expenses for this row (brokerage, exchange charges, GST on them; not STT). |

Rows are grouped into one sale per (`account`, `symbol`, `sell_date`). A logged sale with the same
key and quantity is confirmed with the broker's figures. A sale not logged is imported. A quantity
difference, or a gain differing by more than 1% plus Rs 10, is listed as a mismatch and left
unconfirmed. Running it again changes nothing.

*Not investment advice. Verify figures before acting.*
