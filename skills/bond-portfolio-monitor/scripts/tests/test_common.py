import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402


class TestParsing(unittest.TestCase):
    def test_dates_in_both_report_formats(self):
        self.assertEqual(common.parse_date("20/09/2025"), "2025-09-20")
        self.assertEqual(common.parse_date("21-09-2026"), "2026-09-21")
        self.assertEqual(common.parse_date("2026-09-21"), "2026-09-21")

    def test_blank_and_dash_dates_are_none(self):
        self.assertIsNone(common.parse_date(""))
        self.assertIsNone(common.parse_date(" - "))

    def test_bad_date_raises(self):
        with self.assertRaises(ValueError):
            common.parse_date("soon")

    def test_numbers(self):
        self.assertEqual(common.parse_num("12.00%"), 12.0)
        self.assertEqual(common.parse_num("11.75"), 11.75)
        self.assertEqual(common.parse_num("2,26,106"), 226106.0)
        self.assertIsNone(common.parse_num("-"))
        self.assertIsNone(common.parse_num(""))

    def test_months_between(self):
        self.assertEqual(common.months_between("2026-01-01", "2027-01-01"), 12.0)


class TestProfile(unittest.TestCase):
    def test_template_is_a_valid_profile(self):
        template = common.load_json(os.path.join(common.SKILL_DIR, "profile-template.json"))
        self.assertEqual(common.validate_profile(template), template)

    def test_profile_missing_key_is_named(self):
        template = common.load_json(os.path.join(common.SKILL_DIR, "profile-template.json"))
        del template["min_rating"]
        with self.assertRaises(ValueError) as ctx:
            common.validate_profile(template)
        self.assertIn("min_rating", str(ctx.exception))

    def test_bad_values_are_named(self):
        template = common.load_json(os.path.join(common.SKILL_DIR, "profile-template.json"))
        for key, value in (("min_rating", "BBB +"), ("tax_slab_pct", "thirty"),
                           ("max_rating_bucket_share_pct", 40), ("allow_unsecured", "no"),
                           ("max_rating_bucket_share_pct", {"BBB": "forty"})):
            with self.assertRaises(ValueError) as ctx:
                common.validate_profile(dict(template, **{key: value}))
            self.assertIn(key, str(ctx.exception))

    def test_optional_keys_are_checked_when_present(self):
        template = common.load_json(os.path.join(common.SKILL_DIR, "profile-template.json"))
        self.assertTrue(common.validate_profile(dict(template, effective_tax_rate_pct=31.2,
                                                     total_investable=500000)))
        for key, value in (("effective_tax_rate_pct", "31%"), ("total_investable", 0),
                           ("total_investable", "lots")):
            with self.assertRaises(ValueError) as ctx:
                common.validate_profile(dict(template, **{key: value}))
            self.assertIn(key, str(ctx.exception))

    def test_missing_profile_points_at_template(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(FileNotFoundError) as ctx:
                common.load_profile(root)
            self.assertIn("profile-template.json", str(ctx.exception))


class TestFilesAndConfig(unittest.TestCase):
    def test_dated_files_sorted_oldest_first(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("snapshot-2026-10-02.json", "snapshot-2026-09-01.json", "other.json"):
                open(os.path.join(d, name), "w").close()
            names = [os.path.basename(p) for p in common.dated_files(d, "snapshot-")]
            self.assertEqual(names, ["snapshot-2026-09-01.json", "snapshot-2026-10-02.json"])

    def test_stale_config_entry_is_named(self):
        config = {"config_max_age_months": 12,
                  "tax": {"interest": {"treatment": "slab", "as_of": "2024-01-01"}},
                  "portal": {"fee": {"value": 1, "as_of": "2026-09-01"}}}
        warnings = common.stale_config_warnings(config, "2026-10-02")
        self.assertEqual(len(warnings), 1)
        self.assertIn("tax.interest", warnings[0])
        self.assertIn("2024-01-01", warnings[0])

    def test_shipped_config_is_fresh_and_loads(self):
        config = common.load_config()
        self.assertEqual(common.stale_config_warnings(config, "2026-10-02"), [])
        self.assertIn("holdings", config["report_columns"])

    def test_canonical_is_key_order_independent(self):
        self.assertEqual(common.canonical({"b": 1, "a": 2}), common.canonical({"a": 2, "b": 1}))


if __name__ == "__main__":
    unittest.main()
