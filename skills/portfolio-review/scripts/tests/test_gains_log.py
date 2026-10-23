import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gains_log  # noqa: E402
import sell_signals  # noqa: E402
import tax_lots  # noqa: E402


def snapshot(fy="FY 2026-27"):
    return {"holdings_date": "2026-10-19",
            "tax_position": {"fy": fy, "realised_stcg": 1000.0, "realised_ltcg": 5000.0},
            "stocks": [{"ticker": "STOCKA", "avg_cost": 100, "lots": [
                {"broker": "a", "date": "2026-01-15", "qty": 10, "cost": 100},
                {"broker": "a", "date": "2026-03-15", "qty": 10, "cost": 120},
                {"broker": "b", "date": "2020-01-01", "qty": 10, "cost": 50}]}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        sd = os.path.join(self.tmp.name, "data", "skill-data")
        os.makedirs(sd)
        self.sd = sd
        for target, name, val in ((gains_log, "ROOT", self.tmp.name), (gains_log, "SKILL_DATA_DIR", sd),
                                  (gains_log, "LOG_DIR", os.path.join(sd, "realised-gains")),
                                  (tax_lots, "SKILL_DATA_DIR", sd)):
            p = mock.patch.object(target, name, val)
            p.start()
            self.addCleanup(p.stop)
        self.snap = snapshot()


class TestGainsLog(Base):
    def test_fy_of(self):
        self.assertEqual(gains_log.fy_of(date(2027, 3, 31)), "2026-27")
        self.assertEqual(gains_log.fy_of(date(2027, 4, 1)), "2027-28")

    def test_second_record_continues_fifo(self):
        r1 = gains_log.record("STOCKA", 10, 150, "2026-10-20", "a", snapshot=self.snap)
        r2 = gains_log.record("stocka", 5, 150, "2026-10-21", "a", snapshot=self.snap)
        self.assertEqual(r1["lots"][0]["cost"], 100)
        self.assertEqual(r2["lots"][0]["cost"], 120)
        self.assertEqual(r1["status"], "unconfirmed")
        self.assertNotEqual(r1["id"], r2["id"])
        with self.assertRaises(ValueError):
            gains_log.record("STOCKA", 6, 150, "2026-10-22", "a", snapshot=self.snap)

    def test_ids_unique_same_day(self):
        r1 = gains_log.record("STOCKA", 2, 150, "2026-10-20", "a", snapshot=self.snap)
        r2 = gains_log.record("STOCKA", 2, 150, "2026-10-20", "a", snapshot=self.snap)
        self.assertNotEqual(r1["id"], r2["id"])

    def test_fy_running_baseline_plus_later_sales(self):
        gains_log.record("STOCKA", 10, 150, "2026-10-20", "a", snapshot=self.snap)   # STCG 500
        gains_log.record("STOCKA", 5, 150, "2026-10-19", "b", snapshot=self.snap)    # on as_of: excluded
        run = gains_log.fy_running("2026-27", snapshot=self.snap)
        self.assertEqual(run["baseline"]["as_of"], "2026-10-19")
        self.assertEqual(run["stcg"], 1500.0)
        self.assertEqual(run["ltcg"], 5000.0)
        self.assertEqual(run["unconfirmed"], 1)
        self.assertEqual(run["fy_tax"]["exempt_left"], tax_lots.LTCG_EXEMPTION_PER_FY - 5000)

    def test_other_fy_baseline_ignored(self):
        snap = snapshot("FY 2025-26")
        gains_log.record("STOCKA", 10, 150, "2026-10-20", "a", snapshot=snap)
        run = gains_log.fy_running("2026-27", snapshot=snap)
        self.assertIsNone(run["baseline"])
        self.assertEqual((run["stcg"], run["ltcg"]), (500.0, 0.0))

    def test_confirm_folds(self):
        r = gains_log.record("STOCKA", 2, 150, "2026-10-20", "a", snapshot=self.snap)
        entries = gains_log.read_entries() + [{"kind": "confirm", "ref": r["id"]}]
        self.assertEqual(gains_log.fold(entries)[0]["status"], "confirmed")
        self.assertEqual(gains_log.fy_running("2026-27", entries, self.snap)["unconfirmed"], 0)

    def test_export(self):
        gains_log.record("STOCKA", 10, 150, "2026-10-20", "a", snapshot=self.snap)
        with open(os.path.join(self.sd, "snapshot-2026-10-19.json"), "w") as fh:
            json.dump(self.snap, fh)
        path = gains_log.export("2026-27")
        self.assertEqual(os.path.basename(path), "realised-gains-FY2026-27.json")
        with open(path) as fh:
            doc = json.load(fh)
        self.assertEqual(set(doc), {"fy", "generated_at", "baseline", "sales", "totals"})
        self.assertIn("mutual funds", doc["baseline"]["note"])
        self.assertEqual(set(doc["sales"][0]), {"date", "ticker", "account", "qty", "stcg", "ltcg", "status"})
        self.assertIn("exempt_left", doc["totals"])


class TestSellSignalsWiring(Base):
    def test_headroom_and_sold_since_read_the_log(self):
        with open(os.path.join(self.sd, "snapshot-2026-10-19.json"), "w") as fh:
            json.dump(self.snap, fh)
        gains_log.record("STOCKA", 4, 150, "2026-10-20", "a", snapshot=self.snap)
        headroom, note = sell_signals.lt_headroom(date(2026, 10, 23))
        self.assertEqual(headroom, tax_lots.LTCG_EXEMPTION_PER_FY - 5000)
        self.assertIsNone(note)
        self.assertEqual(sell_signals.sold_since("STOCKA", "2026-10-20"), 4)
        self.assertEqual(sell_signals.sold_since("STOCKA", "2026-10-21"), 0)


if __name__ == "__main__":
    unittest.main()
