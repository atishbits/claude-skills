import os
import sys
import unittest

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import nse_index  # noqa: E402


class TestParseConstituents(unittest.TestCase):
    def test_normal_payload_with_priority_rows_and_constituents(self):
        """Priority 1 row is the index summary; priority 0 are constituents."""
        payload = {
            "data": [
                {"symbol": "INFY", "priority": 1, "name": "Nifty 50"},  # summary row
                {"symbol": "TCS", "priority": 0},
                {"symbol": "WIPRO", "priority": 0},
                {"symbol": "BAJFINANCE"},  # no priority key
            ]
        }
        result = nse_index.parse_constituents(payload)
        # Should exclude priority==1, include others, sorted
        self.assertEqual(result, ["BAJFINANCE", "TCS", "WIPRO"])

    def test_normalizes_lowercase_and_whitespace(self):
        """Symbols are uppercased and whitespace-stripped."""
        payload = {
            "data": [
                {"symbol": "  tcs  ", "priority": 0},
                {"symbol": " infy ", "priority": 0},
            ]
        }
        result = nse_index.parse_constituents(payload)
        self.assertEqual(result, ["INFY", "TCS"])

    def test_empty_data_list(self):
        """Empty data list returns empty result."""
        payload = {"data": []}
        result = nse_index.parse_constituents(payload)
        self.assertEqual(result, [])

    def test_payload_is_none(self):
        """None payload returns empty result."""
        result = nse_index.parse_constituents(None)
        self.assertEqual(result, [])

    def test_payload_missing_data_key(self):
        """Payload without 'data' key returns empty result."""
        payload = {"some_other_key": "value"}
        result = nse_index.parse_constituents(payload)
        self.assertEqual(result, [])

    def test_duplicate_symbols_deduped(self):
        """Duplicate symbols across rows appear once."""
        payload = {
            "data": [
                {"symbol": "TCS", "priority": 0},
                {"symbol": "TCS", "priority": 0},  # duplicate
                {"symbol": "INFY", "priority": 0},
            ]
        }
        result = nse_index.parse_constituents(payload)
        self.assertEqual(result, ["INFY", "TCS"])

    def test_skips_blank_symbols(self):
        """Rows with blank or missing symbols are skipped."""
        payload = {
            "data": [
                {"symbol": "TCS", "priority": 0},
                {"symbol": "", "priority": 0},  # blank
                {"symbol": "   ", "priority": 0},  # whitespace only
                {"priority": 0},  # missing symbol
                {"symbol": "INFY", "priority": 0},
            ]
        }
        result = nse_index.parse_constituents(payload)
        self.assertEqual(result, ["INFY", "TCS"])

    def test_returns_sorted_list(self):
        """Result is always sorted."""
        payload = {
            "data": [
                {"symbol": "ZEEL", "priority": 0},
                {"symbol": "BAJAJ", "priority": 0},
                {"symbol": "INFY", "priority": 0},
            ]
        }
        result = nse_index.parse_constituents(payload)
        self.assertEqual(result, ["BAJAJ", "INFY", "ZEEL"])

    def test_data_key_is_none(self):
        """data key with None value is handled gracefully."""
        payload = {"data": None}
        result = nse_index.parse_constituents(payload)
        self.assertEqual(result, [])

    def test_non_dict_payload_returns_empty(self):
        """A list, string or number payload returns [] rather than raising."""
        for payload in (["ZENTRO"], "ZENTRO", 42):
            self.assertEqual(nse_index.parse_constituents(payload), [])

    def test_data_not_a_list_returns_empty(self):
        self.assertEqual(nse_index.parse_constituents({"data": "ZENTRO"}), [])
        self.assertEqual(nse_index.parse_constituents({"data": {"symbol": "ZENTRO"}}), [])

    def test_non_dict_rows_and_non_string_symbols_skipped(self):
        payload = {
            "data": [
                "ZENTRO",                          # not a dict
                None,                              # not a dict
                ["QORVIK"],                        # not a dict
                {"symbol": 123, "priority": 0},    # non-string symbol
                {"symbol": None, "priority": 0},   # null symbol
                {"symbol": "MALBEX", "priority": 0},
            ]
        }
        self.assertEqual(nse_index.parse_constituents(payload), ["MALBEX"])


class FakeResponse:
    def __init__(self, status_code=200, body=None, bad_json=False):
        self.status_code = status_code
        self._body = body
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            # What requests itself raises on a non-JSON body.
            raise requests.JSONDecodeError("Expecting value", "<html>", 0)
        return self._body


class FakeSession:
    def __init__(self, responses=None, exc=None):
        self.headers = {}
        self._responses = list(responses or [])
        self._exc = exc

    def get(self, url, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._responses.pop(0)


class TestFetchConstituents(unittest.TestCase):
    """fetch_constituents against a fake session -- no network."""

    def test_success_parses_payload(self):
        session = FakeSession([FakeResponse(), FakeResponse(body={"data": [{"symbol": "ZENTRO"}]})])
        self.assertEqual(nse_index.fetch_constituents("NIFTY TEST 50", session=session), ["ZENTRO"])

    def test_bad_json_reports_parse_failure_not_request_failure(self):
        session = FakeSession([FakeResponse(), FakeResponse(bad_json=True)])
        with self.assertRaises(RuntimeError) as ctx:
            nse_index.fetch_constituents("NIFTY TEST 50", session=session)
        self.assertIn("failed to parse JSON", str(ctx.exception))
        self.assertNotIn("Request failed", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, ValueError)

    def test_request_exception_is_chained(self):
        err = requests.ConnectionError("connection reset")
        session = FakeSession(exc=err)
        with self.assertRaises(RuntimeError) as ctx:
            nse_index.fetch_constituents("NIFTY TEST 50", session=session)
        self.assertIn("Request failed", str(ctx.exception))
        self.assertIs(ctx.exception.__cause__, err)

    def test_non_200_names_endpoint_and_status(self):
        session = FakeSession([FakeResponse(), FakeResponse(status_code=401)])
        with self.assertRaises(RuntimeError) as ctx:
            nse_index.fetch_constituents("NIFTY TEST 50", session=session)
        self.assertIn("equity-stockIndices: HTTP 401", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
