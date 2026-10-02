import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import ingest  # noqa: E402


def row(**over):
    base = {"href": "/bonds/listing/Alpha-Finance-101?productTenureId=77", "issuer": "Alpha Finance",
            "rating": "BBB+", "min": "Min. ₹10k", "sold": "96% Sold", "ytm_label": "YTM",
            "ytm": "11.75%", "ytm_alt": "", "maturity_left": "17 months", "interest": "Monthly",
            "principal": "At Maturity", "tags": []}
    base.update(over)
    return base


def capture(rows, **over):
    doc = {"schema": 1, "captured_at": "2026-10-02T05:53:38.583Z", "source": "/bonds/listing/",
           "stated_live_count": len(rows), "sha256": ingest.rows_checksum(rows), "rows": rows}
    doc.update(over)
    return doc


class TestChecksum(unittest.TestCase):
    def test_matches_the_browser_serialisation(self):
        # JSON.stringify output for this row, hashed by the browser snippet.
        rows = [{"href": "/x-1", "min": "Min. ₹10k", "tags": ["A B"]}]
        text = '[{"href":"/x-1","min":"Min. ₹10k","tags":["A B"]}]'
        self.assertEqual(ingest.rows_checksum(rows), common.sha256_text(text))

    def test_altered_row_is_rejected(self):
        doc = capture([row()])
        doc["rows"][0]["ytm"] = "12.75%"
        with self.assertRaises(ingest.IngestError) as ctx:
            ingest.verify_capture(doc)
        self.assertIn("checksum", str(ctx.exception))

    def test_missing_top_level_key_is_rejected(self):
        doc = capture([row()])
        del doc["captured_at"]
        with self.assertRaises(ingest.IngestError):
            ingest.verify_capture(doc)

    def test_extra_field_is_rejected(self):
        rows = [dict(row(), email="someone@example.com")]
        with self.assertRaises(ingest.IngestError) as ctx:
            ingest.verify_capture(capture(rows))
        self.assertIn("email", str(ctx.exception))


class TestNormalise(unittest.TestCase):
    def test_plain_card(self):
        item, warnings = ingest.normalise_listing(row())
        self.assertEqual(warnings, [])
        self.assertEqual(item["key"], "/bonds/listing/Alpha-Finance-101?productTenureId=77")
        self.assertEqual(item["bond_id"], "101")
        self.assertEqual(item["tenure_id"], "77")
        self.assertEqual(item["url"],
                         "https://www.wintwealth.com/bonds/listing/Alpha-Finance-101?productTenureId=77")
        self.assertEqual(item["min_investment"], 10000)
        self.assertEqual(item["sold_pct"], 96.0)
        self.assertIsNone(item["units_left"])
        self.assertEqual(item["ytm"], 11.75)
        self.assertFalse(item["ytm_is_upper_bound"])
        self.assertEqual(item["tenure_months"], 17.0)
        self.assertIsNone(item["secured"])
        self.assertIsNone(item["seniority"])
        self.assertFalse(item["held"])

    def test_money_units(self):
        for text, rupees in (("Min. ₹1 lakh", 100000), ("Min. ₹1k", 1000), ("Min. ₹25k", 25000),
                             ("Min. ₹2.5 lakh", 250000)):
            self.assertEqual(ingest.normalise_listing(row(min=text))[0]["min_investment"], rupees)

    def test_units_left_days_and_upper_bound(self):
        item, _ = ingest.normalise_listing(row(sold="5 units left", maturity_left="90 days",
                                               ytm_label="YTM up to", ytm="11%", ytm_alt="10.75%",
                                               href="/bonds/listing/Beta-Capital-202"))
        self.assertEqual(item["units_left"], 5)
        self.assertIsNone(item["sold_pct"])
        self.assertEqual(item["tenure_months"], 3.0)
        self.assertTrue(item["ytm_is_upper_bound"])
        self.assertEqual(item["ytm_alt"], 10.75)
        self.assertIsNone(item["tenure_id"])

    def test_tags_become_flags(self):
        item, _ = ingest.normalise_listing(row(
            rating="AA (CE)",
            tags=["SUB DEBT", "UNSECURED", "GOLD-LOAN BACKED", "GOVT. GUARANTEED",
                  "RATING UPGRADED: A+", "₹10k Invested"]))
        self.assertEqual(item["rating"], "AA")
        self.assertEqual(item["rating_raw"], "AA (CE)")
        self.assertEqual(item["seniority"], "subordinated")
        self.assertIs(item["secured"], False)
        self.assertEqual(item["collateral"], "GOLD-LOAN BACKED")
        self.assertEqual(item["guarantee"], "GOVT. GUARANTEED")
        self.assertEqual(item["rating_action"], "upgrade")
        self.assertTrue(item["held"])

    def test_unparseable_fields_become_null_with_warning(self):
        item, warnings = ingest.normalise_listing(row(min="Min. call us", ytm="", sold="",
                                                      maturity_left="a while"))
        self.assertIsNone(item["min_investment"])
        self.assertIsNone(item["ytm"])
        self.assertIsNone(item["tenure_months"])
        self.assertIsNone(item["sold_pct"])
        self.assertEqual(len(warnings), 3)
        self.assertTrue(all("Alpha Finance" in w for w in warnings))

    def test_years_tenure(self):
        self.assertEqual(ingest.normalise_listing(row(maturity_left="3 years"))[0]["tenure_months"],
                         36.0)


class TestBuildAndCli(unittest.TestCase):
    def test_small_count_mismatch_warns(self):
        rows = [row(href=f"/bonds/listing/Alpha-Finance-{i}") for i in range(97)]
        doc = ingest.build_listings(capture(rows, stated_live_count=100))
        self.assertEqual(len(doc["listings"]), 97)
        self.assertTrue(any("100" in w for w in doc["warnings"]))

    def test_partial_capture_fails_unless_allowed(self):
        rows = [row(href=f"/bonds/listing/Alpha-Finance-{i}") for i in range(60)]
        raw = capture(rows, stated_live_count=100)
        with self.assertRaises(ingest.IngestError) as ctx:
            ingest.build_listings(raw)
        self.assertIn("60", str(ctx.exception))
        self.assertIn("100", str(ctx.exception))
        doc = ingest.build_listings(raw, allow_partial=True)
        self.assertEqual(len(doc["listings"]), 60)
        self.assertTrue(doc["partial"])

    def test_no_checksum_marks_unverified(self):
        raw = capture([row()], sha256="")
        doc = ingest.build_listings(raw, check_sum=False)
        self.assertFalse(doc["verified"])

    def test_template_ingests_with_no_checksum(self):
        template = common.load_json(os.path.join(common.SKILL_DIR, "listings-template.json"))
        doc = ingest.build_listings(template, check_sum=False)
        self.assertEqual(doc["listings"][0]["issuer"], "Alpha Finance")

    def test_cli_writes_a_dated_file(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "wint-listings-x.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(capture([row()]), fh, ensure_ascii=False)
            self.assertEqual(ingest.main(["listings", "--file", path, "--root", root]), 0)
            out = os.path.join(root, "data", "skill-data", "listings-20261002T0553.json")
            self.assertEqual(common.load_json(out)["listings"][0]["bond_id"], "101")

    def test_cli_rejects_a_tampered_file(self):
        with tempfile.TemporaryDirectory() as root:
            doc = capture([row()])
            doc["rows"][0]["rating"] = "AAA"
            path = os.path.join(root, "wint-listings-x.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False)
            self.assertEqual(ingest.main(["listings", "--file", path, "--root", root]), 1)



class TestReviewFindings(unittest.TestCase):
    def test_unknown_money_suffix_is_null_not_a_guess(self):
        for text in ("Min. ₹1L", "Min. ₹1 Lac", "Min. ₹10 thousand", "Min. ₹1.2.3"):
            item, warnings = ingest.normalise_listing(row(min=text))
            self.assertIsNone(item["min_investment"], text)
            self.assertTrue(any("min_investment" in w for w in warnings), text)

    def test_wrong_value_types_are_rejected_by_name(self):
        for field, value in (("sold", None), ("ytm", 10), ("tags", None), ("tags", [1])):
            rows = [row(**{field: value})]
            with self.assertRaises(ingest.IngestError) as ctx:
                ingest.verify_capture(capture(rows), check_sum=False)
            self.assertIn(field, str(ctx.exception))

    def test_unsecured_tag_with_extra_words(self):
        item, _ = ingest.normalise_listing(row(tags=["UNSECURED NCD"]))
        self.assertIs(item["secured"], False)


if __name__ == "__main__":
    unittest.main()
