import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile

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


def write(text, name="book.csv"):
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class TestTopics(unittest.TestCase):
    def test_reads_only_the_name_column(self):
        path = write("Symbol,Units,Price\nEXAMPLEB,5,500\nEXAMPLEA,10,100\n")
        got, skipped = user_profile.topics([path])
        self.assertEqual(got, [{"name": "EXAMPLEA", "kind": "company"},
                               {"name": "EXAMPLEB", "kind": "company"}])
        self.assertEqual(skipped, 0)

    def test_name_column_need_not_be_first(self):
        path = write("Units,Issuer,Price\n5,Example Finance,500\n")
        got, _ = user_profile.topics([path], kind="issuer")
        self.assertEqual(got, [{"name": "Example Finance", "kind": "issuer"}])

    def test_unknown_header_uses_the_first_column(self):
        path = write("Thing,Units\nEXAMPLEA,10\n")
        got, _ = user_profile.topics([path])
        self.assertEqual([t["name"] for t in got], ["EXAMPLEA"])

    def test_byte_order_mark_is_ignored(self):
        path = write("\ufeffSymbol,Units\nEXAMPLEA,10\n")
        got, _ = user_profile.topics([path])
        self.assertEqual([t["name"] for t in got], ["EXAMPLEA"])

    def test_totals_and_blank_rows_are_dropped(self):
        path = write("Symbol,Units\nEXAMPLEA,10\n,\nTotal,10\nGrand Total,10\n")
        got, _ = user_profile.topics([path])
        self.assertEqual([t["name"] for t in got], ["EXAMPLEA"])

    def test_identifier_like_names_are_counted_not_returned(self):
        path = write("Symbol,Units\nEXAMPLEA,10\n9876543210,4\n")
        got, skipped = user_profile.topics([path])
        self.assertEqual([t["name"] for t in got], ["EXAMPLEA"])
        self.assertEqual(skipped, 1)

    def test_duplicates_across_files_collapse(self):
        a = write("Symbol,Units\nEXAMPLEA,10\n")
        b = write("Symbol,Units\nEXAMPLEA,3\nEXAMPLEC,1\n")
        got, _ = user_profile.topics([a, b])
        self.assertEqual([t["name"] for t in got], ["EXAMPLEA", "EXAMPLEC"])

    def test_named_column_must_exist(self):
        path = write("Symbol,Units\nEXAMPLEA,10\n")
        with self.assertRaises(ValueError):
            user_profile.topics([path], column="Company")

    def test_empty_file(self):
        self.assertEqual(user_profile.topics([write("")]), ([], 0))


class TestLatest(unittest.TestCase):
    NOW = parse_ts("2026-10-10T06:00:00Z")

    def test_later_time_wins(self):
        a, b = parse_ts("2026-10-07T06:00:00Z"), parse_ts("2026-10-09T06:00:00Z")
        self.assertEqual(user_profile.latest([a, b], self.NOW), b)

    def test_future_times_are_dropped(self):
        a, future = parse_ts("2026-10-07T06:00:00Z"), parse_ts("2026-10-11T06:00:00Z")
        self.assertEqual(user_profile.latest([a, future], self.NOW), a)

    def test_nothing_usable(self):
        self.assertIsNone(user_profile.latest([], self.NOW))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.profile = os.path.join(self.dir, "profile.json")
        self.state = os.path.join(self.dir, "nested", "state.json")

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            user_profile.main(["--profile", self.profile, "--state", self.state, *argv])
        return out.getvalue()

    def save(self, profile):
        with open(self.profile, "w", encoding="utf-8") as fh:
            json.dump(profile, fh)

    def test_validate_ok(self):
        self.save(GOOD)
        self.assertEqual(self.run_cli("validate").strip(), "OK")

    def test_validate_reports_and_exits_nonzero(self):
        self.save(changed(quantity=10))
        with self.assertRaises(SystemExit) as ctx:
            self.run_cli("validate")
        self.assertIn("quantity: unknown field", str(ctx.exception))

    def test_missing_with_no_profile_lists_every_field(self):
        self.assertEqual(self.run_cli("missing").split(), list(user_profile.ONBOARDING))

    def test_merge_state_creates_the_folder_and_keeps_the_latest(self):
        self.run_cli("merge-state", "--now", "2026-10-10T06:00:00Z", "2026-10-07T06:00:00Z")
        got = self.run_cli("merge-state", "--now", "2026-10-10T06:00:00Z",
                           "2026-10-05T06:00:00Z", "2026-10-11T06:00:00Z")
        self.assertEqual(got.strip(), "2026-10-07T06:00:00Z")
        with open(self.state, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"last_run": "2026-10-07T06:00:00Z"})

    def test_merge_state_with_nothing_to_record(self):
        self.assertEqual(self.run_cli("merge-state").strip(), "none")
        self.assertFalse(os.path.exists(self.state))

    def test_export_takes_last_run_from_state_not_the_profile(self):
        self.save(changed(last_run="2026-10-01T00:00:00Z"))
        self.run_cli("merge-state", "--now", "2026-10-10T06:00:00Z", "2026-10-07T06:00:00Z")
        exported = json.loads(self.run_cli("export"))
        self.assertEqual(exported["last_run"], "2026-10-07T06:00:00Z")
        self.assertEqual(exported["home"], GOOD["home"])

    def test_export_refuses_an_invalid_profile(self):
        self.save(changed(quantity=10))
        with self.assertRaises(SystemExit):
            self.run_cli("export")

    def test_topics_prints_json_and_counts_skips_on_stderr(self):
        path = write("Symbol,Units\nEXAMPLEA,10\n9876543210,4\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = self.run_cli("topics", "--holdings", path)
        self.assertEqual(json.loads(out), [{"name": "EXAMPLEA", "kind": "company"}])
        self.assertIn("1 row", err.getvalue())
        self.assertNotIn("9876543210", err.getvalue())


def xlsx(sheets, inline=False, name="report.xlsx"):
    """A minimal workbook. sheets maps a sheet name to its rows; a row is a
    list of cell values with None for an empty cell, and [] for an empty row."""
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    path = os.path.join(tempfile.mkdtemp(), name)
    strings = []

    def cell(ref, value):
        if isinstance(value, (int, float)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        if inline:
            return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'
        if value not in strings:
            strings.append(value)
        return f'<c r="{ref}" t="s"><v>{strings.index(value)}</v></c>'

    with zipfile.ZipFile(path, "w") as z:
        entries, rels = [], []
        for n, (title, rows) in enumerate(sheets.items(), 1):
            body = ""
            for r, row in enumerate(rows, 1):
                if row:  # an empty row is simply absent, as in a real workbook
                    cells = "".join(cell(f"{chr(65 + c)}{r}", v)
                                    for c, v in enumerate(row) if v is not None)
                    body += f'<row r="{r}">{cells}</row>'
            z.writestr(f"xl/worksheets/sheet{n}.xml",
                       f'<worksheet xmlns="{main}"><sheetData>{body}</sheetData></worksheet>')
            entries.append(f'<sheet name="{title}" sheetId="{n}" r:id="rId{n}"/>')
            rels.append(f'<Relationship Id="rId{n}" Target="worksheets/sheet{n}.xml"/>')
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
                   + "".join(entries) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(rels) + "</Relationships>")
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{main}">'
                   + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
    return path


PLAIN = {"Sheet1": [["Symbol", "Units", "Price"], ["EXAMPLEB", 5, 500], ["EXAMPLEA", 10, 100]]}
# A statement as a platform exports it: a summary sheet, then lines about the
# investor above the table itself and notes below it.
REPORT = {
    "Summary": [["Totals"], ["Units", 15]],
    "Holdings": [[], ["STATEMENT OF HOLDINGS"], ["Name", "Sample Investor"],
                 ["Account", "9876543210"], [], ["Issuer", "Units", "Rate"],
                 ["Example Finance", 5, 9.5], ["Sample Housing", 10, 10.25], ["Total", 15],
                 [], ["Disclaimer:"], ["This statement is for reference only."]],
}


class TestSpreadsheets(unittest.TestCase):
    def test_a_plain_workbook_needs_no_options(self):
        got, skipped = user_profile.topics([xlsx(PLAIN)])
        self.assertEqual([t["name"] for t in got], ["EXAMPLEA", "EXAMPLEB"])
        self.assertEqual(skipped, 0)

    def test_inline_strings_are_read(self):
        got, _ = user_profile.topics([xlsx(PLAIN, inline=True)])
        self.assertEqual([t["name"] for t in got], ["EXAMPLEA", "EXAMPLEB"])

    def test_sheet_and_header_row_reach_a_table_below_the_investor_details(self):
        got, skipped = user_profile.topics([xlsx(REPORT)], kind="issuer", sheet="Holdings",
                                           header_row=6)
        self.assertEqual(got, [{"name": "Example Finance", "kind": "issuer"},
                               {"name": "Sample Housing", "kind": "issuer"}])
        self.assertEqual(skipped, 0)

    def test_the_table_ends_at_the_first_empty_row(self):
        path = write("Symbol,Units\nEXAMPLEA,10\n,\nNotes\nPrices are indicative\n")
        got, _ = user_profile.topics([path])
        self.assertEqual([t["name"] for t in got], ["EXAMPLEA"])

    def test_an_unknown_sheet_names_the_sheets_there_are(self):
        with self.assertRaises(ValueError) as ctx:
            user_profile.topics([xlsx(REPORT)], sheet="Positions")
        self.assertIn("Summary, Holdings", str(ctx.exception))

    def test_a_header_row_past_the_end_is_refused(self):
        with self.assertRaises(ValueError):
            user_profile.topics([xlsx(PLAIN)], header_row=9)

    def test_cells_are_placed_by_their_column(self):
        path = xlsx({"Sheet1": [[None, "Symbol", "Units"], [None, "EXAMPLEA", 10]]})
        got, _ = user_profile.topics([path])
        self.assertEqual([t["name"] for t in got], ["EXAMPLEA"])

    def test_a_file_that_is_not_a_table_is_refused(self):
        path = os.path.join(tempfile.mkdtemp(), "statement.pdf")
        with open(path, "wb") as fh:
            fh.write(b"%PDF-1.7\n\xff\xfe\x00")
        with self.assertRaises(ValueError) as ctx:
            user_profile.topics([path])
        self.assertIn("not a CSV or .xlsx table", str(ctx.exception))

    def test_a_damaged_workbook_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            user_profile.topics([write("not a workbook", name="report.xlsx")])
        self.assertIn("not a readable .xlsx workbook", str(ctx.exception))


class TestLayout(unittest.TestCase):
    def test_lists_the_wide_rows_with_their_row_numbers(self):
        self.assertEqual(user_profile.layout([xlsx(REPORT)]), [
            {"file": "report.xlsx", "sheet": "Holdings", "row": 6, "cells": ["Issuer", "Units", "Rate"]},
            {"file": "report.xlsx", "sheet": "Holdings", "row": 7, "cells": ["Example Finance", "#", "#"]},
            {"file": "report.xlsx", "sheet": "Holdings", "row": 8, "cells": ["Sample Housing", "#", "#"]},
        ])

    def test_identifiers_and_amounts_are_masked(self):
        path = xlsx({"Sheet1": [["Issuer", "Reference", "Amount"], ["Example Finance", "AB9876543210", 150000]]})
        got = user_profile.layout([path])
        self.assertEqual(got[1]["cells"], ["Example Finance", "#", "#"])
        self.assertNotIn("98765", json.dumps(got))

    def test_short_codes_small_amounts_and_dates_are_masked_too(self):
        path = xlsx({"Sheet1": [["Issuer", "Code", "Amount", "Due"],
                                ["Example Finance", "XX001A01AB1", 304.14, "19/11/2026"]]})
        self.assertEqual(user_profile.layout([path])[1]["cells"], ["Example Finance", "#", "#", "#"])

    def test_at_most_five_rows_a_sheet(self):
        rows = [["Symbol", "Units", "Price"]] + [[f"EXAMPLE{c}", 1, 2] for c in "ABCDEFGH"]
        self.assertEqual([r["row"] for r in user_profile.layout([xlsx({"Sheet1": rows})])],
                         [1, 2, 3, 4, 5])

    def test_a_csv_is_one_unnamed_table(self):
        got = user_profile.layout([write("Symbol,Units,Price\nEXAMPLEA,10,100\n")])
        self.assertEqual(got[0], {"file": "book.csv", "sheet": "", "row": 1,
                                  "cells": ["Symbol", "Units", "Price"]})


class TestSpreadsheetCli(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            user_profile.main(list(argv))
        return json.loads(out.getvalue())

    def test_topics_takes_a_sheet_and_a_header_row(self):
        got = self.run_cli("topics", "--holdings", xlsx(REPORT), "--kind", "issuer",
                           "--sheet", "Holdings", "--header-row", "6")
        self.assertEqual([t["name"] for t in got], ["Example Finance", "Sample Housing"])

    def test_layout_prints_the_rows(self):
        got = self.run_cli("layout", "--holdings", xlsx(REPORT))
        self.assertEqual([r["row"] for r in got], [6, 7, 8])


if __name__ == "__main__":
    unittest.main()
