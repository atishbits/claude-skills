import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import tax_profile  # noqa: E402

PERSON = {"fd_interest_rate": 0.07, "fd_tax_pct": 0.20, "savings_interest_rate": 0.03,
          "other_tax_pct": 0.30, "surcharge_multiplier": 1.10}


class TestEffectiveRates(unittest.TestCase):
    def test_slab_times_surcharge_times_cess(self):
        rates = tax_profile.effective_rates(PERSON, 1.04)
        self.assertEqual(rates, {"tax_slab_pct": 30.0, "effective_tax_rate_pct": 34.32,
                                 "tax_multiplier": 1.144})

    def test_no_surcharge(self):
        rates = tax_profile.effective_rates(dict(PERSON, surcharge_multiplier=1.0), 1.04)
        self.assertEqual(rates["effective_tax_rate_pct"], 31.2)

    def test_missing_rate_is_named(self):
        with self.assertRaises(ValueError) as ctx:
            tax_profile.effective_rates({"surcharge_multiplier": 1.0}, 1.04)
        self.assertIn("other_tax_pct", str(ctx.exception))


class TestApply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "data"))
        self.profile_path = os.path.join(self.root, "data", "profile.json")
        common.write_json(self.profile_path, common.load_json(
            os.path.join(common.SKILL_DIR, "profile-template.json")))
        self.tax_path = os.path.join(self.root, "tax-profile.json")
        common.write_json(self.tax_path, {"people": {"asha": PERSON}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_the_rates_and_where_they_came_from(self):
        code = tax_profile.main(["--tax-profile", self.tax_path, "--person", "asha", "--cess", "1.04",
                                 "--root", self.root, "--write"])
        self.assertEqual(code, 0)
        profile = common.load_profile(self.root)
        self.assertEqual(profile["effective_tax_rate_pct"], 34.32)
        self.assertEqual(profile["tax_multiplier"], 1.144)
        self.assertEqual(profile["tax_slab_pct"], 30.0)
        self.assertIn("asha", profile["tax_rates_from"])
        self.assertEqual(profile["min_rating"], "BBB+")  # nothing else is touched

    def test_without_write_nothing_changes(self):
        before = open(self.profile_path).read()
        self.assertEqual(tax_profile.main(["--tax-profile", self.tax_path, "--person", "asha",
                                           "--cess", "1.04", "--root", self.root]), 0)
        self.assertEqual(open(self.profile_path).read(), before)

    def test_unknown_person_lists_who_is_there(self):
        self.assertEqual(tax_profile.main(["--tax-profile", self.tax_path, "--person", "nobody",
                                           "--cess", "1.04", "--root", self.root]), 1)


if __name__ == "__main__":
    unittest.main()
