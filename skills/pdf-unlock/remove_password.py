#!/usr/bin/env python3
"""Remove the open password from an encrypted PDF, given the correct password."""
import argparse
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to the password-protected PDF")
    parser.add_argument("password", help="The PDF's open password")
    parser.add_argument(
        "-o", "--output", type=Path,
        help="Output path (default: <input>_unlocked.pdf next to the input)",
    )
    args = parser.parse_args()

    output = args.output or args.input.with_name(args.input.stem + "_unlocked.pdf")

    reader = PdfReader(args.input)
    if reader.is_encrypted:
        if reader.decrypt(args.password) == 0:
            sys.exit(f"Wrong password for {args.input}")

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    with open(output, "wb") as f:
        writer.write(f)

    print(f"Wrote {output} ({len(reader.pages)} pages)")


if __name__ == "__main__":
    main()
