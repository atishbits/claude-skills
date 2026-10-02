import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import common  # noqa: E402
import screen_listings  # noqa: E402

CONFIG = common.load_config()
NOW = dt.datetime(2026, 10, 2, 7, 0, tzinfo=dt.timezone.utc)


def profile(**over):
    base = common.load_json(os.path.join(common.SKILL_DIR, "profile-template.json"))
    base.update(over)
    return base


def listing(issuer="Gamma Microfin", **over):
    base = {"key": f"/bonds/listing/{issuer.replace(' ', '-')}-1", "bond_id": "1",
            "tenure_id": None, "url": "https://www.wintwealth.com/x", "issuer": issuer,
            "rating": "A", "rating_raw": "A", "min_investment": 10000, "sold_pct": 50.0,
            "units_left": None, "ytm": 10.0, "ytm_is_upper_bound": False, "ytm_alt": None,
            "tenure_months": 18.0, "interest_frequency": "Monthly", "principal_type": "At Maturity",
            "seniority": None, "secured": None, "collateral": None, "guarantee": None,
            "rating_action": None, "held": False, "tags": []}
    base.update(over)
    return base


def doc(listings, captured_at="2026-10-02T05:00:00.000Z"):
    return {"schema": 1, "captured_at": captured_at, "capture_sha256": "s", "verified": True,
            "stated_live_count": len(listings), "warnings": [], "listings": listings}


def snapshot(holdings=None):
    return {"as_of": "2026-10-02", "holdings": holdings if holdings is not None else [
        {"issuer": "Alpha Finance", "isin": "INE000A07011", "current_value": 80000.0},
        {"issuer": "Beta Capital", "isin": "INE000B07022", "current_value": 20000.0}]}


FACTS = [{"isin": "INE000A07011", "wint_bond_id": None, "rating": "A"},
         {"isin": "INE000B07022", "wint_bond_id": None, "rating": "BBB+"}]


def run(listings, **kw):
    kw.setdefault("profile", profile())
    return screen_listings.screen(doc(listings), kw.pop("snapshot", snapshot()), FACTS,
                                  kw.pop("profile"), CONFIG, NOW, **kw)


def reasons(result):
    return " | ".join(r for x in result["rejected"] for r in x["reasons"])


class TestStaleness(unittest.TestCase):
    def test_stale_capture_is_refused(self):
        old = doc([listing()], captured_at="2026-10-01T05:00:00.000Z")
        with self.assertRaises(screen_listings.StaleCapture) as ctx:
            screen_listings.screen(old, snapshot(), FACTS, profile(), CONFIG, NOW)
        self.assertIn("26.0", str(ctx.exception))

    def test_allow_stale_runs_and_says_so(self):
        old = doc([listing()], captured_at="2026-10-01T05:00:00.000Z")
        result = screen_listings.screen(old, snapshot(), FACTS, profile(), CONFIG, NOW,
                                        allow_stale=True)
        self.assertTrue(result["stale"])
        self.assertEqual(result["age_hours"], 26.0)

    def test_fresh_capture(self):
        self.assertFalse(run([listing()])["stale"])


class TestHardFilters(unittest.TestCase):
    def test_passes_and_computes_post_tax_ytm(self):
        result = run([listing()])
        self.assertEqual(result["counts"], {"listed": 1, "shortlisted": 1, "rejected": 0})
        row = result["shortlist"][0]
        self.assertEqual(row["post_tax_ytm"], 7.0)
        self.assertEqual(row["security"], "security unconfirmed")
        self.assertEqual(row["rank"], 1)

    def test_rating_below_floor(self):
        self.assertIn("below", reasons(run([listing(rating="BBB")])))

    def test_unknown_rating_fails(self):
        self.assertIn("rating", reasons(run([listing(rating=None)])))
        self.assertIn("rating", reasons(run([listing(rating="PP-MLD AA")])))

    def test_tenure_above_ceiling(self):
        self.assertIn("tenure", reasons(run([listing(tenure_months=40.0)])))

    def test_unknown_tenure_or_ytm_fails(self):
        self.assertIn("tenure", reasons(run([listing(tenure_months=None)])))
        self.assertIn("YTM", reasons(run([listing(ytm=None)])))

    def test_low_post_tax_ytm(self):
        self.assertIn("post-tax", reasons(run([listing(ytm=9.0)])))

    def test_subordinated_and_unsecured_rejected_unless_allowed(self):
        risky = listing(seniority="subordinated", secured=False)
        text = reasons(run([risky]))
        self.assertIn("subordinated", text)
        self.assertIn("unsecured", text)
        allowed = run([risky], profile=profile(allow_unsecured=True, allow_subordinated=True))
        self.assertEqual(allowed["counts"]["shortlisted"], 1)
        self.assertEqual(allowed["shortlist"][0]["security"], "unsecured")

    def test_sold_out_is_rejected(self):
        self.assertIn("sold out", reasons(run([listing(sold_pct=100.0)])))
        self.assertIn("sold out", reasons(run([listing(sold_pct=None, units_left=0)])))

    def test_minimum_above_available_cash(self):
        result = run([listing(min_investment=100000)], cash=50000.0)
        self.assertIn("cash", reasons(result))
        self.assertEqual(result["cash"], 50000.0)


class TestConcentration(unittest.TestCase):
    def test_issuer_already_over_the_cap_is_rejected(self):
        # Alpha is 80% of a 100000 portfolio; the cap is 15%.
        self.assertIn("issuer", reasons(run([listing(issuer="Alpha Finance")])))

    def test_max_buy_keeps_a_new_issuer_under_the_cap(self):
        row = run([listing()])["shortlist"][0]
        # (0.15 * 100000 - 0) / (1 - 0.15)
        self.assertEqual(row["max_buy"], 17647.0)

    def test_rating_bucket_cap(self):
        # BBB bucket holds 20% of 100000; cap 40% -> room = (0.4*100000 - 20000)/0.6 = 33333
        ok = run([listing(rating="BBB+", ytm=11.0)])["shortlist"][0]
        self.assertEqual(ok["max_buy"], 17647.0)  # the issuer cap binds first
        tight = run([listing(rating="BBB+", ytm=11.0)],
                    profile=profile(max_rating_bucket_share_pct={"BBB": 21}))
        self.assertIn("BBB", reasons(tight))

    def test_empty_portfolio_has_no_caps(self):
        row = run([listing()], snapshot=snapshot(holdings=[]))["shortlist"][0]
        self.assertIsNone(row["max_buy"])


class TestRanking(unittest.TestCase):
    def test_ranked_within_risk_buckets_not_by_ytm_alone(self):
        result = run([
            listing(issuer="High Yield Co", rating="BBB+", ytm=12.0),
            listing(issuer="Safer Co", rating="AA", ytm=9.5),
            listing(issuer="Middle Co", rating="A", ytm=10.5),
            listing(issuer="Middle Quarterly", rating="A", ytm=11.0, interest_frequency="Quarterly"),
        ])
        self.assertEqual([r["issuer"] for r in result["shortlist"]],
                         ["Safer Co", "Middle Co", "Middle Quarterly", "High Yield Co"])
        self.assertEqual([r["rank"] for r in result["shortlist"]], [1, 2, 3, 4])

    def test_without_income_preference_higher_ytm_leads_the_bucket(self):
        result = run([
            listing(issuer="Middle Co", ytm=10.5),
            listing(issuer="Middle Quarterly", ytm=11.0, interest_frequency="Quarterly"),
        ], profile=profile(prefer_monthly_income=False))
        self.assertEqual([r["issuer"] for r in result["shortlist"]],
                         ["Middle Quarterly", "Middle Co"])

    def test_recorded_facts_fill_in_security(self):
        facts = FACTS + [{"isin": None, "wint_bond_id": "1", "secured": True,
                          "seniority": "senior"}]
        result = screen_listings.screen(doc([listing()]), snapshot(), facts, profile(), CONFIG, NOW)
        self.assertEqual(result["shortlist"][0]["security"], "secured")
        self.assertEqual(result["shortlist"][0]["risk_bucket"], "A / secured / senior")



class TestReviewFindings(unittest.TestCase):
    def test_unrated_holdings_are_reported_because_bucket_caps_cannot_see_them(self):
        result = screen_listings.screen(doc([listing()]), snapshot(), [], profile(), CONFIG, NOW)
        self.assertEqual(result["unrated_held_value"], 100000.0)
        self.assertTrue(any("unrated" in w for w in result["warnings"]))
        rated = run([listing()])
        self.assertEqual(rated["unrated_held_value"], 0)
        self.assertEqual(rated["warnings"], [])

    def test_bad_profile_rating_is_a_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            run([listing()], profile=profile(min_rating="BBB +"))
        self.assertIn("min_rating", str(ctx.exception))



class TestGroups(unittest.TestCase):
    def test_a_listing_from_a_held_group_counts_against_the_group(self):
        facts = FACTS + [{"isin": "INE000A07011", "wint_bond_id": None, "issuer": "Alpha Finance",
                          "group": "Alpha Group", "rating": "A"},
                         {"isin": None, "wint_bond_id": "9", "issuer": "Gamma Microfin",
                          "group": "Alpha Group"}]
        facts = [f for f in facts if f.get("issuer") or f["isin"] != "INE000A07011"]
        result = screen_listings.screen(doc([listing()]), snapshot(), facts, profile(), CONFIG, NOW)
        text = " | ".join(r for x in result["rejected"] for r in x["reasons"])
        self.assertIn("Alpha Group", text)



class TestRecordedRatingAndTaxBasis(unittest.TestCase):
    def facts(self, rating):
        return FACTS + [{"isin": None, "wint_bond_id": "1", "issuer": "Gamma Microfin",
                         "rating": rating, "secured": True, "seniority": "senior"}]

    def test_recorded_rating_overrides_the_card_for_the_floor(self):
        # The card says A; the agency's rating, recorded from its rationale, is BBB.
        result = screen_listings.screen(doc([listing()]), snapshot(), self.facts("BBB"),
                                        profile(), CONFIG, NOW)
        self.assertEqual(result["counts"]["shortlisted"], 0)
        self.assertIn("rating BBB is below", " ".join(result["rejected"][0]["reasons"]))

    def test_recorded_rating_drives_bucket_and_sort_and_the_card_is_shown(self):
        result = screen_listings.screen(
            doc([listing(rating="BBB+", rating_raw="BBB+", ytm=11.0),
                 listing(issuer="Other Co", bond_id="2", rating="A", ytm=10.0)]),
            snapshot(), self.facts("AA"), profile(), CONFIG, NOW)
        first = result["shortlist"][0]
        self.assertEqual((first["issuer"], first["rating"], first["rating_on_card"]),
                         ("Gamma Microfin", "AA", "BBB+"))
        self.assertTrue(first["risk_bucket"].startswith("AA /"))
        self.assertTrue(any("Gamma Microfin" in w and "BBB+" in w for w in result["warnings"]))

    def test_effective_tax_rate_replaces_the_slab_when_given(self):
        plain = run([listing()])
        self.assertEqual(plain["shortlist"][0]["post_tax_ytm"], 7.0)
        self.assertIn("30", plain["post_tax_basis"])
        self.assertIn("approximation", plain["post_tax_basis"])
        cess = run([listing()], profile=profile(effective_tax_rate_pct=31.2))
        self.assertEqual(cess["shortlist"][0]["post_tax_ytm"], 6.88)
        self.assertIn("31.2", cess["post_tax_basis"])


class TestTotalInvestable(unittest.TestCase):
    def test_caps_are_measured_against_everything_invested_when_given(self):
        # Alpha is 80000 of a 100000 Wint book, but 8% of 1,000,000 invested overall.
        result = run([listing(issuer="Alpha Finance")], profile=profile(total_investable=1_000_000))
        row = result["shortlist"][0]
        # 15% of 1,000,000 less the 80000 already held; the base does not grow with the purchase
        self.assertEqual(row["max_buy"], 70000.0)
        self.assertIn("1000000", result["cap_basis"])

    def test_without_it_the_basis_is_the_wint_book(self):
        self.assertIn("Wint", run([listing()])["cap_basis"])



class TestBudgetAndYieldFloor(unittest.TestCase):
    def snap(self):
        s = snapshot()
        s["purchases"] = [{"isin": "INE000A07011", "date": "2026-05-01", "invested": 300000.0},
                          {"isin": "INE000B07022", "date": "2026-02-01", "invested": 900000.0}]
        return s

    def test_yield_under_the_floor_is_rejected(self):
        result = run([listing(ytm=8.9)], profile=profile(min_ytm_pct=9, min_post_tax_ytm_pct=0))
        self.assertIn("YTM 8.9% is under the 9% floor", reasons(result))
        ok = run([listing(ytm=9.0)], profile=profile(min_ytm_pct=9, min_post_tax_ytm_pct=0))
        self.assertEqual(ok["counts"]["shortlisted"], 1)

    def test_budget_counts_only_this_financial_year_and_caps_max_buy(self):
        # Financial year from 1 Apr 2026: 300000 invested so far, 12000 of a 312000 budget left.
        result = run([listing()], snapshot=self.snap(),
                     profile=profile(annual_investment_budget=312000))
        self.assertEqual(result["budget"], {"annual": 312000, "financial_year_from": "2026-04-01",
                                            "invested_so_far": 300000.0, "remaining": 12000.0})
        self.assertEqual(result["shortlist"][0]["max_buy"], 12000.0)

    def test_budget_used_up_rejects_everything(self):
        result = run([listing()], snapshot=self.snap(),
                     profile=profile(annual_investment_budget=305000))
        self.assertIn("budget", reasons(result))

    def test_no_budget_set(self):
        self.assertIsNone(run([listing()])["budget"])


if __name__ == "__main__":
    unittest.main()
