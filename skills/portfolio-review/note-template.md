# Per-stock note format — `stocks/<TICKER>.md`

Read this before writing or rewriting any note. `PORTFOLIO.md` checks every note for the required
fields and lists any that are missing under "Notes on an old template".

Keep it brief: under ~350 words. The Balance sheet, Guidance and Portfolio context fields are one
line each, not paragraphs. Match this structure:

```markdown
# TICKER — Company Name

**Last analysis:** <today, e.g. 11 Sep 2026> (prev <date from the file you are replacing, or "first analysis">)
**My inputs:** <qty> shares @ avg ₹<cost> — approx <+/-N%> at ₹<price> (screener, <date>)

**Rating:** <BUY | HOLD | SELL / trim><, UPGRADED or DOWNGRADED from <prev> if it moved>
**Action:** Now: <buy N / nothing / trim N>. Then: <what, at which level, or "nothing">.
**Signal row:** Row <N> → *<row description from the cheat sheet>* (confidence: <high | low, and why>)

**Snapshot (<date>):** Price ₹X (screener, <date><; CSV ₹Y on <date> if they differ by more than 2%>),
<N>% up the 52wk range (₹low–high). P/E N<, forward range if trailing and run-rate diverge>.
ROE N%, ROCE N%. Consensus <rating>, avg TP ₹N = <N% upside | below price> — <N of M post-result | unavailable>.
**Balance sheet:** <gross debt ₹N Cr, D/E N, debt/EBITDA N, direction; net debt ₹N Cr at <date> if
material | low / effectively debt-free (₹N Cr) / debt-free (nil) | lender, not applicable>.
**Cash & ownership:** <CFO N.Nx profit over 5 years | lender, not applicable>. ROCE N% against a
5-year peak of N%. <Promoters N% (<+/-N pp over the window>), FIIs N% (<+/-N pp>); pledge N% of
promoter holding as of <date> | no pledge on file as of <date> | pledge data unavailable>.
<Insider dealing only if the block is fresh, with the date of the newest filing.>
**Technicals:** <N% vs 200DMA (or 50DMA if 200 is unreliable), RSI N <oversold|neutral|overbought>,
3m/6m return, 60-day range ₹low–high, beta N. Only the readings that matter for this call.>
**Portfolio context:** <N% of book; <sector> N% incl. <largest peers>, and the economically-linked
weight if the CSV tag understates it. What the Action does to that.>

**What changed since last analysis:**
- <**Correction:** what the previous note got wrong, if anything>
- <latest quarter by end month: revenue, PAT, margin, and the quality of the growth>
- <corporate actions, capacity, management, regulatory>

**Guidance:** <what management guided, source and date. Prior guidance: met | missed | pending | none recorded.>

**Notes:** <why this rating and not the adjacent one, what the market is pricing in, and what would
change the call. Name the re-look price anchored on a real level: the 200 DMA, the 60-day low, or
the consensus low estimate, not a round number picked by feel.>

---

*Not investment advice — verify prices and figures before acting.*
```

## Rules for these files

- Preserve `**My inputs:**` and roll the old analysis date into the `(prev ...)` field on every
  rewrite, including a same-day re-rating. Never drop the history.
- Mark a rating change as **UPGRADED** or **DOWNGRADED** so the direction is visible at a glance.
- If this run shows the previous note got a fact wrong, open "What changed" with a **Correction:**
  line saying what was wrong. Do not quietly overwrite it.
- Where a number is unavailable, write it as unavailable. Do not carry a stale figure forward as if
  it were current, and do not estimate a consensus target you did not find. In **Cash & ownership**
  in particular, an absent pledge or insider filing is not a clean bill: say the data is
  unavailable, or give the date of the newest filing on file (SKILL.md 3b.6).
- **Cash & ownership** was added on 12 Sep 2026 and is not in the required-field check, so notes
  written before it are not flagged as being on an old template. Add the line whenever you rewrite
  one.
- The disclaimer footer is part of the template, not optional.
