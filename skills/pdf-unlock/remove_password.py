#!/usr/bin/env python3
"""Remove the open password from an encrypted PDF, given the correct password.

Uses pypdf. If pypdf is not installed but the `qpdf` command is, uses that
instead. If neither is available, or pypdf lacks the AES backend a PDF needs,
it exits with status 3 and says what to install.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

MISSING = 3
INSTALL_HINT = "pip install 'pypdf[crypto]'"


def unlock_with_pypdf(pypdf, src: Path, password: str, dst: Path) -> int:
    from pypdf.errors import DependencyError

    try:
        reader = pypdf.PdfReader(src)
        if reader.is_encrypted and reader.decrypt(password) == 0:
            sys.exit(f"Wrong password for {src}")
        writer = pypdf.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
    except DependencyError as e:
        print(f"{src} uses AES encryption, which needs an extra package ({e}).\n"
              f"Install it with: {INSTALL_HINT}", file=sys.stderr)
        return MISSING

    with open(dst, "wb") as f:
        writer.write(f)
    print(f"Wrote {dst} ({len(reader.pages)} pages)")
    return 0


def unlock_with_qpdf(qpdf: str, src: Path, password: str, dst: Path) -> int:
    proc = subprocess.run(
        [qpdf, f"--password={password}", "--decrypt", str(src), str(dst)],
        capture_output=True, text=True)
    # qpdf exits 3 for success with warnings.
    if proc.returncode not in (0, 3):
        if "invalid password" in proc.stderr.lower():
            sys.exit(f"Wrong password for {src}")
        sys.exit(f"qpdf failed on {src}: {proc.stderr.strip()}")
    print(f"Wrote {dst} (via qpdf)")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="Path to the password-protected PDF")
    parser.add_argument("password", help="The PDF's open password")
    parser.add_argument(
        "-o", "--output", type=Path,
        help="Output path (default: <input>_unlocked.pdf next to the input)",
    )
    args = parser.parse_args()

    output = args.output or args.input.with_name(args.input.stem + "_unlocked.pdf")

    try:
        import pypdf
    except ImportError:
        pypdf = None
    if pypdf is not None:
        return unlock_with_pypdf(pypdf, args.input, args.password, output)

    qpdf = shutil.which("qpdf")
    if qpdf:
        return unlock_with_qpdf(qpdf, args.input, args.password, output)

    print(f"Neither pypdf nor qpdf is available.\nInstall pypdf with: {INSTALL_HINT}",
          file=sys.stderr)
    return MISSING


if __name__ == "__main__":
    sys.exit(main())
