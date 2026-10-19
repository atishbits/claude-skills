"""Unit tests for tax_calc.py. Run from scripts/:

    python3 -m unittest discover -s tests -p 'test_*.py'
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tax_calc import Inputs, compute  # noqa: E402


def new(**kw):
    return compute(Inputs(regime="new", ay="2026-27", **kw))


def old(**kw):
    return compute(Inputs(regime="old", ay="2026-27", **kw))


class RebateTest(unittest.TestCase):
    def test_below_threshold_is_nil(self):
        r = new(normal_income=700000)
        self.assertAlmostEqual(r.slab_tax, 15000, delta=1)
        self.assertAlmostEqual(r.rebate, 15000, delta=1)
        self.assertAlmostEqual(r.total_liability, 0, delta=1)

    def test_marginal_relief_just_above_threshold(self):
        r = new(normal_income=1210000)
        self.assertAlmostEqual(r.slab_tax, 61500, delta=1)
        self.assertAlmostEqual(r.rebate_marginal_relief, 51500, delta=1)
        self.assertAlmostEqual(r.total_liability, 10400, delta=1)

    def test_no_cliff_at_threshold(self):
        a = new(normal_income=1210000)
        b = new(normal_income=1210010)
        self.assertLessEqual(b.total_liability - a.total_liability, 11)

    def test_rebate_never_runs_against_112a(self):
        r = new(normal_income=400000, ltcg_112a=500000)
        self.assertEqual(r.rebate, 0)
        self.assertAlmostEqual(r.special_tax["ltcg_112a"],
                               (500000 - 125000) * 0.125, delta=1)

    def test_old_regime_rebate_at_5_lakh(self):
        r = old(normal_income=500000)
        self.assertAlmostEqual(r.slab_tax, 12500, delta=1)
        self.assertAlmostEqual(r.total_liability, 0, delta=1)


class SurchargeTest(unittest.TestCase):
    def test_no_surcharge_at_50_lakh(self):
        r = new(normal_income=5000000)
        self.assertAlmostEqual(r.slab_tax, 1080000, delta=1)
        self.assertAlmostEqual(r.surcharge, 0, delta=1)
        self.assertAlmostEqual(r.total_liability, 1123200, delta=1)

    def test_marginal_relief_at_every_band_floor(self):
        for regime in ("new", "old"):
            for floor in (5000000, 10000000, 20000000, 50000000):
                with self.subTest(regime=regime, floor=floor):
                    base = compute(Inputs(regime=regime, normal_income=floor))
                    over = compute(Inputs(regime=regime,
                                          normal_income=floor + 100))
                    self.assertLessEqual(
                        over.total_liability - base.total_liability, 110)

    def test_cap_on_112a_tax(self):
        r = new(normal_income=5000000, ltcg_112a=20000000)
        self.assertAlmostEqual(r.slab_tax, 1080000, delta=1)
        self.assertAlmostEqual(r.special_tax["ltcg_112a"], 2484375, delta=1)
        self.assertAlmostEqual(r.surcharge_rate, 0.25, places=9)
        self.assertAlmostEqual(r.surcharge,
                               1080000 * 0.25 + 2484375 * 0.15, delta=1)


class BasicExemptionTest(unittest.TestCase):
    def test_unused_exemption_set_against_111a(self):
        r = new(normal_income=100000, stcg_111a=500000)
        self.assertAlmostEqual(r.basic_exemption_adjusted, 300000, delta=1)
        self.assertAlmostEqual(r.special_tax["stcg_111a"], 200000 * 0.20,
                               delta=1)

    def test_old_regime_senior_exemption(self):
        r = old(age=65, normal_income=1000000)
        self.assertAlmostEqual(
            r.slab_tax, (500000 - 300000) * 0.05 + (1000000 - 500000) * 0.20,
            delta=1)


class InterestTest(unittest.TestCase):
    def test_234c_fully_deferred(self):
        r = new(normal_income=2000000, paid_by_quarter=[0, 0, 0, 0])
        a = r.total_liability
        want = (0.15 * a * 0.03 + 0.45 * a * 0.03
                + 0.75 * a * 0.03 + 1.00 * a * 0.01)
        self.assertAlmostEqual(r.interest_234c, want, delta=1)

    def test_234c_nil_when_paid_on_schedule(self):
        a = new(normal_income=2000000).total_liability
        r = new(normal_income=2000000,
                paid_by_quarter=[0.15 * a, 0.45 * a, 0.75 * a, a])
        self.assertAlmostEqual(r.interest_234c, 0, delta=1)

    def test_234b_on_unpaid_tax(self):
        r = new(normal_income=2000000, months_234b=4)
        self.assertAlmostEqual(r.total_liability, 208000, delta=1)
        self.assertAlmostEqual(r.interest_234b, 208000 * 0.04, delta=1)

    def test_234b_nil_when_90_percent_paid(self):
        r = new(normal_income=2000000, months_234b=4, advance_tax=190000)
        self.assertEqual(r.interest_234b, 0)


class InputValidationTest(unittest.TestCase):
    def test_unknown_ay_refused(self):
        with self.assertRaises(SystemExit):
            compute(Inputs(ay="2099-00", normal_income=100000))

    def test_dividend_cannot_exceed_normal_income(self):
        with self.assertRaises(SystemExit):
            new(normal_income=100000, dividend_income=200000)


if __name__ == "__main__":
    unittest.main()
