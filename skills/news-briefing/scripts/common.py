#!/usr/bin/env python3
"""Shared by the news-briefing scripts: where the personal data folder is, and
UTC timestamps. Everything personal lives in that folder, which is gitignored."""
import json
import os
from datetime import datetime, timezone


def data_dir():
    """$NEWS_BRIEFING_DATA, else the data/ folder beside scripts/."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.environ.get("NEWS_BRIEFING_DATA") or os.path.join(here, "..", "data"))


def parse_ts(text):
    """ISO 8601 text -> aware UTC datetime. A value with no offset is taken as UTC."""
    if not isinstance(text, str):
        raise ValueError("timestamp must be text")
    s = text.strip()
    if s[-1:] in ("Z", "z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_ts(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def read_last_run(state_path):
    """The last-run time in state.json, or None if the file is absent or unreadable.
    A damaged state file must never stop a briefing: it just means a full window."""
    try:
        with open(state_path, encoding="utf-8") as fh:
            return parse_ts(json.load(fh)["last_run"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
