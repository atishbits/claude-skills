import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import bond_facts  # noqa: E402


class TestBondFacts(unittest.TestCase):
    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(bond_facts.load(os.path.join(d, "bond-facts.json")), [])

    def test_upsert_then_lookup_by_isin_and_bond_id(self):
        facts = []
        bond_facts.upsert(facts, isin="INE000A07011", bond_id="101", issuer="Alpha Finance",
                          rating="A", agency="Example Ratings", secured=True, listed=True,
                          source="https://example.com/rationale", as_of="2026-10-02")
        self.assertEqual(bond_facts.lookup(facts, isin="INE000A07011")["rating"], "A")
        self.assertEqual(bond_facts.lookup(facts, bond_id="101")["issuer"], "Alpha Finance")
        self.assertIsNone(bond_facts.lookup(facts, isin="INE000B07022"))

    def test_upsert_updates_in_place_and_keeps_other_fields(self):
        facts = []
        bond_facts.upsert(facts, isin="INE000A07011", rating="A", secured=True,
                          source="https://example.com/1", as_of="2026-09-01")
        bond_facts.upsert(facts, isin="INE000A07011", rating="A-", rating_action="downgrade",
                          source="https://example.com/2", as_of="2026-10-02")
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["rating"], "A-")
        self.assertIs(facts[0]["secured"], True)
        self.assertEqual(facts[0]["as_of"], "2026-10-02")

    def test_source_and_date_are_required(self):
        with self.assertRaises(ValueError):
            bond_facts.upsert([], isin="INE000A07011", rating="A", as_of="2026-10-02")
        with self.assertRaises(ValueError):
            bond_facts.upsert([], rating="A", source="https://example.com", as_of="2026-10-02")

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(ValueError):
            bond_facts.upsert([], isin="INE000A07011", colour="blue",
                              source="https://example.com", as_of="2026-10-02")

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bond-facts.json")
            facts = []
            bond_facts.upsert(facts, isin="INE000A07011", rating="A",
                              source="https://example.com", as_of="2026-10-02")
            bond_facts.save(path, facts)
            self.assertEqual(bond_facts.load(path), facts)


if __name__ == "__main__":
    unittest.main()
