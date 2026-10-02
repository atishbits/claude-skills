import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import diff_snapshots  # noqa: E402

CONFIG = common.load_config()


def item(key, issuer, **over):
    base = {"key": key, "issuer": issuer, "rating": "A", "ytm": 10.0, "sold_pct": 50.0,
            "units_left": None, "rating_action": None, "url": "https://www.wintwealth.com" + key}
    base.update(over)
    return base


def doc(*items):
    return {"captured_at": "2026-10-02T05:00:00.000Z", "listings": list(items)}


class TestDiffListings(unittest.TestCase):
    def test_new_gone_and_changed(self):
        prev = doc(item("/a-1", "Alpha Finance"), item("/b-2", "Beta Capital"))
        cur = doc(item("/a-1", "Alpha Finance", rating="A-", ytm=10.5),
                  item("/c-3", "Gamma Microfin"))
        diff = diff_snapshots.diff_listings(prev, cur, CONFIG)
        self.assertEqual([x["issuer"] for x in diff["new"]], ["Gamma Microfin"])
        self.assertEqual([x["issuer"] for x in diff["gone"]], ["Beta Capital"])
        self.assertEqual(diff["changed"], [{"issuer": "Alpha Finance", "key": "/a-1",
                                            "rating": ["A", "A-"], "ytm": [10.0, 10.5]}])

    def test_nearly_sold_by_percent_or_units(self):
        cur = doc(item("/a-1", "Alpha Finance", sold_pct=96.0),
                  item("/b-2", "Beta Capital", sold_pct=None, units_left=5),
                  item("/c-3", "Gamma Microfin", sold_pct=40.0))
        diff = diff_snapshots.diff_listings(None, cur, CONFIG)
        self.assertEqual([x["issuer"] for x in diff["nearly_sold"]],
                         ["Alpha Finance", "Beta Capital"])
        self.assertIn("no earlier", diff["note"])
        self.assertEqual(diff["new"], [])

    def test_rating_actions_are_surfaced(self):
        cur = doc(item("/a-1", "Alpha Finance", rating_action="downgrade"))
        diff = diff_snapshots.diff_listings(None, cur, CONFIG)
        self.assertEqual(diff["rating_actions"], [{"issuer": "Alpha Finance", "key": "/a-1",
                                                   "action": "downgrade", "rating": "A"}])


class TestDiffHoldings(unittest.TestCase):
    def test_new_closed_and_value_changes(self):
        prev = {"holdings": [{"issuer": "Alpha Finance", "isin": "INE000A07011",
                              "current_value": 20000.0},
                             {"issuer": "Beta Capital", "isin": "INE000B07022",
                              "current_value": 10000.0}]}
        cur = {"holdings": [{"issuer": "Alpha Finance", "isin": "INE000A07011",
                             "current_value": 20100.0},
                            {"issuer": "Gamma Microfin", "isin": "INE000C07033",
                             "current_value": 5000.0}]}
        diff = diff_snapshots.diff_holdings(prev, cur)
        self.assertEqual([h["issuer"] for h in diff["new"]], ["Gamma Microfin"])
        self.assertEqual([h["issuer"] for h in diff["closed"]], ["Beta Capital"])
        self.assertEqual(diff["value_changes"], [{"issuer": "Alpha Finance",
                                                  "isin": "INE000A07011",
                                                  "from": 20000.0, "to": 20100.0}])

    def test_no_previous_snapshot(self):
        diff = diff_snapshots.diff_holdings(None, {"holdings": []})
        self.assertEqual(diff["new"], [])
        self.assertIn("no earlier", diff["note"])


class TestHeldIssuerSignals(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"holdings": [{"issuer": "Alpha Finance", "isin": "INE000A07011",
                                       "current_value": 20000.0}]}
        self.facts = [{"isin": "INE000A07011", "wint_bond_id": None, "rating": "A"}]

    def test_listing_rating_differs_from_recorded(self):
        cur = doc(item("/a-9", "alpha finance", rating="A-"))
        signals = diff_snapshots.held_issuer_signals(cur, self.snapshot, self.facts)
        self.assertEqual(signals, [{"issuer": "Alpha Finance", "isin": "INE000A07011",
                                    "recorded_rating": "A", "listed_ratings": ["A-"],
                                    "rating_actions": [],
                                    "signal": "listing rating differs from the recorded rating"}])

    def test_rating_action_on_a_held_issuer(self):
        cur = doc(item("/a-9", "Alpha Finance", rating="A", rating_action="downgrade"))
        signals = diff_snapshots.held_issuer_signals(cur, self.snapshot, self.facts)
        self.assertEqual(signals[0]["rating_actions"], ["downgrade"])
        self.assertEqual(signals[0]["signal"], "rating action on a held issuer")

    def test_matching_rating_is_quiet(self):
        cur = doc(item("/a-9", "Alpha Finance", rating="A"))
        self.assertEqual(diff_snapshots.held_issuer_signals(cur, self.snapshot, self.facts), [])


if __name__ == "__main__":
    unittest.main()
