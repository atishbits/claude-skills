import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import card_offer  # noqa: E402

BASE = {"name": "Fuel Card A", "joining_fee": 0, "annual_fee": 0, "fee_waiver_spend": None,
        "gst_on_fees_pct": 18, "rates": {"fuel": 0.0, "default": 0.0}, "reward_cap_month": {},
        "point_value_inr": 1.0, "fuel_surcharge_pct": 1.0, "surcharge_waiver_pct": 0,
        "surcharge_txn_min": 400, "surcharge_txn_max": 4000, "surcharge_waiver_cap_month": None,
        "use_for": ["fuel"]}


def spend(fuel_txns, other=None, factor=1.0):
    by = {"fuel": sum(x["amount"] for x in fuel_txns) * factor}
    by.update(other or {})
    return {"by_category": by, "fuel_txns": fuel_txns, "factor": factor, "annualised": factor != 1.0,
            "months_covered": 12}


def dump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f)


def monthly_fuel(amount):
    return [{"date": f"2026-{m:02d}-10", "amount": amount, "account": "x"} for m in range(1, 13)]


class TestValue(unittest.TestCase):
    def test_fuel_reward_capped_monthly(self):
        o = dict(BASE, rates={"fuel": 0.05}, reward_cap_month={"fuel": 250})
        self.assertEqual(card_offer.value(o, spend(monthly_fuel(10000)))["rewards"], 3000.0)

    def test_per_txn_factor_used_for_fuel(self):
        # Three months of fuel on a card, each scaled by 4 to a year.
        txns = [{"date": f"2026-{m:02d}-10", "amount": 5000, "account": "c", "factor": 4.0} for m in (7, 8, 9)]
        o = dict(BASE, rates={"fuel": 0.05}, reward_cap_month={"fuel": 200}, surcharge_waiver_pct=100,
                 surcharge_txn_max=None)
        v = card_offer.value(o, spend(txns, factor=1.7))
        self.assertEqual(v["rewards"], 2400.0)        # 200 cap x 3 months x 4
        self.assertEqual(v["surcharge_saved"], 600.0)  # 50 x 3 x 4

    def test_surcharge_only_in_txn_band(self):
        o = dict(BASE, surcharge_waiver_pct=100)
        txns = [{"date": "2026-01-01", "amount": a, "account": "x"} for a in (300, 2000, 5000)]
        self.assertEqual(card_offer.value(o, spend(txns))["surcharge_saved"], 20.0)

    def test_surcharge_monthly_cap(self):
        o = dict(BASE, surcharge_waiver_pct=100, surcharge_txn_max=100000, surcharge_waiver_cap_month=50)
        self.assertEqual(card_offer.value(o, spend(monthly_fuel(10000)))["surcharge_saved"], 600.0)

    def test_fee_waived_above_spend(self):
        o = dict(BASE, annual_fee=500, fee_waiver_spend=50000)
        self.assertEqual(card_offer.value(o, spend(monthly_fuel(5000)))["fees"], 0.0)
        self.assertEqual(card_offer.value(o, spend(monthly_fuel(3000)))["fees"], 590.0)

    def test_gst_on_fee_and_joining_fee_separate(self):
        o = dict(BASE, annual_fee=1000, joining_fee=500)
        v = card_offer.value(o, spend(monthly_fuel(1000)))
        self.assertEqual((v["fees"], v["first_year_extra"]), (1180.0, 590.0))
        self.assertEqual(v["net"], round(v["rewards"] + v["surcharge_saved"] - 1180.0, 2))

    def test_annualised_spend_scales_and_notes(self):
        o = dict(BASE, rates={"fuel": 0.01})
        txns = monthly_fuel(1000)[:6]
        v = card_offer.value(o, spend(txns, factor=2.0))
        self.assertEqual(v["rewards"], 120.0)
        self.assertTrue(any("annualised" in n for n in v["notes"]))

    def test_sorted_by_net(self):
        with tempfile.TemporaryDirectory() as root:
            sd = os.path.join(root, "data", "skill-data")
            os.makedirs(sd)
            os.makedirs(os.path.join(root, "data", "offers"))
            dump({"as_of": "2026-12-31", "spend_12m": spend(monthly_fuel(5000))},
                 os.path.join(sd, "analysis-2026-12-31.json"))
            for name, rate in (("Low", 0.01), ("High", 0.04)):
                dump(dict(BASE, name=name, rates={"fuel": rate}),
                     os.path.join(root, "data", "offers", name + ".json"))
            out = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "..",
                                                               "card_offer.py"), "--root", root, "--json"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            names = [r["name"] for r in json.loads(out.stdout)]
            self.assertEqual(names, ["High", "Low"])

    def test_default_use_for_skips_uncardable(self):
        o = dict(BASE, rates={"default": 0.01})
        o.pop("use_for")
        s = spend([], {"fuel": 0.0, "dining": 10000.0, "loan_emi": 100000.0, "housing": 50000.0,
                       "card_spend_unexpanded": 50000.0})
        v = card_offer.value(o, s)
        self.assertEqual(v["rewards"], 100.0)
        self.assertTrue(any("left out" in n and "loan_emi" in n for n in v["notes"]))

    def test_scale_fuel_scales_each_fill(self):
        # Price drop: 4,500 fills fall to 3,600, inside a 4,000 surcharge band.
        txns = [{"date": "2026-01-10", "amount": 4500, "account": "x"}]
        s = card_offer.scale_spend(spend(txns), {"fuel": 0.8})
        self.assertEqual(s["fuel_txns"][0]["amount"], 3600.0)
        self.assertEqual(s["by_category"]["fuel"], 3600.0)
        o = dict(BASE, surcharge_waiver_pct=100)
        self.assertEqual(card_offer.value(o, spend(txns))["surcharge_saved"], 0.0)
        self.assertEqual(card_offer.value(o, s)["surcharge_saved"], 36.0)

    def test_scale_leaves_input_and_other_categories(self):
        base = spend(monthly_fuel(1000), other={"dining": 500.0})
        s = card_offer.scale_spend(base, {"fuel": 0.5})
        self.assertEqual(s["by_category"]["dining"], 500.0)
        self.assertEqual(base["fuel_txns"][0]["amount"], 1000)

    def test_parse_scales(self):
        self.assertEqual(card_offer._parse_scales(["fuel=0.85"]), {"fuel": 0.85})
        for bad in (["fuel"], ["=0.5"], ["fuel=-1"]):
            with self.assertRaises(SystemExit):
                card_offer._parse_scales(bad)


if __name__ == "__main__":
    unittest.main()
