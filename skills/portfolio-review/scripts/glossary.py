#!/usr/bin/env python3
"""Prints a plain-English footer for the finance shorthand a reply uses: each
term's full form and a one-line explanation, ready to paste at the end of the
chat summary. Which terms appear and how they are worded is fixed here, so the
footer reads the same every run instead of being re-composed each time.

    python3 scripts/glossary.py --terms "RSI,EBITDA,200 DMA"   # scorecard terms + these
    python3 scripts/glossary.py --no-scorecard --terms "CAGR"  # only these
    python3 scripts/glossary.py --file path/to/text.md         # every known term in a file
    python3 scripts/glossary.py --all                          # the whole glossary

The terms the Step 4 scorecard always prints are included by default; `--terms`
adds whatever else the reply itself used, so the footer covers the reply and
not every term that exists. A `--terms` entry with no glossary line is reported
on stderr rather than dropped silently, so the gap gets filled here."""
import argparse
import re
import sys

# The Step 4 scorecard prints these on every run, whatever the note says.
SCORECARD_TEXT = "P/E run-rate ROE ROCE TP"

# (label, full form, one-line explanation, regex that spots it in text).
# Order here is the order of the footer: valuation, quality, results,
# balance sheet and cash, chart readings, ownership, tax, the rest.
GLOSSARY = [
    ("P/E", "price-to-earnings ratio",
     "share price divided by a year's profit per share; how many years of today's profit you pay for the stock",
     r"\bP/E\b"),
    ("Run-rate P/E", "P/E on the latest quarter annualised",
     "the same ratio using the newest quarter's profit times four instead of the last twelve months",
     r"\brun-?rate\b"),
    ("PEG", "price/earnings-to-growth",
     "P/E divided by the profit growth rate; around 1 or below means the growth is not overpriced",
     r"\bPEG\b"),
    ("GARP", "growth at a reasonable price",
     "buying a growing business only when its P/E is in line with that growth",
     r"\bGARP\b"),
    ("EPS", "earnings per share",
     "the company's profit divided by the number of shares",
     r"\bEPS\b"),
    ("TP", "target price",
     "the price a broker's analyst expects the share to reach, usually within 12 months",
     r"\bTP\b"),
    ("ROE", "return on equity",
     "profit as a percentage of shareholders' own money in the business; higher means it earns more per rupee invested",
     r"\bROE\b"),
    ("ROCE", "return on capital employed",
     "operating profit as a percentage of all the money the business uses, shareholders' funds plus debt",
     r"\bROCE\b"),
    ("EBITDA", "earnings before interest, tax, depreciation and amortisation",
     "profit from running the business before financing and accounting charges; EBITDA margin is that as a share of sales",
     r"\bEBITDA\b"),
    ("EBIT", "earnings before interest and tax",
     "operating profit after depreciation, before financing costs and tax",
     r"\bEBIT\b"),
    ("PBT", "profit before tax",
     "profit after all costs and interest, before income tax",
     r"\bPBT\b"),
    ("PAT", "profit after tax",
     "the final net profit left for shareholders",
     r"\bPAT\b"),
    ("TTM", "trailing twelve months",
     "the last four reported quarters added together",
     r"\bTTM\b"),
    ("YoY", "year-on-year",
     "compared with the same period a year earlier",
     r"\bYoY\b"),
    ("QoQ", "quarter-on-quarter",
     "compared with the previous quarter",
     r"\bQoQ\b"),
    ("CAGR", "compound annual growth rate",
     "the steady yearly rate that would turn the starting figure into the ending one",
     r"\bCAGR\b"),
    ("FY", "financial year",
     "April to March for most Indian companies; FY27 ends on 31 March 2027",
     r"\bFY\s?\d{2,4}E?\b|\bFY\b"),
    ("Q1-Q4", "quarters of the financial year",
     "for a March year-end, Q1 is April-June, Q2 July-September, Q3 October-December, Q4 January-March",
     r"\bQ[1-4]\b"),
    ("Cr", "crore",
     "ten million rupees (₹1,00,00,000)",
     r"\bCr\b"),
    ("pp", "percentage points",
     "the plain difference between two percentages; 54% to 53% is a fall of 1pp",
     r"\d\s?pp\b"),
    ("D/E", "debt-to-equity ratio",
     "borrowings divided by shareholders' funds; lower means less debt",
     r"\bD/E\b"),
    ("Debt/EBITDA", "debt to yearly operating profit",
     "roughly how many years of operating profit it would take to repay the borrowings",
     r"\bdebt/EBITDA\b"),
    ("CFO", "cash flow from operations",
     "the cash the business actually collected from its operations, as against the profit it reported",
     r"\bCFO\b"),
    ("FCF", "free cash flow",
     "operating cash left after spending on plant and equipment",
     r"\bFCF\b"),
    ("Capex", "capital expenditure",
     "money spent on plant, equipment and other long-lived assets",
     r"\bcapex\b"),
    ("DMA", "day moving average",
     "the average closing price over that many trading days; the 200 DMA is the usual long-term trend line",
     r"\bDMA\b|\d\s?DMA\b"),
    ("RSI", "relative strength index",
     "a 0-100 gauge of recent price momentum; below about 30 is read as oversold, above about 70 as overbought",
     r"\bRSI\b"),
    ("Beta", "sensitivity to the index",
     "how much the stock tends to move when the Nifty moves 1%; below 1 means it swings less than the market",
     r"\bbeta\b"),
    ("Tranche", "one slice of a planned purchase",
     "the total budget is split into parts bought at different times or prices instead of all at once",
     r"\btranches?\b"),
    ("52wk range", "52-week range",
     "the lowest and highest prices of the past year",
     r"\b52[- ]?(?:wk|week)\b"),
    ("LTP", "last traded price",
     "the most recent price the share changed hands at",
     r"\bLTP\b"),
    ("P&L", "profit and loss",
     "the gain or loss on a position against what was paid for it",
     r"\bP&L\b"),
    ("Promoters", "founders and controlling shareholders",
     "the family or group that runs the company; their stake falling is a caution sign",
     r"\bpromoters?\b"),
    ("Pledge", "promoter shares given as loan collateral",
     "shares that lenders can sell if the promoter's loan goes bad",
     r"\bpledged?\b"),
    ("FII", "foreign institutional investors",
     "overseas funds investing in Indian shares",
     r"\bFIIs?\b"),
    ("DII", "domestic institutional investors",
     "Indian mutual funds, insurers and pension funds",
     r"\bDIIs?\b"),
    ("OFS", "offer for sale",
     "an existing large shareholder selling shares to the public through the exchange",
     r"\bOFS\b"),
    ("SAST", "substantial acquisition of shares and takeovers filings",
     "the disclosure a holder must file when a large stake changes",
     r"\bSAST\b"),
    ("RPT", "related-party transactions",
     "dealings between the company and its promoters or their other businesses",
     r"\bRPTs?\b"),
    ("LTCG", "long-term capital gains",
     "profit on shares held more than 12 months, taxed at 12.5% above the yearly exemption",
     r"\bLTCG\b"),
    ("STCG", "short-term capital gains",
     "profit on shares held 12 months or less, taxed at 20%",
     r"\bSTCG\b"),
    ("LT/ST", "long-term / short-term",
     "whether a lot has been held more than 12 months, which sets its tax rate",
     r"\bLT/ST\b"),
    ("NSE / BSE", "National Stock Exchange / Bombay Stock Exchange",
     "India's two main stock exchanges, where companies also file their announcements",
     r"\bNSE\b|\bBSE\b"),
    ("SEBI", "Securities and Exchange Board of India",
     "the stock-market regulator",
     r"\bSEBI\b"),
    ("PSU", "public sector undertaking",
     "a company controlled by the government",
     r"\bPSUs?\b"),
    ("NBFC", "non-banking financial company",
     "a lender that is not a bank",
     r"\bNBFCs?\b"),
    ("GST", "goods and services tax",
     "India's sales tax; a rate change shifts demand and distorts year-on-year comparisons",
     r"\bGST\b"),
    ("M&A", "mergers and acquisitions",
     "growth by buying or combining with other companies",
     r"\bM&A\b"),
]

# Terms matched as written: "PAT" must not fire on "pat", "TP" not on "tp".
# The rest are ordinary words and match in any case.
CASE_INSENSITIVE = {"Run-rate P/E", "Tranche", "Capex", "Beta", "52wk range", "Promoters", "Pledge", "Debt/EBITDA"}


def terms_in(text):
    """Glossary labels found in `text`, in glossary order."""
    found = []
    for label, _full, _line, pattern in GLOSSARY:
        flags = re.IGNORECASE if label in CASE_INSENSITIVE else 0
        if re.search(pattern, text, flags):
            found.append(label)
    return found


def resolve_terms(names):
    """Map free-typed names ("rsi", "200 DMA", "ebitda margin") to glossary
    labels. Returns (labels, unknown names)."""
    labels, unknown = [], []
    by_label = {label.lower(): label for label, *_ in GLOSSARY}
    for raw in names:
        name = raw.strip()
        if not name:
            continue
        if name.lower() in by_label:
            labels.append(by_label[name.lower()])
            continue
        hit = terms_in(name) or terms_in(name.upper())
        if hit:
            labels.extend(hit)
        else:
            unknown.append(name)
    return labels, unknown


def render(labels):
    """The footer as markdown, in glossary order, one line per term."""
    wanted = set(labels)
    rows = [(label, full, line) for label, full, line, _ in GLOSSARY if label in wanted]
    if not rows:
        return ""
    out = ["**Terms used**"]
    out.extend(f"- **{label}** ({full}): {line}." for label, full, line in rows)
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--terms", default="", help="comma-separated terms the reply used")
    p.add_argument("--no-scorecard", action="store_true", help="leave out the scorecard's own terms")
    p.add_argument("--file", action="append", default=[], help="scan this text file for known terms")
    p.add_argument("--all", action="store_true", help="print the whole glossary")
    args = p.parse_args()

    if args.all:
        print(render([label for label, *_ in GLOSSARY]))
        return

    labels = [] if args.no_scorecard else terms_in(SCORECARD_TEXT)
    for path in args.file:
        with open(path, encoding="utf-8") as fh:
            labels.extend(terms_in(fh.read()))
    extra, unknown = resolve_terms(args.terms.split(","))
    labels.extend(extra)
    if unknown:
        print("No glossary line for: " + ", ".join(unknown)
              + " -- explain these inline, and add them to GLOSSARY in glossary.py.", file=sys.stderr)

    footer = render(labels)
    if not footer:
        raise SystemExit("Nothing to explain -- pass --terms, --file or --all.")
    print(footer)


if __name__ == "__main__":
    main()
