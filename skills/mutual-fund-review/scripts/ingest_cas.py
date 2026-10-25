#!/usr/bin/env python3
"""Bring a registrar Consolidated Account Statement (CAS, detailed, with
transactions) into the ledger.

    python3 scripts/ingest_cas.py --pdf FILE [--password-env VAR] [--root R] [--date D] [--force]
    python3 scripts/ingest_cas.py --text FILE [--root R] [--date D] [--force]

--pdf runs `pdftotext -layout`; the PDF password, if any, is read from the
environment variable named by --password-env and never from the command line.
A CAS carries full history, so its holdings replace any other source's holding
of the same folio and ISIN (source name "cas"). A scheme whose statement opens
with a non-zero unit balance is marked transactions_complete=false: request a
CAS from an earlier start date to fill it.

The layout parsed is the common registrar format: a "Folio No:" line, a
scheme line ending in "ISIN: <ISIN>", "Opening Unit Balance:", transaction
lines "DD-Mon-YYYY  description  amount  units  nav  balance" (negatives in
parentheses), amount-only lines for stamp duty, STT and IDCW paid, and a
"Closing Unit Balance:" line with NAV, cost and market value. Re-check against
a real statement whenever the registrar changes its layout.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

import common
import ledger

NUM = r"\(?-?[\d,]+\.\d+\)?"
RE_PERIOD = re.compile(r"(\d{2}-[A-Za-z]{3}-\d{4})\s+To\s+(\d{2}-[A-Za-z]{3}-\d{4})")
RE_FOLIO = re.compile(r"Folio No\s*:\s*([\w/ ]+?)\s*(?:/\s*\d+)?\s{2,}|Folio No\s*:\s*(\S+)")
RE_SCHEME = re.compile(r"^\s*(?:[A-Z0-9]+-)?(.+?)\s*-\s*ISIN\s*:\s*([A-Z0-9]{12})")
RE_OPEN = re.compile(r"Opening Unit Balance\s*:\s*(" + NUM + ")")
RE_TX = re.compile(r"^\s*(\d{2}-[A-Za-z]{3}-\d{4})\s+(.+?)\s+(" + NUM + r")\s+(" + NUM
                   + r")\s+(" + NUM + r")\s+(" + NUM + r")\s*$")
RE_AMT_ONLY = re.compile(r"^\s*(\d{2}-[A-Za-z]{3}-\d{4})\s+(.+?)\s+(" + NUM + r")\s*$")
RE_CLOSE = re.compile(r"Closing Unit Balance\s*:\s*(" + NUM + r").*?NAV on\s+(\S+)\s*:\s*INR\s*("
                      + NUM + r").*?Cost Value\s*:\s*(?:INR\s*)?(" + NUM
                      + r").*?Market Value on\s+\S+\s*:\s*INR\s*(" + NUM + ")")


def tx_type(desc):
    d = desc.lower()
    # Sales are written "Redemption less TDS, STT", so the sale words come
    # before the bare "stt" that marks the tax line itself.
    rules = [("systematic withdrawal", "sell"), ("swp", "sell"), ("stamp duty", "stamp"),
             ("switch in", "switch_in"), ("switch-in", "switch_in"),
             ("switch out", "switch_out"), ("switch-out", "switch_out"),
             ("redemption", "sell"), ("stt", "stt"),
             ("reinvest", "dividend_reinvest"), ("idcw paid", "dividend_payout"),
             ("dividend paid", "dividend_payout"), ("payout", "dividend_payout"),
             ("systematic", "sip"), ("sip", "sip"), ("purchase", "buy")]
    for word, t in rules:
        if word in d:
            return t
    raise ValueError(f"unrecognised CAS transaction: {desc!r}")


def _scheme_attrs(name):
    low = name.lower()
    return {"plan": "direct" if "direct" in low else "regular",
            "option": "idcw" if ("idcw" in low or "dividend" in low) else "growth",
            "scheme": re.sub(r"\s*\((?:Non-)?Demat\)\s*", " ", name).strip()}


def parse_cas_text(text, owner="self"):
    meta = {"period_from": None, "period_to": None}
    m = RE_PERIOD.search(text)
    if m:
        meta["period_from"], meta["period_to"] = (common.parse_date(x) for x in m.groups())
    holdings, txs = [], []
    folio = None
    cur = None
    raw_seen = {}
    for line in text.splitlines():
        if "Folio No" in line:
            fm = RE_FOLIO.search(line)
            folio = (fm.group(1) or fm.group(2)).strip() if fm else None
            continue
        sm = RE_SCHEME.search(line)
        if sm:
            cur = {"isin": sm.group(2), "folio_ref": common.folio_ref(folio), "opening": 0.0,
                   **_scheme_attrs(sm.group(1))}
            continue
        if cur is None:
            continue
        om = RE_OPEN.search(line)
        if om:
            cur["opening"] = abs(common.parse_num(om.group(1)) or 0.0)
            continue
        cm = RE_CLOSE.search(line)
        if cm:
            units, nav_date, nav, cost, value = cm.groups()
            holdings.append({"source": "cas", "owner": owner, "folio_ref": cur["folio_ref"],
                             "isin": cur["isin"], "scheme": cur["scheme"], "plan": cur["plan"],
                             "option": cur["option"], "units": common.parse_num(units),
                             "invested": common.parse_num(cost),
                             "current_value": common.parse_num(value),
                             "nav": common.parse_num(nav),
                             "nav_date": common.parse_date(nav_date.rstrip(":")),
                             "opening_units": cur["opening"],
                             "transactions_complete": cur["opening"] <= ledger.UNIT_TOLERANCE})
            cur = None
            continue
        tm = RE_TX.match(line)
        am = None if tm else RE_AMT_ONLY.match(line)
        if not (tm or am):
            continue
        date, desc = (tm or am).group(1), (tm or am).group(2).strip()
        amount = abs(common.parse_num((tm or am).group(3)))
        units = abs(common.parse_num(tm.group(4))) if tm else ""
        nav = common.parse_num(tm.group(5)) if tm else ""
        if re.search(r"rejection|reversal", desc, re.I):
            # A bounced instalment: the purchase it undoes never happened.
            match = [i for i, x in enumerate(txs)
                     if (x["folio_ref"], x["isin"]) == (cur["folio_ref"], cur["isin"])
                     and x["type"] in ("buy", "sip") and x["units"] == units
                     and x["amount"] == amount]
            if not match:
                raise ValueError(f"{date} {desc!r}: no purchase of {units} units to cancel")
            del txs[match[-1]]
            continue
        raw = f"{cur['folio_ref']}|{cur['isin']}|{line.strip()}"
        n = raw_seen.get(raw, 0)
        raw_seen[raw] = n + 1
        txs.append({"date": common.parse_date(date), "source": "cas", "owner": owner,
                    "folio_ref": cur["folio_ref"], "isin": cur["isin"], "amfi_code": "",
                    "scheme": cur["scheme"], "plan": cur["plan"], "option": cur["option"],
                    "type": tx_type(desc), "amount": amount, "units": units, "nav": nav,
                    "row_id": ledger.make_row_id("cas", raw, n)})
    return holdings, txs, meta


def pdf_to_text(path, password=None):
    cmd = ["pdftotext", "-layout"]
    if password:
        cmd += ["-upw", password]
    cmd += [path, "-"]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pdf")
    g.add_argument("--text")
    ap.add_argument("--password-env")
    ap.add_argument("--root")
    ap.add_argument("--date")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    root = common.resolve_root(a.root)
    owner = common.load_profile(root).get("owner", "self")
    if a.pdf:
        pw = os.environ.get(a.password_env) if a.password_env else None
        text = pdf_to_text(a.pdf, pw)
    else:
        with open(a.text) as f:
            text = f.read()
    holdings, txs, meta = parse_cas_text(text, owner)
    if not holdings:
        raise ValueError("no schemes found: is this a detailed CAS with transactions?")
    date = a.date or meta["period_to"] or dt.date.today().isoformat()
    complete = all(h["transactions_complete"] for h in holdings)
    out = ledger.ingest(root, "cas", holdings, txs, date, complete, force=a.force, supersede=True)
    out["statement"] = meta
    out["incomplete_history"] = [h["scheme"] for h in holdings if not h["transactions_complete"]]
    if argv is None:
        print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        sys.exit(f"error: {e}")
