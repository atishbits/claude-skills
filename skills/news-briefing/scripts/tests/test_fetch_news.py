import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import fetch_news  # noqa: E402
from common import parse_ts  # noqa: E402

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Example Wire</title>
<item><title>Example Industries opens a new plant</title>
  <link>https://news.example.com/a?utm_source=feed</link>
  <pubDate>Fri, 09 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Old story</title><link>https://news.example.com/old</link>
  <pubDate>Thu, 01 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>No date story</title><link>https://news.example.com/nodate</link></item>
<item><title>Rain &amp;amp; &lt;b&gt;floods&lt;/b&gt; hit Sampleville</title>
  <link>https://news.example.com/b</link>
  <pubDate>Thu, 08 Oct 2026 09:00:00 +0530</pubDate></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><title>Example Atom</title>
<entry><title>Model railways show draws crowds</title>
  <link rel="alternate" href="https://atom.example.org/c"/>
  <updated>2026-10-09T12:00:00Z</updated></entry>
<entry><title>Example Industries opens a new plant - Example Atom</title>
  <link href="https://atom.example.org/dup"/>
  <published>2026-10-09T11:00:00Z</published><updated>2026-10-09T13:00:00Z</updated></entry>
</feed>"""


class TestParseFeed(unittest.TestCase):
    def test_rss_items(self):
        items = fetch_news.parse_feed(RSS)
        self.assertEqual([i["title"] for i in items], [
            "Example Industries opens a new plant", "Old story", "No date story",
            "Rain & floods hit Sampleville"])
        self.assertEqual(items[0]["url"], "https://news.example.com/a?utm_source=feed")
        self.assertEqual(items[0]["published"], parse_ts("2026-10-09T10:00:00Z"))

    def test_rss_date_with_an_offset_is_converted_to_utc(self):
        self.assertEqual(fetch_news.parse_feed(RSS)[3]["published"], parse_ts("2026-10-08T03:30:00Z"))

    def test_item_without_a_date_has_none(self):
        self.assertIsNone(fetch_news.parse_feed(RSS)[2]["published"])

    def test_atom_entries(self):
        items = fetch_news.parse_feed(ATOM.encode("utf-8"))
        self.assertEqual(items[0]["url"], "https://atom.example.org/c")
        self.assertEqual(items[0]["published"], parse_ts("2026-10-09T12:00:00Z"))

    def test_atom_published_beats_updated(self):
        self.assertEqual(fetch_news.parse_feed(ATOM)[1]["published"], parse_ts("2026-10-09T11:00:00Z"))

    def test_broken_xml_raises(self):
        with self.assertRaises(SyntaxError):
            fetch_news.parse_feed("<html><body>503 Service Unavailable</body>")

    def test_entity_declarations_are_refused(self):
        bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel/></rss>'
        with self.assertRaises(ValueError):
            fetch_news.parse_feed(bomb)


class TestNormalise(unittest.TestCase):
    def test_tracking_parameters_host_case_and_slash(self):
        a = fetch_news.normalise_url("http://WWW.Example.com/story/?utm_source=x&id=7&fbclid=y#top")
        b = fetch_news.normalise_url("https://example.com/story?id=7")
        self.assertEqual(a, b)

    def test_different_stories_stay_different(self):
        self.assertNotEqual(fetch_news.normalise_url("https://example.com/a"),
                            fetch_news.normalise_url("https://example.com/b"))

    def test_title_drops_the_outlet_suffix_and_punctuation(self):
        self.assertEqual(fetch_news.normalise_title("Example Industries opens a new plant - Example Atom"),
                         fetch_news.normalise_title("Example Industries opens a new plant!"))

    def test_host(self):
        self.assertEqual(fetch_news.host("https://www.News.Example.com/x?key=SECRET"), "news.example.com")


class TestDedupe(unittest.TestCase):
    def test_same_url_or_same_title_keeps_the_first(self):
        items = [
            {"title": "Plant opens", "url": "https://example.com/a?utm_medium=rss"},
            {"title": "Something else", "url": "https://example.com/a"},
            {"title": "Plant opens | Example Wire", "url": "https://other.example.org/z"},
            {"title": "A different story", "url": "https://example.com/d"},
        ]
        self.assertEqual([i["url"] for i in fetch_news.dedupe(items)],
                         ["https://example.com/a?utm_medium=rss", "https://example.com/d"])


class TestMatchTopic(unittest.TestCase):
    TOPICS = [{"name": "Tin", "kind": "sector"}, {"name": "Example Industries", "kind": "company"}]

    def test_whole_word_case_insensitive(self):
        self.assertEqual(fetch_news.match_topic("tin prices rise", self.TOPICS)["name"], "Tin")

    def test_no_match_inside_a_longer_word(self):
        self.assertIsNone(fetch_news.match_topic("Tintin sequel announced", self.TOPICS))

    def test_no_match(self):
        self.assertIsNone(fetch_news.match_topic("Rain hits Sampleville", self.TOPICS))


G = "https://news.example.com/world.xml"
H = "https://atom.example.org/home.xml"
START = parse_ts("2026-10-03T06:00:00Z")
END = parse_ts("2026-10-10T06:00:00Z")
PROFILE = {
    "feeds": {"global": [G], "home": [H], "markets": []},
    "portfolio_topics": [{"name": "Example Industries", "kind": "company"}],
    "interest_topics": [{"name": "model railways", "why": "a hobby"}],
}


def fake(pages):
    def fetch(url):
        if url not in pages:
            raise OSError("unreachable")
        return pages[url].encode("utf-8")
    return fetch


class TestCollect(unittest.TestCase):
    def test_filters_tags_and_dedupes(self):
        got = fetch_news.collect(PROFILE, START, END, fetch=fake({G: RSS, H: ATOM}))
        by_section = {c["section"]: c for c in got["candidates"]}
        self.assertEqual(len(got["candidates"]), 3)
        self.assertEqual(by_section["portfolio"]["topic"], "Example Industries")
        self.assertEqual(by_section["portfolio"]["kind"], "company")
        self.assertEqual(by_section["interests"]["topic"], "model railways")
        self.assertEqual(by_section["interests"]["why"], "a hobby")
        self.assertEqual(by_section["global"]["title"], "Rain & floods hit Sampleville")
        self.assertEqual(by_section["global"]["published"], "2026-10-08T03:30:00Z")
        self.assertEqual(by_section["global"]["source"], "news.example.com")
        self.assertEqual(got["undated_dropped"], 1)
        self.assertEqual((got["reachable"], got["sources_ok"], got["failed"]), (True, 2, []))

    def test_one_feed_failing_does_not_stop_the_others(self):
        got = fetch_news.collect(PROFILE, START, END, fetch=fake({G: RSS}))
        self.assertTrue(got["reachable"])
        self.assertEqual(got["failed"], [{"source": "atom.example.org", "error": "OSError"}])
        self.assertEqual({c["section"] for c in got["candidates"]}, {"portfolio", "global"})

    def test_an_error_page_counts_as_a_failed_source(self):
        pages = {G: RSS, H: "<html><body>503 Service Unavailable</body>"}
        got = fetch_news.collect(PROFILE, START, END, fetch=fake(pages))
        self.assertEqual(got["failed"], [{"source": "atom.example.org", "error": "ParseError"}])
        self.assertTrue(got["candidates"])

    def test_nothing_reachable(self):
        got = fetch_news.collect(PROFILE, START, END, fetch=fake({}))
        self.assertEqual((got["reachable"], got["candidates"]), (False, []))

    def test_no_feeds_configured_is_not_reachable(self):
        got = fetch_news.collect({}, START, END, fetch=fake({}))
        self.assertEqual((got["reachable"], got["failed"]), (False, []))

    def test_search_feed_is_fetched_per_topic_and_failures_listed_once(self):
        profile = dict(PROFILE, feeds={"search": "https://search.example.com/rss?q={query}"})
        hit = RSS.replace("Example Industries opens a new plant", "New plant announced")
        pages = {"https://search.example.com/rss?q=Example+Industries": hit}
        got = fetch_news.collect(profile, START, END, fetch=fake(pages))
        titles = {c["title"]: c for c in got["candidates"]}
        self.assertEqual(titles["New plant announced"]["section"], "portfolio")
        self.assertEqual(titles["New plant announced"]["topic"], "Example Industries")
        self.assertEqual(got["failed"], [{"source": "search.example.com", "error": "OSError"}])

    def test_per_section_cap_keeps_the_newest(self):
        items = "".join(
            f"<item><title>Story {n}</title><link>https://news.example.com/s{n}</link>"
            f"<pubDate>0{n} Oct 2026 12:00:00 GMT</pubDate></item>" for n in range(4, 9))
        rss = f'<rss version="2.0"><channel>{items}</channel></rss>'
        got = fetch_news.collect({"feeds": {"global": [G]}}, START, END, fetch=fake({G: rss}),
                                 per_section=2)
        self.assertEqual([c["title"] for c in got["candidates"]], ["Story 8", "Story 7"])


class TestMain(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.profile = os.path.join(self.dir, "profile.json")

    def save(self, profile):
        with open(self.profile, "w", encoding="utf-8") as fh:
            json.dump(profile, fh)

    def args(self):
        return ["--profile", self.profile, "--start", "2026-10-03T06:00:00Z",
                "--end", "2026-10-10T06:00:00Z", "--api", os.path.join(self.dir, "api.json")]

    def test_prints_the_collection(self):
        self.save(PROFILE)
        out = io.StringIO()
        with mock.patch.object(fetch_news, "default_fetch", fake({G: RSS, H: ATOM})), \
                contextlib.redirect_stdout(out):
            fetch_news.main(self.args())
        self.assertEqual(len(json.loads(out.getvalue())["candidates"]), 3)

    def test_invalid_profile_stops_before_any_fetch(self):
        self.save(dict(PROFILE, quantity=10))
        called = mock.Mock(side_effect=AssertionError("network was used"))
        with mock.patch.object(fetch_news, "default_fetch", called):
            with self.assertRaises(SystemExit) as ctx:
                fetch_news.main(self.args())
        self.assertIn("quantity: unknown field", str(ctx.exception))
        called.assert_not_called()


API = {
    "url_template": "https://api.example.com/v1?apikey={key}&q={query}&from={start_date}",
    "key": "SECRETKEY",
    "items_path": "data.results",
    "fields": {"title": "title", "url": "link", "published": "pubDate", "source": "outlet.name"},
}
API_BODY = json.dumps({"data": {"results": [
    {"title": "Example Industries wins an order", "link": "https://wire.example.net/o",
     "pubDate": "2026-10-09 08:00:00", "outlet": {"name": "Example Net"}},
    {"title": "", "link": "https://wire.example.net/blank", "pubDate": "2026-10-09 08:00:00"},
    "not an object",
]}})
API_URL = "https://api.example.com/v1?apikey=SECRETKEY&q=Example+Industries&from=2026-10-03"


class TestApi(unittest.TestCase):
    def test_url_is_built_from_the_template(self):
        self.assertEqual(fetch_news.api_url(API, "Example Industries", START), API_URL)

    def test_response_is_read_through_the_field_paths(self):
        items = fetch_news.parse_api(API_BODY, API)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "Example Net")
        self.assertEqual(items[0]["published"], parse_ts("2026-10-09T08:00:00Z"))

    def test_response_without_the_list_raises(self):
        with self.assertRaises(ValueError):
            fetch_news.parse_api('{"status": "error"}', API)

    def test_collect_tags_api_items_with_their_topic(self):
        profile = {"portfolio_topics": PROFILE["portfolio_topics"]}
        got = fetch_news.collect(profile, START, END, fetch=fake({API_URL: API_BODY}), api=API)
        self.assertEqual(got["candidates"][0]["topic"], "Example Industries")
        self.assertEqual(got["candidates"][0]["section"], "portfolio")

    def test_a_failing_api_never_leaks_the_key(self):
        profile = {"portfolio_topics": PROFILE["portfolio_topics"]}
        got = fetch_news.collect(profile, START, END, fetch=fake({}), api=API)
        self.assertEqual(got["failed"], [{"source": "api.example.com", "error": "OSError"}])
        self.assertNotIn("SECRETKEY", json.dumps(got))

    def test_max_queries_limits_the_calls(self):
        topics = [{"name": f"Topic {n}", "kind": "sector"} for n in range(5)]
        calls = []

        def fetch(url):
            calls.append(url)
            return API_BODY.encode("utf-8")

        fetch_news.collect({"portfolio_topics": topics}, START, END, fetch=fetch,
                           api=dict(API, max_queries=2))
        self.assertEqual(len(calls), 2)

    def test_load_api_absent_file_means_no_api(self):
        self.assertIsNone(fetch_news.load_api("/nonexistent/api.json"))

    def test_load_api_names_the_missing_part_without_printing_the_key(self):
        path = os.path.join(tempfile.mkdtemp(), "api.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"url_template": "https://api.example.com/v1?q={query}", "key": "SECRETKEY"}, fh)
        with self.assertRaises(SystemExit) as ctx:
            fetch_news.load_api(path)
        self.assertIn("fields", str(ctx.exception))
        self.assertNotIn("SECRETKEY", str(ctx.exception))


class TestHostNeverCarriesCredentials(unittest.TestCase):
    def test_userinfo_and_port_are_dropped(self):
        self.assertEqual(fetch_news.host("https://reader:SECRETKEY@www.Example.com:8443/feed.xml"),
                         "example.com")

    def test_a_failing_feed_with_credentials_in_its_address_does_not_leak_them(self):
        url = "https://reader:SECRETKEY@feeds.example.com/private.xml"
        got = fetch_news.collect({"feeds": {"global": [url]}}, START, END, fetch=fake({}))
        self.assertEqual(got["failed"], [{"source": "feeds.example.com", "error": "OSError"}])
        self.assertNotIn("SECRETKEY", json.dumps(got))


class TestNotAFeed(unittest.TestCase):
    PAGE = "<html><head><title>Sign in</title></head><body><p>Please sign in</p></body></html>"

    def test_a_well_formed_page_that_is_not_a_feed_raises(self):
        with self.assertRaises(ValueError):
            fetch_news.parse_feed(self.PAGE)

    def test_collect_lists_it_as_failed_and_not_reachable(self):
        got = fetch_news.collect({"feeds": {"global": [G]}}, START, END, fetch=fake({G: self.PAGE}))
        self.assertEqual(got["failed"], [{"source": "news.example.com", "error": "ValueError"}])
        self.assertFalse(got["reachable"])

    def test_rdf_feeds_are_still_read(self):
        rdf = ('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
               'xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<item><title>Story</title><link>https://news.example.com/r</link>'
               '<dc:date>2026-10-09T10:00:00Z</dc:date></item></rdf:RDF>')
        self.assertEqual(fetch_news.parse_feed(rdf)[0]["published"], parse_ts("2026-10-09T10:00:00Z"))


class TestAcronymTopics(unittest.TestCase):
    TOPICS = [{"name": "IT", "kind": "sector"}]

    def test_an_all_capitals_name_does_not_match_the_ordinary_word(self):
        self.assertIsNone(fetch_news.match_topic("Central bank says it will hold rates", self.TOPICS))

    def test_an_all_capitals_name_matches_itself(self):
        self.assertEqual(fetch_news.match_topic("IT exporters report results", self.TOPICS)["name"], "IT")


if __name__ == "__main__":
    unittest.main()
