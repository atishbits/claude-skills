#!/usr/bin/env python3
"""Read a statement file into rows of text cells: CSV, XLSX (standard library),
old binary XLS (needs xlrd, optional), PDF (via pdftotext -layout) or text.
A PDF or text file gives one single-cell row per line."""
import csv
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _xlsx(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        sheet = "xl/worksheets/sheet1.xml"
        if sheet not in names:
            sheet = sorted(n for n in names if n.startswith("xl/worksheets/sheet"))[0]
        rows = []
        for row in ET.fromstring(z.read(sheet)).iter(NS + "row"):
            cells = {}
            for c in row.iter(NS + "c"):
                t = c.get("t")
                if t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(NS + "t"))
                else:
                    v = c.find(NS + "v")
                    val = v.text if v is not None and v.text is not None else ""
                    if t == "s" and val != "":
                        val = shared[int(val)]
                cells[_col(c.get("r"))] = val
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
        return rows


def _xls(path, root):
    if root:
        vendor = os.path.join(root, "data", "vendor")
        if os.path.isdir(vendor) and vendor not in sys.path:
            sys.path.insert(0, vendor)
    try:
        import xlrd
    except ImportError:
        sys.exit("This is an old binary .xls file, which needs the xlrd library. "
                 "Download the statement as CSV/XLSX/PDF instead, or run "
                 "pip install --target <root>/data/vendor xlrd")
    s = xlrd.open_workbook(path).sheet_by_index(0)
    out = []
    for r in range(s.nrows):
        row = []
        for c in s.row(r):
            v = c.value
            row.append(("%.2f" % v if isinstance(v, float) and v != int(v) else
                        str(int(v)) if isinstance(v, float) else str(v)))
        out.append(row)
    return out


def read_rows(path, root=None):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xls":
        return _xls(path, root)
    if ext == ".xlsx":
        return _xlsx(path)
    if ext == ".pdf":
        text = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True,
                              text=True, check=True).stdout
        return [[line] for line in text.splitlines()]
    if ext == ".txt":
        with open(path, encoding="utf-8", errors="replace") as f:
            return [[line.rstrip("\n")] for line in f]
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        return [[c.strip() for c in row] for row in csv.reader(f)]
