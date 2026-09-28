import os
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
