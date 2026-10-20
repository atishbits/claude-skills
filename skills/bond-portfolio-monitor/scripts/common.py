#!/usr/bin/env python3
"""Helpers shared by every bond-portfolio-monitor script: where data lives, loading the
committed config and the user's profile, and parsing the date and number
formats the holdings report uses. No script here touches the network."""
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROFILE_KEYS = ["tax_slab_pct", "min_rating", "max_tenure_months", "min_post_tax_ytm_pct",
                "max_issuer_share_pct", "max_rating_bucket_share_pct", "allow_unsecured",
                "allow_subordinated", "prefer_monthly_income", "lookahead_days"]


ROOT_ENV = "BOND_ROOT"


def resolve_root(arg=None):
    """--root, then $BOND_ROOT, then the working directory. The skill's own
    folder is a root only if its data/ already exists (the skill run from a
    checkout of its repo, where data/ is gitignored): installed as a plugin,
    the folder is replaced on update, and a data/ made there would be lost."""
    root = os.path.abspath(arg or os.environ.get(ROOT_ENV) or os.getcwd())
    if (os.path.realpath(root) == os.path.realpath(SKILL_DIR)
            and not os.path.isdir(os.path.join(root, "data"))):
        sys.exit(f"No working folder: {root} is the skill's own folder and has no data/. "
                 f"Pass --root with the folder that holds data/, or set ${ROOT_ENV}.")
    return root


_NAME_DATE = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})")


def name_date(path):
    """The first YYYY-MM-DD (or YYYYMMDD) in a file's name, else None."""
    m = _NAME_DATE.search(os.path.basename(path))
    if not m:
        return None
    try:
        return dt.date(*map(int, m.groups())).isoformat()
    except ValueError:
        return None


def newest_by_name_date(paths):
    """The newest file by the date in its name, falling back to its
    modification date when the name has none; the modification time breaks a
    tie. A file copied down from cloud storage gets a fresh modification time,
    so the name is the better witness to which report is newest. Two names on
    one date compare as text, which orders the capture's own timestamps."""
    def key(path):
        mtime, day = os.path.getmtime(path), name_date(path)
        return (day or dt.date.fromtimestamp(mtime).isoformat(),
                os.path.basename(path) if day else "", mtime)
    return max(paths, key=key)


def where(root=None):
    """What `common.py --where` prints: the working root, where it came from,
    and how old the newest holdings snapshot and listings capture in it are,
    so a run that cannot fetch fresh data can say what it is working from."""
    if root is None and os.environ.get(ROOT_ENV):
        root, source = os.path.abspath(os.environ[ROOT_ENV]), ROOT_ENV
    elif root is None and os.path.isdir(os.path.join(SKILL_DIR, "data")):
        root, source = SKILL_DIR, "skill data/"
    elif root is None:
        return {"root": None, "from": None, "exists": False}
    else:
        root, source = os.path.abspath(root), "--root"
    data = os.path.join(root, "data")
    out = {"root": root, "from": source, "exists": os.path.isdir(data)}
    if out["exists"]:
        skill_data = os.path.join(data, "skill-data")
        snaps = dated_files(skill_data, "snapshot-")
        caps = dated_files(skill_data, "listings-")
        out.update({
            "profile": os.path.isfile(os.path.join(data, "profile.json")),
            "notes": os.path.isfile(os.path.join(data, "notes.md")),
            "newest_snapshot": os.path.basename(snaps[-1]) if snaps else None,
            "newest_listings": os.path.basename(caps[-1]) if caps else None,
        })
    return out


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


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_profile(profile, config=None):
    missing = [k for k in PROFILE_KEYS if k not in profile]
    if missing:
        raise ValueError(f"profile.json is missing: {missing}. See profile-template.json.")
    order = (config or load_config())["rating_order"]
    problems = []
    if profile["min_rating"] not in order:
        problems.append(f"min_rating {profile['min_rating']!r} must be one of {order}")
    for key in ("tax_slab_pct", "max_tenure_months", "min_post_tax_ytm_pct",
                "max_issuer_share_pct", "lookahead_days"):
        if not _is_number(profile[key]):
            problems.append(f"{key} must be a number")
    for key in ("allow_unsecured", "allow_subordinated", "prefer_monthly_income"):
        if not isinstance(profile[key], bool):
            problems.append(f"{key} must be true or false")
    if "effective_tax_rate_pct" in profile and not _is_number(profile["effective_tax_rate_pct"]):
        problems.append("effective_tax_rate_pct must be a number")
    if "total_investable" in profile and not (
            _is_number(profile["total_investable"]) and profile["total_investable"] > 0):
        problems.append("total_investable must be a number above zero")
    if "tax_multiplier" in profile and not (
            _is_number(profile["tax_multiplier"]) and profile["tax_multiplier"] >= 1):
        problems.append("tax_multiplier must be a number of 1 or more")
    if "annual_investment_budget" in profile and not (
            _is_number(profile["annual_investment_budget"])
            and profile["annual_investment_budget"] > 0):
        problems.append("annual_investment_budget must be a number above zero")
    if "min_ytm_pct" in profile and not _is_number(profile["min_ytm_pct"]):
        problems.append("min_ytm_pct must be a number")
    caps = profile["max_rating_bucket_share_pct"]
    if not isinstance(caps, dict) or not all(_is_number(v) for v in caps.values()):
        problems.append("max_rating_bucket_share_pct must map a rating bucket to a number")
    if problems:
        raise ValueError("profile.json: " + "; ".join(problems))
    return profile


def tax_rate(profile):
    """The rate applied to slab-taxed income: the effective rate (slab plus cess
    and any surcharge) if the profile gives one, otherwise the bare slab."""
    return profile.get("effective_tax_rate_pct", profile["tax_slab_pct"])


def financial_year_start(date_iso):
    """1 April of the Indian financial year that `date_iso` falls in."""
    year, month = int(date_iso[:4]), int(date_iso[5:7])
    return f"{year if month >= 4 else year - 1}-04-01"


def cap_basis(profile):
    """What the issuer and rating-bucket caps are a share of."""
    total = profile.get("total_investable")
    return (f"total investable of {total} (profile)" if total
            else "the bond portfolio alone (set total_investable in the profile to measure "
                 "caps against everything you invest)")


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


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] != ["--where"] or len(args) > 2:
        sys.exit("usage: common.py --where [ROOT]")
    print(json.dumps(where(args[1] if len(args) == 2 else None), indent=2))
