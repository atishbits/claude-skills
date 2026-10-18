import importlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestCacheRoot(unittest.TestCase):
    def test_cache_dir_follows_portfolio_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["PORTFOLIO_ROOT"] = tmp
            try:
                import nse_disclosures
                mod = importlib.reload(nse_disclosures)
                self.assertEqual(mod.CACHE_DIR,
                                 os.path.join(os.path.abspath(tmp), "data", "skill-data", ".cache"))
            finally:
                del os.environ["PORTFOLIO_ROOT"]


if __name__ == "__main__":
    unittest.main()
