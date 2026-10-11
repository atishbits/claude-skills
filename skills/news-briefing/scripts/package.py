#!/usr/bin/env python3
"""Build the bundle to upload where the skill cannot be installed from disk.

    python3 scripts/package.py [--out PATH]

The archive holds the skill folder without data/ (the profile, the last-run
time, any API key), without caches and without the tests. It prints what went
in, so the absence of anything personal can be seen before uploading."""
import argparse
import os
import tempfile
import zipfile

EXCLUDED_DIRS = ("data", "__pycache__", "tests")


def build_zip(skill_dir, out_path):
    skill_dir = os.path.realpath(skill_dir)
    if not os.path.isfile(os.path.join(skill_dir, "SKILL.md")):
        raise ValueError(f"{skill_dir} has no SKILL.md")
    name = os.path.basename(skill_dir)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, dirs, files in os.walk(skill_dir):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
            for filename in sorted(files):
                if filename.endswith(".pyc"):
                    continue
                full = os.path.join(root, filename)
                archive.write(full, "/".join([name, *os.path.relpath(full, skill_dir).split(os.sep)]))
        return archive.namelist()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "news-briefing.zip"))
    args = ap.parse_args(argv)
    skill_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    for member in build_zip(skill_dir, args.out):
        print("  " + member)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
