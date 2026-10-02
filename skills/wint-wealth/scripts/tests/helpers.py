"""Test helpers: build a small .xlsx in memory-free stdlib code, and a sample
Master Report shaped like Wint's (identity preamble, header on row 8, a side
table, repeated financial-year blocks, a trailing disclaimer). Every issuer,
ISIN and amount here is invented."""
import zipfile
from xml.sax.saxutils import escape

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def _col(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def make_xlsx(path, sheets):
    """sheets: {name: [[cell, ...], ...]}. Cells are inline strings; None and
    "" are omitted, which leaves a gap exactly as a real sheet would."""
    with zipfile.ZipFile(path, "w") as z:
        sheet_tags, rel_tags = [], []
        for i, (name, rows) in enumerate(sheets.items(), start=1):
            sheet_tags.append(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>')
            rel_tags.append(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>')
            body = []
            for r, row in enumerate(rows, start=1):
                cells = "".join(
                    f'<c r="{_col(c)}{r}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'
                    for c, v in enumerate(row) if v not in (None, ""))
                body.append(f'<row r="{r}">{cells}</row>')
            z.writestr(
                f"xl/worksheets/sheet{i}.xml",
                f'<worksheet xmlns="{MAIN}"><sheetData>{"".join(body)}</sheetData></worksheet>')
        z.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets>{"".join(sheet_tags)}</sheets></workbook>')
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{PKG}">{"".join(rel_tags)}</Relationships>')


PREAMBLE = [[], ["Wint Wealth"], ["Name", "Asha Example"], ["Phone Number", "0000000000"],
            ["Email", "asha@example.com"], [" "]]
DISCLAIMER = ["Disclaimer: The document is for informational purposes only."]

HOLD_HEADERS = ["Name Of Bond", "ISIN", "Maturity Date", "Units", "YTM", "Current Value",
                "Upcoming Sell Value", "Upcoming interest", "Upcoming Principal", "Total Invested",
                "Total Sold", "Principal Repaid till Date",
                "Interest Paid (Before TDS Deduction) till Date",
                "Interest Paid (After TDS Deduction) till Date", "TDS Deducted till Date",
                "Principal Repayment Type", "Interest Repayment Type"]
CF_HEADERS = ["Name Of Bond", "ISIN", "Date", "Amount in Bank", "Principal Repaid",
              "Interest Paid (After TDS deduction)", "Interest Paid (Before TDS deduction)", "TDS",
              "Sell Value", "Transactiontype"]
CF_SIDE = ["", "Financial Year", "Amount in Bank", "Principal", "Interest (After TDS Deduction)",
           "Interest (Before TDS Deduction)", "TDS", "Sell Value"]
REP_HEADERS = ["Date", "Name Of Bond", "ISIN", "No. Of Units", "Amount in Bank", "Principal Repaid",
               "Interest Paid (Before TDS Deduction)", "Interest Paid (After TDS Deduction)",
               "TDS Deducted"]
INV_HEADERS = ["Bond Name", "ISIN", "No. Of Units", "Invested Amount", "Face Value",
               "Acquisition Cost*", "Date of Investment", "Maturity Date", "XIRR",
               "Frequency of Interest Payment", "Frequency Of Principal Repayment"]

ALPHA = "INE000A07011"
BETA = "INE000B07022"


def sample_report():
    holdings = PREAMBLE + [
        ["Bonds Holding Statement"],
        HOLD_HEADERS,
        ["Alpha Finance", ALPHA, "31-12-2027", "2.0", "12.0", "20000.0", "", "2400.0", "20000.0",
         "20000.0", "", "", "400.0", "360.0", "40.0", "At Maturity", "Monthly"],
        ["Beta Capital", BETA, "30-06-2027", "1.0", "10.0", "10000.0", "", "500.0", "10000.0",
         "10000.0", "", "", "", "", "", "Staggered", "Quarterly"],
        [" "],
    ]
    cashflows = PREAMBLE + [
        ["Upcoming Cashflow Statement"],
        CF_HEADERS + CF_SIDE,
        ["Alpha Finance", ALPHA, "15-10-2026", "180.0", "", "180.0", "200.0", "20.0", "", "INTEREST",
         "", "2026-2027", "999.0", "999.0", "999.0", "999.0", "999.0", ""],
        ["Beta Capital", BETA, "30-10-2026", "5250.0", "5000.0", "250.0", "250.0", "", "",
         "PRINCIPAL AND INTEREST"],
        ["Alpha Finance", ALPHA, "15-11-2026", "180.0", "", "180.0", "200.0", "20.0", "", "INTEREST"],
        [" "],
    ]
    repayments = PREAMBLE + [
        ["", "", "", "", "REPAYMENT SUMMARY (1/04/2025 - 31/03/2026) FY 25-26"],
        REP_HEADERS,
        ["15/03/2026", "Alpha Finance", ALPHA, "2.0", "180.0", "0.0", "200.0", "180.0", "20.0"],
        [],
        ["", "", "", "", "REPAYMENT SUMMARY (1/04/2026 - 31/03/2027) FY 26-27"],
        REP_HEADERS,
        ["15/09/2026", "Alpha Finance", ALPHA, "2.0", "180.0", "0.0", "200.0", "180.0", "20.0"],
        DISCLAIMER,
    ]
    investments = PREAMBLE + [
        ["", "", "", "", "INVESTMENT SUMMARY (1/04/2025 - 31/03/2026) FY 25-26"],
        INV_HEADERS,
        ["Alpha Finance", ALPHA, "2.0", "20000.0", "20000.0", "-", "01/01/2026", "31/12/2027",
         "12.00%", "Monthly", "At Maturity"],
        ["Beta Capital", BETA, "1.0", "10000.0", "10000.0", "-", "01/07/2026", "30/06/2027", "10%",
         "Quarterly", "Staggered"],
        DISCLAIMER,
    ]
    sells = PREAMBLE + [["Date of report generation:", "02/10/2026"], [], DISCLAIMER]
    return {
        "Investment Summary Report": investments,
        "Repayment Summary Report": repayments,
        "Sell Summary Report": sells,
        "Upcoming Cashflow Statement": cashflows,
        "Holding Statement": holdings,
    }
