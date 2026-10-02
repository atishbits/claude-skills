import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import xlsx_reader  # noqa: E402
from helpers import make_xlsx  # noqa: E402


class TestReadWorkbook(unittest.TestCase):
    def test_reads_sheets_by_name_and_keeps_column_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "book.xlsx")
            make_xlsx(path, {"First": [["a", "", "c"], [], ["x"]], "Second": [["only"]]})
            book = xlsx_reader.read_workbook(path)
        self.assertEqual(list(book), ["First", "Second"])
        self.assertEqual(book["First"][0], ["a", "", "c"])
        self.assertEqual(book["First"][1], [])
        self.assertEqual(book["Second"], [["only"]])


if __name__ == "__main__":
    unittest.main()
