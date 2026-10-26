#!/usr/bin/env python3
"""Open a built deck in a headless Chrome or Chromium at phone and laptop
sizes and report which slides need scrolling (content taller or wider than
the screen). Optionally saves one screenshot per slide to look at.

    python3 scripts/check_layout.py DECK.html [--sizes 390x844,1366x768]
                                    [--shots DIR] [--slides 1,4,7]

Prints JSON: {"browser": ..., "sizes": [{"size", "overflow": [{"slide",
"overflow_px", "overflow_x_px"}]}], "shots": [...]}. With no browser
installed it prints {"browser": null} and exits 0, so the build never
depends on one. Set $CHROME to pick the binary.
"""
import argparse
import html as htmllib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

CANDIDATES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
TOLERANCE_PX = 4


def find_browser():
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    for c in CANDIDATES:
        p = shutil.which(c) or (c if os.path.isabs(c) and os.path.exists(c) else None)
        if p:
            return p
    return None


def parse_sizes(text):
    out = []
    for part in text.split(","):
        m = re.fullmatch(r"\s*(\d+)x(\d+)\s*", part)
        if not m:
            raise ValueError(f"size {part!r} must look like 390x844")
        out.append((int(m.group(1)), int(m.group(2))))
    return out


def parse_report(dom):
    """The layout-check JSON the deck writes into a <meta> when opened with
    ?layoutcheck=1, from the dumped DOM; None when absent."""
    m = re.search(r'<meta name="layout-check" content="([^"]*)"', dom)
    if not m:
        return None
    return json.loads(htmllib.unescape(m.group(1)))


def overflowing(report, tolerance=TOLERANCE_PX):
    return [s for s in report.get("slides", [])
            if s.get("overflow_px", 0) > tolerance or s.get("overflow_x_px", 0) > tolerance]


def _run(browser, args, timeout=60):
    base = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--hide-scrollbars", "--force-device-scale-factor=1", "--virtual-time-budget=2000"]
    return subprocess.run(base + args, capture_output=True, text=True, timeout=timeout)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--sizes", default="390x844,1366x768")
    ap.add_argument("--shots", help="folder for screenshots, one per slide and size")
    ap.add_argument("--slides", help="only these slide numbers for screenshots, e.g. 1,3,5")
    a = ap.parse_args(argv)
    browser = find_browser()
    if not browser:
        print(json.dumps({"browser": None, "note": "no Chrome or Chromium found; layout not checked"}))
        return 0
    url = pathlib.Path(os.path.abspath(a.html)).as_uri()
    out = {"browser": browser, "sizes": [], "shots": []}
    for w, h in parse_sizes(a.sizes):
        r = _run(browser, [f"--window-size={w},{h}", "--dump-dom", url + "?layoutcheck=1"])
        rep = parse_report(r.stdout)
        if rep is None:
            out["sizes"].append({"size": f"{w}x{h}", "error": (r.stderr or "no layout report")[-300:]})
            continue
        out["sizes"].append({"size": f"{w}x{h}", "slides": len(rep["slides"]), "overflow": overflowing(rep)})
        if a.shots:
            os.makedirs(a.shots, exist_ok=True)
            n = len(rep["slides"])
            want = [int(x) for x in a.slides.split(",")] if a.slides else range(1, n + 1)
            for k in want:
                path = os.path.join(os.path.abspath(a.shots), f"slide{k:02d}-{w}x{h}.png")
                _run(browser, [f"--window-size={w},{h}", f"--screenshot={path}", f"{url}?shot=1#{k}"])
                if os.path.exists(path):
                    out["shots"].append(path)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
