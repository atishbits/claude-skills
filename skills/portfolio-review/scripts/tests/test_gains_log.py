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
        old = {"kind": "sale", "id": "x", "ticker": "STOCKA", "account": "b", "sell_date": "2026-10-19",
               "qty": 5, "stcg": 0.0, "ltcg": 777.0, "status": "unconfirmed"}  # on as_of: excluded
        run = gains_log.fy_running("2026-27", gains_log.read_entries() + [old], self.snap)
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
        self.assertEqual(set(doc["sales"][0]), {"date", "ticker", "account", "qty", "stcg", "ltcg", "status", "in_baseline"})
        self.assertIn("exempt_left", doc["totals"])


class TestFixes(Base):
    def test_charges_split_pro_rata(self):
        snap = snapshot()
        snap["stocks"][0]["lots"] = [{"broker": "a", "date": "2020-01-01", "qty": 10, "cost": 100},
                                     {"broker": "a", "date": "2026-09-01", "qty": 30, "cost": 100}]
        r = gains_log.record("STOCKA", 40, 150, "2026-10-21", "a", snapshot=snap, entries=[])
        self.assertEqual((r["ltcg"], r["stcg"]), (500.0, 1500.0))
        r = gains_log.record("STOCKA", 40, 150, "2026-10-22", "a", charges=100, snapshot=snap, entries=[])
        self.assertAlmostEqual(r["ltcg"], 475.0)
        self.assertAlmostEqual(r["stcg"], 1425.0)
        self.assertAlmostEqual(r["est_tax"], 0.125 * 475 + 0.2 * 1425)

    def test_export_marks_baseline_sales(self):
        old = {"kind": "sale", "id": "x", "ticker": "STOCKA", "account": "b", "sell_date": "2026-10-19",
               "qty": 5, "stcg": 0.0, "ltcg": 777.0, "status": "unconfirmed"}
        new = dict(old, id="y", sell_date="2026-10-20")
        gains_log.logdir.append(gains_log.LOG_DIR, old, self.tmp.name, "2026-10-19")
        gains_log.logdir.append(gains_log.LOG_DIR, new, self.tmp.name, "2026-10-20")
        with open(os.path.join(self.sd, "snapshot-2026-10-19.json"), "w") as fh:
            json.dump(self.snap, fh)
        with open(gains_log.export("2026-27")) as fh:
            flags = {x["date"]: x["in_baseline"] for x in json.load(fh)["sales"]}
        self.assertEqual(flags, {"2026-10-19": True, "2026-10-20": False})

    def test_report_marks_baseline_sales(self):
        import io
        from contextlib import redirect_stdout
        old = {"kind": "sale", "id": "x", "ticker": "STOCKA", "account": "b", "sell_date": "2026-10-19",
               "qty": 5, "price": 150, "stcg": 0.0, "ltcg": 777.0, "status": "unconfirmed"}
        new = dict(old, id="y", sell_date="2026-10-20", ticker="STOCKB")
        gains_log.logdir.append(gains_log.LOG_DIR, old, self.tmp.name, "2026-10-19")
        gains_log.logdir.append(gains_log.LOG_DIR, new, self.tmp.name, "2026-10-20")
        with open(os.path.join(self.sd, "snapshot-2026-10-19.json"), "w") as fh:
            json.dump(self.snap, fh)
        buf = io.StringIO()
        with redirect_stdout(buf):
            gains_log._report("2026-27")
        lines = buf.getvalue().splitlines()
        first = next(x for x in lines if "2026-10-19 STOCKA" in x)
        second = next(x for x in lines if "2026-10-20 STOCKB" in x)
        self.assertIn("(in broker baseline, not added)", first)
        self.assertNotIn("(in broker baseline, not added)", second)

    def test_sale_on_or_before_export_rejected(self):
        with self.assertRaises(ValueError) as cm:
            gains_log.record("STOCKA", 1, 150, "2026-10-19", "a", snapshot=self.snap)
        self.assertIn("already in the export", str(cm.exception))

    def test_account_without_lots(self):
        with self.assertRaises(ValueError):
            gains_log.record("STOCKA", 1, 150, "2026-10-20", "zzz", snapshot=self.snap)


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


HEADER = "account,symbol,sell_date,qty,sell_price,buy_date,buy_price,gain,term,charges\n"


class TestReconcile(Base):
    def csv(self, rows):
        path = os.path.join(self.tmp.name, "tax.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(HEADER + "".join(rows))
        return path

    def test_read_groups_sales(self):
        path = self.csv(["a,STOCKA,2026-10-20,6,150,2026-01-15,100,300,ST,5\n",
                         "a,STOCKA,2026-10-20,4,150,2020-01-01,50,400,LT,3\n"])
        sales = gains_log.read_broker_csv(path)
        self.assertEqual(len(sales), 1)
        self.assertEqual((sales[0]["qty"], sales[0]["stcg"], sales[0]["ltcg"], sales[0]["charges"]),
                         (10, 300, 400, 8))

    def test_logged_sale_confirmed_once_totals_unchanged(self):
        rec = gains_log.record("STOCKA", 10, 150, "2026-10-20", "a", snapshot=self.snap)
        before = gains_log.fy_running("2026-27", snapshot=self.snap)
        path = self.csv(["a,STOCKA,2026-10-20,10,150,2026-01-15,100,495,ST,5\n"])
        res = gains_log.reconcile(path)
        self.assertEqual(res["confirmed"], [rec["id"]])
        self.assertEqual(res["imported"], [])
        folded = gains_log.fold(gains_log.read_entries())
        self.assertEqual(len(folded), 1)
        self.assertEqual(folded[0]["status"], "confirmed")
        self.assertEqual(folded[0]["stcg"], 495)
        after = gains_log.fy_running("2026-27", snapshot=self.snap)
        self.assertAlmostEqual(after["stcg"] - before["stcg"], 495 - rec["stcg"])
        self.assertEqual(after["unconfirmed"], 0)

    def test_unlogged_sale_imported(self):
        path = self.csv(["a,STOCKA,2026-10-21,5,150,2026-01-15,100,200,ST,2\n"])
        res = gains_log.reconcile(path)
        self.assertEqual(len(res["imported"]), 1)
        s = gains_log.fold(gains_log.read_entries())[0]
        self.assertEqual((s["source"], s["status"], s["ticker"], s["stcg"]), ("broker", "confirmed", "STOCKA", 200))
        self.assertEqual(gains_log.fy_running("2026-27", snapshot=self.snap)["stcg"], 1200)

    def test_imported_pre_baseline_sale_not_double_counted(self):
        before = gains_log.fy_running("2026-27", snapshot=self.snap)
        path = self.csv(["a,STOCKA,2026-10-01,5,150,2026-01-15,100,200,ST,2\n"])
        self.assertEqual(len(gains_log.reconcile(path)["imported"]), 1)
        after = gains_log.fy_running("2026-27", snapshot=self.snap)
        self.assertEqual((after["stcg"], after["ltcg"]), (before["stcg"], before["ltcg"]))

    def test_qty_mismatch_listed_not_confirmed(self):
        rec = gains_log.record("STOCKA", 10, 150, "2026-10-20", "a", snapshot=self.snap)
        path = self.csv(["a,STOCKA,2026-10-20,8,150,2026-01-15,100,300,ST,5\n"])
        res = gains_log.reconcile(path)
        self.assertEqual(res["confirmed"], [])
        self.assertEqual(res["imported"], [])
        self.assertEqual(res["mismatched"][0]["id"], rec["id"])
        self.assertEqual(res["mismatched"][0]["field"], "qty")
        self.assertEqual(gains_log.fold(gains_log.read_entries())[0]["status"], "unconfirmed")

    def test_gain_mismatch_listed(self):
        rec = gains_log.record("STOCKA", 10, 150, "2026-10-20", "a", snapshot=self.snap)
        path = self.csv(["a,STOCKA,2026-10-20,10,150,2026-01-15,100,300,ST,5\n"])
        res = gains_log.reconcile(path)
        self.assertEqual(res["mismatched"][0]["field"], "gain")
        self.assertEqual(res["confirmed"], [])
        self.assertEqual(rec["stcg"], 500)

    def test_rerun_idempotent(self):
        gains_log.record("STOCKA", 10, 150, "2026-10-20", "a", snapshot=self.snap)
        path = self.csv(["a,STOCKA,2026-10-20,10,150,2026-01-15,100,500,ST,0\n",
                         "a,STOCKA,2026-10-22,2,150,2026-01-15,100,60,ST,0\n"])
        gains_log.reconcile(path)
        n = len(gains_log.read_entries())
        res = gains_log.reconcile(path)
        self.assertEqual((res["confirmed"], res["imported"], res["mismatched"]), ([], [], []))
        self.assertEqual(len(gains_log.read_entries()), n)
