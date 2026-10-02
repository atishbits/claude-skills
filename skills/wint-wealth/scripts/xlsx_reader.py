#!/usr/bin/env python3
"""Read an .xlsx workbook into plain rows using only the standard library.

Returns {sheet name: [[cell text, ...], ...]} in workbook order. Cells keep
their column position (a gap becomes ""), so a caller can find a header row by
its text and read the columns under it. Values are returned as text exactly as
stored; interpreting them is the caller's job."""
import re
import xml.etree.ElementTree as ET
import zipfile

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _col_index(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _text(cell, shared):
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(NS + "t"))
    value = cell.find(NS + "v")
    if value is None or value.text is None:
        return ""
    return shared[int(value.text)] if kind == "s" else value.text


def _rows(xml_bytes, shared):
    data = ET.fromstring(xml_bytes).find(NS + "sheetData")
    rows = []
    for row in data.findall(NS + "row") if data is not None else []:
        cells = []
        for cell in row.findall(NS + "c"):
            index = _col_index(cell.get("r")) if cell.get("r") else len(cells)
            while len(cells) < index:
                cells.append("")
            cells.append(_text(cell, shared))
        rows.append(cells)
    return rows


def read_workbook(path):
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for item in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(NS + "si"):
                shared.append("".join(t.text or "" for t in item.iter(NS + "t")))
        targets = {rel.get("Id"): rel.get("Target")
                   for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        sheets = {}
        for sheet in ET.fromstring(z.read("xl/workbook.xml")).find(NS + "sheets"):
            target = targets[sheet.get(REL_ID)]
            member = target.lstrip("/") if target.startswith("/") else "xl/" + target
            sheets[sheet.get("name")] = _rows(z.read(member), shared)
        return sheets
