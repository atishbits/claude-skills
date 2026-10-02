import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import ingest  # noqa: E402
import xlsx_reader  # noqa: E402
from helpers import ALPHA, BETA, HOLD_HEADERS, make_xlsx, sample_report  # noqa: E402

CONFIG = common.load_config()


def snapshot_of(sheets):
    return ingest.build_snapshot(sheets, CONFIG, "2026-10-02", "abc123")


class TestBuildSnapshot(unittest.TestCase):
    def setUp(self):
        self.snap = snapshot_of(sample_report())

    def test_holdings_are_typed(self):
        alpha = self.snap["holdings"][0]
        self.assertEqual(alpha["issuer"], "Alpha Finance")
        self.assertEqual(alpha["isin"], ALPHA)
        self.assertEqual(alpha["maturity_date"], "2027-12-31")
        self.assertEqual(alpha["units"], 2.0)
        self.assertEqual(alpha["ytm"], 12.0)
        self.assertEqual(alpha["current_value"], 20000.0)
        self.assertIsNone(alpha["sold"])
        self.assertEqual(alpha["interest_frequency"], "Monthly")
        self.assertEqual(len(self.snap["holdings"]), 2)

    def test_side_table_is_ignored(self):
        flows = self.snap["expected_cashflows"]
        self.assertEqual(len(flows), 3)
        self.assertEqual(flows[0]["date"], "2026-10-15")
        self.assertEqual(flows[0]["amount"], 180.0)
        self.assertEqual(flows[0]["tds"], 20.0)
        self.assertNotIn("Financial Year", json.dumps(self.snap))
        self.assertNotIn("999.0", json.dumps(self.snap))

    def test_every_financial_year_block_is_read(self):
        received = self.snap["received_cashflows"]
        self.assertEqual([r["date"] for r in received], ["2026-03-15", "2026-09-15"])
        self.assertEqual(received[0]["interest_gross"], 200.0)

    def test_percent_and_dash_formats(self):
        purchases = self.snap["purchases"]
        self.assertEqual(purchases[0]["xirr"], 12.0)
        self.assertEqual(purchases[1]["xirr"], 10.0)
        self.assertIsNone(purchases[0]["acquisition_cost"])
        self.assertEqual(purchases[0]["date"], "2026-01-01")

    def test_identity_preamble_never_copied(self):
        text = json.dumps(self.snap)
        for secret in ("Asha Example", "0000000000", "asha@example.com"):
            self.assertNotIn(secret, text)

    def test_empty_sell_sheet_gives_no_sells_and_no_warning(self):
        self.assertEqual(self.snap["sells"], [])
        self.assertEqual(self.snap["warnings"], [])

    def test_hash_is_stable_and_recorded(self):
        again = snapshot_of(sample_report())
        self.assertEqual(self.snap["snapshot_hash"], again["snapshot_hash"])
        self.assertEqual(len(self.snap["snapshot_hash"]), 64)
        self.assertEqual(self.snap["source"], {"report_sha256": "abc123"})


class TestFormatDrift(unittest.TestCase):
    def test_renamed_header_fails_and_names_it(self):
        sheets = sample_report()
        renamed = [h if h != "Current Value" else "Present Value" for h in HOLD_HEADERS]
        sheets["Holding Statement"] = [renamed if row == HOLD_HEADERS else row
                                       for row in sheets["Holding Statement"]]
        with self.assertRaises(ingest.IngestError) as ctx:
            snapshot_of(sheets)
        message = str(ctx.exception)
        self.assertIn("Holding Statement", message)
        self.assertIn("Current Value", message)
        self.assertIn("Present Value", message)

    def test_missing_required_sheet_fails_and_lists_sheets(self):
        sheets = sample_report()
        del sheets["Holding Statement"]
        with self.assertRaises(ingest.IngestError) as ctx:
            snapshot_of(sheets)
        self.assertIn("Holding Statement", str(ctx.exception))
        self.assertIn("Repayment Summary Report", str(ctx.exception))

    def test_unmapped_extra_column_warns(self):
        sheets = sample_report()
        sheets["Holding Statement"] = [row + ["Coupon"] if row == HOLD_HEADERS else row
                                       for row in sheets["Holding Statement"]]
        snap = snapshot_of(sheets)
        self.assertEqual(len(snap["holdings"]), 2)
        self.assertTrue(any("Coupon" in w for w in snap["warnings"]))

    def test_sell_sheet_with_data_but_no_map_warns(self):
        sheets = sample_report()
        sheets["Sell Summary Report"] = sheets["Sell Summary Report"] + [
            ["Date", "Name Of Bond", "ISIN", "Units", "Sell Value"],
            ["01/09/2026", "Alpha Finance", ALPHA, "1.0", "9900.0"]]
        snap = snapshot_of(sheets)
        self.assertEqual(snap["sells"], [])
        self.assertTrue(any("Sell Summary Report" in w for w in snap["warnings"]))

    def test_rows_without_an_isin_are_skipped_not_a_stop(self):
        sheets = sample_report()
        rows = sheets["Holding Statement"]
        first = rows.index(HOLD_HEADERS) + 1
        rows.insert(first + 1, ["Subtotal", "", "", "2.0"])
        rows.insert(-1, ["Total", "", "", "3.0"])
        snap = snapshot_of(sheets)
        self.assertEqual([h["isin"] for h in snap["holdings"]], [ALPHA, BETA])

    def test_unreadable_cell_names_sheet_and_field(self):
        sheets = sample_report()
        rows = sheets["Holding Statement"]
        rows[rows.index(HOLD_HEADERS) + 1][2] = "45567"
        with self.assertRaises(ingest.IngestError) as ctx:
            snapshot_of(sheets)
        self.assertIn("Holding Statement", str(ctx.exception))
        self.assertIn("maturity_date", str(ctx.exception))

    def test_required_sheet_with_no_table_is_an_error(self):
        sheets = sample_report()
        sheets["Holding Statement"] = [["", "Name Of Bond", "ISIN"], ["", "x", "y"]]
        with self.assertRaises(ingest.IngestError):
            snapshot_of(sheets)


class TestCli(unittest.TestCase):
    def test_reports_command_writes_a_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            report = os.path.join(root, "report.xlsx")
            make_xlsx(report, sample_report())
            code = ingest.main(["reports", "--file", report, "--root", root, "--date", "2026-10-02"])
            self.assertEqual(code, 0)
            out = os.path.join(root, "data", "skill-data", "snapshot-2026-10-02.json")
            snap = common.load_json(out)
            self.assertEqual({h["isin"] for h in snap["holdings"]}, {ALPHA, BETA})
            self.assertEqual(snap["source"]["report_sha256"], common.sha256_file(report))
            self.assertNotIn("report.xlsx", json.dumps(snap))



class TestFindingAndFailing(unittest.TestCase):
    def test_newest_report_in_data_wins(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "data"))
            old = os.path.join(root, "data", "wint-master-report-2026-09-01.xlsx")
            new = os.path.join(root, "data", "wint-master-report-2026-10-02.xlsx")
            for path, stamp in ((old, 1_000_000), (new, 2_000_000)):
                open(path, "w").close()
                os.utime(path, (stamp, stamp))
            self.assertEqual(ingest._find_report(root), new)
            os.utime(old, (3_000_000, 3_000_000))
            self.assertEqual(ingest._find_report(root), old)

    def test_nothing_in_data_says_where_to_put_it(self):
        with tempfile.TemporaryDirectory() as root:
            for find in (ingest._find_report, ingest._find_capture):
                with self.assertRaises(ingest.IngestError) as ctx:
                    find(root)
                self.assertIn("data/", str(ctx.exception))

    def test_newest_capture_in_data_wins(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "data"))
            old = os.path.join(root, "data", "wint-listings-2026-10-01T05-00-00-000Z.json")
            new = os.path.join(root, "data", "wint-listings-2026-10-02T05-00-00-000Z.json")
            for path, stamp in ((old, 1_000_000), (new, 2_000_000)):
                open(path, "w").close()
                os.utime(path, (stamp, stamp))
            self.assertEqual(ingest._find_capture(root), new)

    def test_missing_or_corrupt_file_is_an_error_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(ingest.main(["reports", "--file", os.path.join(root, "nope.xlsx"),
                                          "--root", root]), 1)
            bad = os.path.join(root, "bad.xlsx")
            with open(bad, "w") as fh:
                fh.write("not a workbook")
            self.assertEqual(ingest.main(["reports", "--file", bad, "--root", root]), 1)
            self.assertEqual(ingest.main(["listings", "--file", bad, "--root", root]), 1)

    def test_bad_date_argument_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            report = os.path.join(root, "report.xlsx")
            make_xlsx(report, sample_report())
            self.assertEqual(ingest.main(["reports", "--file", report, "--root", root,
                                          "--date", "today"]), 1)


if __name__ == "__main__":
    unittest.main()
