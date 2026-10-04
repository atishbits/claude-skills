import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import compute_advance_tax as cat  # noqa: E402

# Invented rates: nobody's slab.
PERSON = {"fd_interest_rate": 0.10, "fd_tax_pct": 0.20, "savings_interest_rate": 0.05,
          "other_tax_pct": 0.30, "surcharge_multiplier": 1.10,
          "house_rent_standard_deduction_pct": 0.30, "cess_multiplier": 1.04}


class TestCompute(unittest.TestCase):
    def test_each_bucket_and_the_gross_up(self):
        out = cat.compute(PERSON, 1000000, 200000, 10000, 100000)
        self.assertAlmostEqual(out["fd_tax"], 20000.0)
        self.assertAlmostEqual(out["savings_tax"], 3000.0)
        self.assertAlmostEqual(out["dividend_tax"], 3000.0)
        self.assertAlmostEqual(out["house_rent_taxable"], 70000.0)
        self.assertAlmostEqual(out["house_rent_tax"], 21000.0)
        self.assertAlmostEqual(out["bond_tax"], 0.0)
        self.assertAlmostEqual(out["pre_surcharge_tax"], 47000.0)
        self.assertAlmostEqual(out["estimated_annual_tax"], 47000.0 * 1.10 * 1.04)

    def test_bond_interest_is_taxed_at_slab_and_its_tds_comes_off_after_the_gross_up(self):
        out = cat.compute(PERSON, 0, 0, 0, 0, bond_interest_total=10000, bond_tds=1000)
        self.assertAlmostEqual(out["bond_tax"], 3000.0)
        self.assertAlmostEqual(out["estimated_annual_tax"], 3000.0 * 1.10 * 1.04 - 1000.0)

    def test_bond_figures_are_read_from_a_fy_interest_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bond-interest.json")
            with open(path, "w") as f:
                json.dump({"total": {"interest_gross": 850.0, "tds": 60.0}}, f)
            self.assertEqual(cat.load_bond_interest(path), (850.0, 60.0))


class TestSchedule(unittest.TestCase):
    def test_installments_map_to_cumulative_shares(self):
        config = cat.load_config()
        self.assertEqual([cat.resolve_cum_pct(config, q)[0] for q in ("Q1", "Q2", "q3", "Q4")],
                         [0.15, 0.45, 0.75, 1.0])
        self.assertEqual(cat.resolve_cum_pct(config, cum_pct=0.5)[0], 0.5)
        with self.assertRaises(SystemExit):
            cat.resolve_cum_pct(config, "Q5")


class TestFindProfile(unittest.TestCase):
    def test_falls_back_to_the_skills_data_folder(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cwd:
            profile = Path(d) / cat.PROFILE_NAME
            profile.write_text("{}")
            with mock.patch.object(cat, "DATA_DIR", Path(d)), \
                    mock.patch.object(Path, "cwd", return_value=Path(cwd)), \
                    mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(cat.find_profile(), profile)
                self.assertEqual(cat.find_profile(str(profile)), profile)
            with mock.patch.object(cat, "DATA_DIR", Path(cwd)), \
                    mock.patch.object(Path, "cwd", return_value=Path(cwd)), \
                    mock.patch.dict(os.environ, {}, clear=True):
                self.assertIsNone(cat.find_profile())

    def test_an_explicit_profile_wins_over_the_data_folder(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            (Path(d) / cat.PROFILE_NAME).write_text("{}")
            explicit = Path(other) / "mine.json"
            explicit.write_text("{}")
            with mock.patch.object(cat, "DATA_DIR", Path(d)):
                self.assertEqual(cat.find_profile(str(explicit)), explicit)


class TestMain(unittest.TestCase):
    def test_due_now_nets_off_what_was_paid(self):
        with tempfile.TemporaryDirectory() as d:
            profile = os.path.join(d, "p.json")
            with open(profile, "w") as f:
                json.dump({"people": {"self": {k: PERSON[k] for k in cat.PERSON_KEYS}}}, f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cat.main(["--profile", profile, "--installment", "Q2", "--fdr-total", "1000000",
                          "--savings-balance", "0", "--dividends-total", "0",
                          "--bond-interest-total", "10000", "--bond-tds", "1000",
                          "--already-paid", "5000", "--json"])
            out = json.loads(buf.getvalue())
            annual = (20000.0 + 3000.0) * 1.10 * 1.04 - 1000.0
            self.assertAlmostEqual(out["estimated_annual_tax"], annual)
            self.assertAlmostEqual(out["due_now"], annual * 0.45 - 5000.0)


if __name__ == "__main__":
    unittest.main()
