import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import user_profile  # noqa: E402
from common import parse_ts  # noqa: E402

GOOD = {
    "home": {"country": "Examplestan", "city": "Sampleville"},
    "work": {"employer": "Example Corp", "industry": "software", "role": "engineer"},
    "feeds": {
        "global": ["https://news.example.com/feed/1234567.xml"],
        "home": [],
        "markets": [],
        "search": "https://news.example.com/search?q={query}",
    },
    "portfolio_topics": [{"name": "Example Industries", "kind": "company"}],
    "interest_topics": [{"name": "model railways", "why": "a hobby"}],
    "declined": [],
    "updated": "2026-10-10T06:00:00Z",
}


def changed(**overrides):
    profile = copy.deepcopy(GOOD)
    profile.update(overrides)
    return profile


class TestValidate(unittest.TestCase):
    def assertRejected(self, profile, fragment):
        errors = user_profile.validate(profile)
        self.assertTrue(any(fragment in e for e in errors), errors)

    def test_good_profile_has_no_errors(self):
        self.assertEqual(user_profile.validate(GOOD), [])

    def test_empty_profile_is_valid(self):
        self.assertEqual(user_profile.validate({}), [])

    def test_not_an_object(self):
        self.assertRejected([], "must be a JSON object")

    def test_unknown_top_level_key(self):
        self.assertRejected(changed(quantity=10), "quantity: unknown field")

    def test_unknown_nested_key(self):
        self.assertRejected(changed(home={"country": "Examplestan", "postcode": "X"}),
                            "home.postcode: unknown field")

    def test_digit_run_in_a_name_is_rejected(self):
        self.assertRejected(changed(portfolio_topics=[{"name": "Example 1234567", "kind": "company"}]),
                            "5 or more digits")

    def test_digit_run_in_a_feed_url_is_allowed(self):
        self.assertEqual(user_profile.validate(GOOD), [])

    def test_search_feed_needs_the_query_marker(self):
        feeds = dict(GOOD["feeds"], search="https://news.example.com/search")
        self.assertRejected(changed(feeds=feeds), "feeds.search")

    def test_feed_must_be_a_url(self):
        feeds = dict(GOOD["feeds"], home=["file:///etc/hosts"])
        self.assertRejected(changed(feeds=feeds), "feeds.home")

    def test_unknown_feed_section(self):
        feeds = dict(GOOD["feeds"], sport=[])
        self.assertRejected(changed(feeds=feeds), "feeds.sport: unknown field")

    def test_topic_with_an_extra_key(self):
        topic = {"name": "Example Industries", "kind": "company", "units": 10}
        self.assertRejected(changed(portfolio_topics=[topic]), "portfolio_topics[0]")

    def test_topic_with_a_bad_kind(self):
        self.assertRejected(changed(portfolio_topics=[{"name": "Example Industries", "kind": "fund"}]),
                            "portfolio_topics[0].kind")

    def test_interest_needs_a_why(self):
        self.assertRejected(changed(interest_topics=[{"name": "model railways", "why": ""}]),
                            "interest_topics[0].why")

    def test_declined_must_name_onboarding_fields(self):
        self.assertRejected(changed(declined=["home.planet"]), "declined")

    def test_bad_timestamp(self):
        self.assertRejected(changed(updated="yesterday"), "updated")


class TestMissing(unittest.TestCase):
    def test_empty_profile_is_missing_everything(self):
        self.assertEqual(user_profile.missing({}), list(user_profile.ONBOARDING))

    def test_good_profile_is_missing_nothing(self):
        self.assertEqual(user_profile.missing(GOOD), [])

    def test_declined_fields_are_not_asked_again(self):
        profile = {"home": {"country": "Examplestan"}, "declined": ["work.employer", "home.city"]}
        self.assertEqual(user_profile.missing(profile),
                         ["work.industry", "work.role", "interest_topics"])

    def test_blank_text_counts_as_missing(self):
        profile = changed(home={"country": "  ", "city": "Sampleville"})
        self.assertEqual(user_profile.missing(profile), ["home.country"])


if __name__ == "__main__":
    unittest.main()
