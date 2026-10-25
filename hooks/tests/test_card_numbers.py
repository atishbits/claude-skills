import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import card_numbers as c  # noqa: E402

# Published test numbers from card networks' developer docs (not real accounts),
# built at runtime so this file itself never holds a card-shaped literal.
VISA_TEST = "4111" + "1" * 12
MC_TEST = "5555" * 3 + "4444"
AMEX_TEST = "3782" + "822463" + "10005"
SP = lambda n, sep: sep.join(n[i:i + 4] for i in range(0, len(n), 4))


class TestCardNumbers(unittest.TestCase):
    def test_luhn_valid_numbers_found(self):
        self.assertEqual(c.find(f"x {VISA_TEST} y"), ["1111"])
        self.assertEqual(c.find(MC_TEST), ["4444"])
        self.assertEqual(c.find(AMEX_TEST), ["0005"])

    def test_grouped_numbers_found(self):
        self.assertEqual(c.find(SP(MC_TEST, " ")), ["4444"])
        self.assertEqual(c.find(SP(MC_TEST, "-")), ["4444"])

    def test_checksum_failures_and_non_card_starts_pass(self):
        self.assertEqual(c.find("4000111122223333"), [])        # fails Luhn
        self.assertEqual(c.find("1111222233334444"), [])        # starts like no card
        self.assertEqual(c.find("4444444444444444"), [])        # one repeated digit

    def test_ids_and_hashes_pass(self):
        # Invented shapes of what statements carry: UPI and NEFT references, a
        # hash, a timestamp, an amount.
        for s in ["UPI/PAYEE/123456789012/ABC1def2", "202601011200", "NEFT-REF-0001",
                  "sha 4" + "0a1b2c3d" * 7 + "4567890",
                  "2026-01-01T10:00:00.000Z", "amount 100000.50"]:
            self.assertEqual(c.find(s), [], s)

    def test_masked_statement_numbers_found(self):
        self.assertEqual(c.find("card 4111" + "X" * 8 + "1234 billed"), ["1234"])
        self.assertEqual(c.find("5555 55" + "** ****" + " 9876"), ["9876"])
        self.assertEqual(c.find("ending XXXX XXXX XXXX 1234"), [])   # no leading digits

    def test_cli_hides_number(self):
        script = os.path.join(HERE, "..", "card_numbers.py")
        out = subprocess.run([sys.executable, script], input=f"+ x {VISA_TEST}\n",
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        self.assertNotIn(VISA_TEST, out.stdout)
        self.assertIn("1111", out.stdout)
        clean = subprocess.run([sys.executable, script], input="+ nothing here\n",
                               capture_output=True, text=True)
        self.assertEqual((clean.returncode, clean.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
