import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import rating_ledger  # noqa: E402


def entry(**over):
    args = dict(kind="holding", issuer="Alpha Finance", verdict="HOLD",
                reason="Rating reaffirmed; payments on time.",
                inputs={"ytm": 12.0, "rating": "A", "repayment_flag": None},
                sources=["https://example.com/rationale"], snapshot_hash="a" * 64,
                isin="INE000A07011", when="2026-10-02T10:00:00+00:00")
    args.update(over)
    return rating_ledger.make_entry(**args)


class TestMakeEntry(unittest.TestCase):
    def test_holding_entry_carries_hash_and_inputs(self):
        e = entry()
        self.assertEqual(e["verdict"], "HOLD")
        self.assertEqual(e["snapshot_hash"], "a" * 64)
        self.assertEqual(e["inputs"]["ytm"], 12.0)
        self.assertEqual(e["at"], "2026-10-02T10:00:00+00:00")

    def test_verdict_must_fit_the_kind(self):
        with self.assertRaises(ValueError):
            entry(verdict="ENTER")
        with self.assertRaises(ValueError):
            entry(kind="listing", verdict="HOLD", listings_sha256="b" * 64)
        with self.assertRaises(ValueError):
            entry(kind="rumour")

    def test_verdict_is_case_insensitive(self):
        self.assertEqual(entry(verdict="review")["verdict"], "REVIEW")

    def test_holding_needs_snapshot_hash_and_listing_needs_capture_hash(self):
        with self.assertRaises(ValueError):
            entry(snapshot_hash=None)
        with self.assertRaises(ValueError):
            entry(kind="listing", verdict="ENTER", listings_sha256=None)

    def test_enter_and_exit_need_a_source(self):
        with self.assertRaises(ValueError):
            entry(verdict="EXIT", sources=[])
        with self.assertRaises(ValueError):
            entry(kind="listing", verdict="ENTER", listings_sha256="b" * 64, sources=[])
        self.assertEqual(entry(sources=[])["sources"], [])  # HOLD may have none

    def test_reason_is_required(self):
        with self.assertRaises(ValueError):
            entry(reason="  ")


class TestAppendAndLoad(unittest.TestCase):
    def test_round_trip_keeps_order(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ratings-ledger.jsonl")
            self.assertEqual(rating_ledger.load(path), [])
            rating_ledger.append(path, entry())
            rating_ledger.append(path, entry(verdict="REVIEW", reason="Payment was short."))
            loaded = rating_ledger.load(path)
            self.assertEqual([e["verdict"] for e in loaded], ["HOLD", "REVIEW"])



class TestEnterGate(unittest.TestCase):
    def test_enter_needs_confirmed_security_and_seniority(self):
        for fact in (None, {"secured": None, "seniority": "senior"},
                     {"secured": True, "seniority": None}):
            with self.assertRaises(ValueError):
                rating_ledger.enter_gate(fact)
        rating_ledger.enter_gate({"secured": True, "seniority": "senior"})
        rating_ledger.enter_gate({"secured": False, "seniority": "subordinated"})


if __name__ == "__main__":
    unittest.main()
