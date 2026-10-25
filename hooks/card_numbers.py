#!/usr/bin/env python3
"""Find payment-card numbers in text, for hooks/pre-commit.

    some-text | python3 hooks/card_numbers.py      # exit 1 and list them if any

Flags two shapes:
  - a full number: 13-19 digits, optionally grouped by single spaces or
    dashes, starting like a card (2-6 or 8) and passing the Luhn checksum
    every real card number carries;
  - a masked number as statements print it: 4-6 digits, 4-9 X or *, then the
    last 4 digits (e.g. 4XXXXXXXXXXX1234 with real leading digits).

Invented card numbers in tests must therefore fail the checksum. Output shows
only the last 4 digits of what it found, so the hook never echoes a number.
"""
import re
import sys

FULL = re.compile(r"(?<![0-9A-Za-z])[2-68](?:[ -]?\d){12,18}(?![0-9A-Za-z])")
MASKED = re.compile(r"(?<![0-9A-Za-z])\d{4}[ -]?\d{0,2}(?:[ -]?[Xx*]){4,9}[ -]?\d{4}(?![0-9A-Za-z])")


def luhn_ok(digits):
    total = 0
    for i, c in enumerate(reversed(digits)):
        d = int(c)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find(text):
    """Last 4 digits of each card-like number in text."""
    out = []
    for m in FULL.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and len(set(digits)) > 1 and luhn_ok(digits):
            out.append(digits[-4:])
    for m in MASKED.finditer(text):
        out.append(re.sub(r"\D", "", m.group())[-4:])
    return out


def main():
    found = find(sys.stdin.read())
    if found:
        print(", ".join("…" + x for x in found))
        sys.exit(1)


if __name__ == "__main__":
    main()
