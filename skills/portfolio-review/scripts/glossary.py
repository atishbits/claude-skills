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
    ("Consensus", "the average view of the analysts covering a stock",
     "here, the average of the brokers' named, dated target prices",
     r"\bconsensus\b"),
    ("Underperform", "a broker's sell-side rating",
     "the analyst expects the stock to do worse than the market; a polite word for Sell",
     r"\bUnderperform\b"),
    ("Re-rating", "a change in the multiple the market pays",
     "the share price moving because investors pay a higher or lower P/E, not because profit estimates changed",
     r"\bre-?rat(?:ing|ed)\b"),
    ("P/E stretch", "a rise carried by the multiple, not by profit",
     "the price rose mostly because investors pay a higher P/E while profit per share grew little; such rises tend to revert",
     r"P/E stretch|stretched P/E"),
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
    ("H1/H2", "first and second half of the financial year",
     "April to September and October to March, for a company whose year ends in March",
     r"\bH[12]\b"),
    ("Constant currency", "growth with exchange rates held fixed",
     "revenue growth after removing the effect of the rupee moving against other currencies; the business's own growth",
     r"\bconstant[- ]currency\b"),
    ("TCV", "total contract value",
     "the full value of the deals signed in the period, earned as revenue over the years the contracts run",
     r"\bTCV\b"),
    ("bps", "basis points",
     "hundredths of a percentage point; 50 bps is 0.5 percentage points",
     r"\bbps\b"),
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
    ("NIM", "net interest margin",
     "what a bank earns on its loans minus what it pays on deposits, as a share of its lending assets",
     r"\bNIMs?\b"),
    ("NII", "net interest income",
     "a bank's interest earned minus interest paid, in rupees; its main revenue line",
     r"\bNII\b"),
    ("GNPA", "gross non-performing assets",
     "loans whose repayments are more than 90 days overdue, as a share of all loans",
     r"\bG?NPAs?\b"),
    ("CC", "constant currency",
     "growth measured as if exchange rates had not moved, so it shows the business rather than the rupee",
     r"\bCC\b|constant currency"),
    ("LT / ST", "long-term / short-term holding",
     "shares held more than 12 months (LT, 12.5% tax on gains above the yearly exemption) or less (ST, 20%)",
     r"\b(?:LT|ST)\b"),
    ("IPO", "initial public offering",
     "a company selling shares to the public for the first time before it lists on the exchange",
     r"\bIPOs?\b"),
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
    ("FIFO", "first in, first out",
     "shares sold from a demat account are taken from its oldest purchase first, and tax follows that order; the only choice is which account to sell from",
     r"\bFIFO\b"),
    ("Break-even drop", "the fall that cancels the tax saved by waiting",
     "how far the price can drop before waiting for the lower long-term rate loses more than it saves",
     r"\bbreak-?even drop\b"),
    ("Realised gain", "profit or loss locked in by a sale",
     "the gain that exists once shares are sold, and the one that is taxed; a gain on shares still held is unrealised",
     r"\breali[sz]ed (?:gain|loss)(?:es|s)?\b"),
    ("NSE / BSE", "National Stock Exchange / Bombay Stock Exchange",
     "India's two main stock exchanges, where companies also file their announcements",
     r"\bNSE\b|\bBSE\b"),
    ("SEBI", "Securities and Exchange Board of India",
     "the stock-market regulator",
     r"\bSEBI\b"),
    ("PSU", "public sector undertaking",
     "a company controlled by the government",
     r"\bPSUs?\b"),
    ("BUY", "buy rating",
     "buying at today's price is right, whether adding to a holding or starting one",
     r"\bBUY\b"),
    ("HOLD", "hold rating",
     "keep what you own and do not add at today's price (the note may name a lower price to add at); for a stock not owned, keep watching",
     r"\bHOLD\b"),
    ("SELL / trim", "sell rating",
     "sell the position, or part of it; the note names which purchase lots to sell first",
     r"\bSELL\b"),
    ("Trim", "selling part of a position",
     "selling some of the shares and keeping the rest, often in planned steps",
     r"\btrim(?:s|med|ming)?\b"),
    ("Sell plan", "a staged exit saved for one stock",
     "step 1 sold now, step 2 only if a named price level breaks, and a core held until the business itself weakens",
     r"\bsell plans?\b"),
    ("Record date", "the cut-off date for a dividend",
     "shareholders on the company's register that day receive the dividend; with next-day settlement, buy at least one trading day before",
     r"\brecord date\b"),
    ("UPI", "Unified Payments Interface",
     "India's instant bank-to-bank payment system, used through phone apps",
     r"\bUPI\b"),
    ("MDR", "merchant discount rate",
     "the fee a merchant pays on each payment it accepts, shared among the banks and payment apps involved",
     r"\bMDR\b"),
    ("MNC", "multinational company",
     "here, the Indian listed arm of a foreign parent, which usually holds most of the shares",
     r"\bMNCs?\b"),
    ("GLP-1", "glucagon-like peptide-1 drugs",
     "the newer diabetes and weight-loss injections (semaglutide and similar) taking share from older treatments",
     r"\bGLP-?1\b"),
    ("Nifty 500", "the NSE's index of 500 companies",
     "the 500 largest listed Indian companies, covering most of the market's value",
     r"\bNifty 500\b"),
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
CASE_INSENSITIVE = {"Run-rate P/E", "Tranche", "Capex", "Beta", "52wk range", "Promoters", "Pledge", "Debt/EBITDA",
                    "Constant currency", "Consensus", "Record date", "Re-rating",
                    "P/E stretch", "Break-even drop", "Realised gain", "Trim", "Sell plan"}


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
