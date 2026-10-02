#!/usr/bin/env python3
"""Helpers shared by every wint-wealth script: where data lives, loading the
committed config and the user's profile, and parsing the date and number
formats the Master Report uses. No script here touches the network."""
import datetime as dt
import glob
import hashlib
import json
import os

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROFILE_KEYS = ["tax_slab_pct", "min_rating", "max_tenure_months", "min_post_tax_ytm_pct",
                "max_issuer_share_pct", "max_rating_bucket_share_pct", "allow_unsecured",
                "allow_subordinated", "prefer_monthly_income", "lookahead_days"]


def resolve_root(arg=None):
    """--root, then $WINT_ROOT, then the working directory."""
    return os.path.abspath(arg or os.environ.get("WINT_ROOT") or os.getcwd())


def skill_data_dir(root):
    path = os.path.join(root, "data", "skill-data")
    os.makedirs(path, exist_ok=True)
    return path


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def load_config(path=None):
    return load_json(path or os.path.join(SKILL_DIR, "config.json"))


def validate_profile(profile):
    missing = [k for k in PROFILE_KEYS if k not in profile]
    if missing:
        raise ValueError(f"profile.json is missing: {missing}. See profile-template.json.")
    return profile


def load_profile(root):
    path = os.path.join(root, "data", "profile.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No {path}. Copy profile-template.json from the skill folder to data/profile.json "
            "and set your own limits.")
    return validate_profile(load_json(path))


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def parse_date(text):
    text = (text or "").strip()
    if text in ("", "-"):
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {text!r}")


def parse_num(text):
    text = str(text if text is not None else "").strip().replace(",", "").replace("₹", "")
    if text in ("", "-"):
        return None
    if text.endswith("%"):
        text = text[:-1]
    return float(text)


def months_between(start_iso, end_iso):
    days = (dt.date.fromisoformat(end_iso) - dt.date.fromisoformat(start_iso)).days
    return round(days / 30.4375, 1)


def dated_files(directory, prefix):
    """Paths named <prefix><sortable date>.json, oldest first."""
    return sorted(glob.glob(os.path.join(directory, prefix + "*.json")))


def stale_config_warnings(config, today_iso):
    limit = config.get("config_max_age_months", 12)
    warnings = []

    def walk(node, path):
        if not isinstance(node, dict):
            return
        as_of = node.get("as_of")
        if as_of and months_between(as_of, today_iso) > limit:
            warnings.append(f"config entry {path} is as of {as_of}; re-verify it")
        for key, value in node.items():
            walk(value, f"{path}.{key}" if path else key)

    walk(config, "")
    return warnings
