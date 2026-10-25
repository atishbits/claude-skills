import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import readers  # noqa: E402

FX = os.path.join(os.path.dirname(__file__), "fixtures")
_TMP = tempfile.mkdtemp()


def bank_csv():
    """The example bank statement as a .csv (the repo keeps no CSV files)."""
    p = os.path.join(_TMP, "bank_statement.csv")
    if not os.path.exists(p):
        shutil.copy(os.path.join(FX, "bank-statement-example.txt"), p)
    return p

SHEET = """<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row>
<row r="2"><c r="A2" t="inlineStr"><is><t>05/04/2026</t></is></c><c r="B2"><v>12.5</v></c><c r="C2" t="s"><v>2</v></c></row>
</sheetData></worksheet>"""
SST = """<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<si><t>Date</t></si><si><t>Remarks</t></si><si><r><t>SHOP</t></r><r><t>MART</t></r></si></sst>"""


class TestReaders(unittest.TestCase):
    def test_read_csv_rows(self):
        rows = readers.read_rows(bank_csv())
        self.assertEqual(rows[0][0], "DETAILED STATEMENT")
        self.assertEqual(len(rows), 10)

    def test_read_xlsx_stdlib(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.xlsx")
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("xl/worksheets/sheet1.xml", SHEET)
                z.writestr("xl/sharedStrings.xml", SST)
            rows = readers.read_rows(p)
        self.assertEqual(rows[0], ["Date", "", "Remarks"])
        self.assertEqual(rows[1], ["05/04/2026", "12.5", "SHOPMART"])

    def test_xls_without_xlrd_explains(self):
        with mock.patch.dict(sys.modules, {"xlrd": None}):
            with self.assertRaises(SystemExit) as cm:
                readers.read_rows(os.path.join(FX, "nothing.xls"))
        self.assertIn("CSV/XLSX/PDF", str(cm.exception))

    def test_read_text_lines(self):
        rows = readers.read_rows(os.path.join(FX, "card-statement-example.txt"))
        self.assertTrue(all(len(r) == 1 for r in rows))
        self.assertIn("Card ending 4321", rows[2][0])


if __name__ == "__main__":
    unittest.main()
