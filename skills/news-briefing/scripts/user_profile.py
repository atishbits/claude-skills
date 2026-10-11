#!/usr/bin/env python3
"""The personal profile a briefing is built from, and the last-run time.

    python3 scripts/user_profile.py [--profile PATH] [--state PATH] COMMAND

    validate       check the profile; prints OK, or one line per problem
    missing        onboarding fields that are neither filled nor declined
    topics         company or issuer names from holdings files, names only
    merge-state    record the latest of several last-run times
    export         the profile plus the last-run time, for the shared copy

The profile may hold only the fields listed here. That is deliberate: it is
what keeps quantities, cost, values and account identifiers out of a file that
is copied to a shared drive."""
import re

from common import parse_ts

ONBOARDING = ("home.country", "home.city", "work.employer", "work.industry", "work.role",
              "interest_topics")
GROUPS = {"home": ("country", "city"), "work": ("employer", "industry", "role")}
FEED_SECTIONS = ("global", "home", "markets")
KINDS = ("company", "sector", "issuer")
TOP_KEYS = ("home", "work", "feeds", "portfolio_topics", "interest_topics", "declined",
            "last_run", "updated")
# An amount or an identifier that slipped into a name field looks like this.
DIGITS = re.compile(r"\d{5,}")


def _is_url(value):
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _text(value, where, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}: must be non-empty text")
    elif DIGITS.search(value):
        errors.append(f"{where}: contains a run of 5 or more digits")


def validate(profile):
    """Problems with the profile, one string each. Empty means valid."""
    if not isinstance(profile, dict):
        return ["profile: must be a JSON object"]
    errors = [f"{key}: unknown field" for key in profile if key not in TOP_KEYS]

    for group, fields in GROUPS.items():
        block = profile.get(group, {})
        if not isinstance(block, dict):
            errors.append(f"{group}: must be an object")
            continue
        for key, value in block.items():
            if key not in fields:
                errors.append(f"{group}.{key}: unknown field")
            else:
                _text(value, f"{group}.{key}", errors)

    feeds = profile.get("feeds", {})
    if not isinstance(feeds, dict):
        errors.append("feeds: must be an object")
    else:
        for key, value in feeds.items():
            if key == "search":
                if not _is_url(value) or "{query}" not in value:
                    errors.append("feeds.search: must be one http(s) URL containing {query}")
            elif key in FEED_SECTIONS:
                if not isinstance(value, list) or not all(_is_url(u) for u in value):
                    errors.append(f"feeds.{key}: must be a list of http(s) URLs")
            else:
                errors.append(f"feeds.{key}: unknown field")

    for key, second in (("portfolio_topics", "kind"), ("interest_topics", "why")):
        items = profile.get(key, [])
        if not isinstance(items, list):
            errors.append(f"{key}: must be a list")
            continue
        for i, item in enumerate(items):
            where = f"{key}[{i}]"
            if not isinstance(item, dict) or set(item) != {"name", second}:
                errors.append(f"{where}: must have exactly name and {second}")
                continue
            _text(item["name"], f"{where}.name", errors)
            if second == "kind":
                if item["kind"] not in KINDS:
                    errors.append(f"{where}.kind: must be one of {', '.join(KINDS)}")
            else:
                _text(item["why"], f"{where}.why", errors)

    declined = profile.get("declined", [])
    if not isinstance(declined, list) or any(d not in ONBOARDING for d in declined):
        errors.append("declined: must be a list drawn from " + ", ".join(ONBOARDING))

    for key in ("last_run", "updated"):
        if key in profile:
            try:
                parse_ts(profile[key])
            except ValueError:
                errors.append(f"{key}: not an ISO 8601 timestamp")
    return errors


def missing(profile):
    """Onboarding fields still to ask about, in asking order."""
    declined = profile.get("declined", [])
    out = []
    for field in ONBOARDING:
        if field in declined:
            continue
        if field == "interest_topics":
            filled = bool(profile.get("interest_topics"))
        else:
            group, key = field.split(".")
            filled = bool(str(profile.get(group, {}).get(key, "")).strip())
        if not filled:
            out.append(field)
    return out
