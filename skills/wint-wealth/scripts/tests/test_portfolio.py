import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import ingest  # noqa: E402
import portfolio  # noqa: E402
from helpers import ALPHA, sample_report  # noqa: E402

PROFILE = common.load_json(os.path.join(common.SKILL_DIR, "profile-template.json"))
FACTS = [{"isin": ALPHA, "wint_bond_id": None, "issuer": "Alpha Finance", "rating": "BBB+"}]


def snapshot():
    return ingest.build_snapshot(sample_report(), common.load_config(), "2026-10-02", "abc")


class TestBuckets(unittest.TestCase):
    def test_rating_bucket(self):
        self.assertEqual(portfolio.rating_bucket("BBB+"), "BBB")
        self.assertEqual(portfolio.rating_bucket("AA-"), "AA")
        self.assertEqual(portfolio.rating_bucket("AAA"), "AAA")
        self.assertEqual(portfolio.rating_bucket(None), "unrated")

    def test_tenure_bucket(self):
        self.assertEqual(portfolio.tenure_bucket(8.9), "under 12m")
        self.assertEqual(portfolio.tenure_bucket(12.0), "12-24m")
        self.assertEqual(portfolio.tenure_bucket(30), "24-36m")
        self.assertEqual(portfolio.tenure_bucket(40), "over 36m")
        self.assertEqual(portfolio.tenure_bucket(None), "unknown")


class TestSummarise(unittest.TestCase):
    def setUp(self):
        self.summary = portfolio.summarise(snapshot(), FACTS, PROFILE)

    def test_totals(self):
        totals = self.summary["totals"]
        self.assertEqual(totals["current_value"], 30000.0)
        self.assertEqual(totals["invested"], 30000.0)
        self.assertEqual(totals["interest_net_received"], 360.0)
        self.assertEqual(totals["tds"], 40.0)
        # (20000 * 12 + 10000 * 10) / 30000
        self.assertEqual(totals["weighted_ytm"], 11.33)

    def test_shares(self):
        self.assertEqual(self.summary["by_issuer"]["Alpha Finance"]["share_pct"], 66.67)
        self.assertEqual(self.summary["by_rating_bucket"]["BBB"]["share_pct"], 66.67)
        self.assertEqual(self.summary["by_rating_bucket"]["unrated"]["share_pct"], 33.33)
        self.assertEqual(self.summary["by_tenure"]["under 12m"]["value"], 10000.0)
        self.assertEqual(self.summary["by_tenure"]["12-24m"]["value"], 20000.0)

    def test_breaches_name_the_limit(self):
        breaches = self.summary["breaches"]
        self.assertTrue(any("Alpha Finance" in b and "15" in b for b in breaches))
        self.assertTrue(any("Beta Capital" in b for b in breaches))
        self.assertTrue(any("BBB" in b and "40" in b for b in breaches))

    def test_unrated_holdings_are_listed_not_assumed_safe(self):
        self.assertEqual(self.summary["unrated"], ["Beta Capital"])

    def test_zero_value_holding_is_excluded(self):
        snap = snapshot()
        snap["holdings"].append(dict(snap["holdings"][0], issuer="Gamma Microfin",
                                     isin="INE000C07033", current_value=None))
        snap["holdings"].append(dict(snap["holdings"][0], issuer="Delta Credit",
                                     isin="INE000D07044", current_value=0.0))
        summary = portfolio.summarise(snap, FACTS, PROFILE)
        self.assertEqual(len(summary["positions"]), 2)
        self.assertEqual(summary["totals"]["current_value"], 30000.0)

    def test_empty_portfolio(self):
        snap = snapshot()
        snap["holdings"] = []
        summary = portfolio.summarise(snap, [], PROFILE)
        self.assertEqual(summary["totals"]["current_value"], 0)
        self.assertIsNone(summary["totals"]["weighted_ytm"])
        self.assertEqual(summary["positions"], [])
        self.assertEqual(summary["breaches"], [])

    def test_markdown_has_totals_positions_and_breaches(self):
        text = portfolio.render_markdown(self.summary)
        self.assertIn("# Wint Wealth portfolio", text)
        self.assertIn("2026-10-02", text)
        self.assertIn("Alpha Finance", text)
        self.assertIn("11.33", text)
        self.assertIn("## Limit breaches", text)
        self.assertIn("## Unrated", text)


if __name__ == "__main__":
    unittest.main()
