#!/usr/bin/env python3
"""Screen the bonds currently on sale against the investor's profile.

    python3 scripts/screen_listings.py [--cash AMOUNT] [--allow-stale] [--root PATH]

Reads the newest listings capture, the newest snapshot, bond-facts.json and
data/profile.json. Steps, in order:

  1. Refuse a capture older than config.json's listings_max_age_hours:
     listings sell out fast. --allow-stale runs anyway and marks the output.
  2. Hard filters from the profile: rating floor, tenure ceiling, minimum
     post-tax YTM, no subordinated or unsecured paper unless allowed, not sold
     out, and (when cash is known) a minimum investment that fits.
  3. Post-tax YTM = YTM x (1 - tax slab), since bond interest is taxed at slab.
  4. Concentration: how much could be bought before the issuer or its rating
     bucket goes over the profile's cap. Nothing fits -> rejected.
  5. Rank within risk buckets: better rating first, then secured before
     unsecured, senior before subordinated; only then monthly income (if the
     profile prefers it) and post-tax YTM. Never by YTM across the whole list.

--cash defaults to the principal and interest due within the profile's
lookahead_days (cashflows.idle_cash), so the shortlist fits money that is
actually arriving. A bond whose security status no tag or recorded fact
settles is labelled "security unconfirmed": check its detail page and record
it with bond_facts.py before any ENTER verdict."""
import argparse
import datetime as dt
import json
import sys

import bond_facts
import cashflows
import common
import portfolio


class StaleCapture(Exception):
    pass


def age_hours(captured_at, now):
    captured = dt.datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    return round((now - captured).total_seconds() / 3600, 1)


def _room(cap_pct, total, held):
    """Rupees that can be added before held/total exceeds cap_pct. None = no limit."""
    if total <= 0 or cap_pct is None or cap_pct >= 100:
        return None
    cap = cap_pct / 100
    return max(0.0, (cap * total - held) / (1 - cap))


def screen(listings_doc, snapshot, facts, profile, config, now, cash=None, allow_stale=False):
    age = age_hours(listings_doc["captured_at"], now)
    stale = age > config["listings_max_age_hours"]
    if stale and not allow_stale:
        raise StaleCapture(
            f"listings capture is {age} hours old (limit {config['listings_max_age_hours']}). "
            "Recapture the listings page, or pass --allow-stale.")
    order = config["rating_order"]
    floor = order.index(profile["min_rating"])
    slab = profile["tax_slab_pct"]
    held = [h for h in snapshot["holdings"] if (h["current_value"] or 0) > 0]
    total = sum(h["current_value"] for h in held)
    by_issuer, by_bucket = {}, {}
    for h in held:
        name = h["issuer"].casefold()
        by_issuer[name] = by_issuer.get(name, 0) + h["current_value"]
        fact = bond_facts.lookup(facts, isin=h["isin"]) or {}
        bucket = portfolio.rating_bucket(fact.get("rating"))
        by_bucket[bucket] = by_bucket.get(bucket, 0) + h["current_value"]

    shortlist, rejected = [], []
    for item in listings_doc["listings"]:
        fact = bond_facts.lookup(facts, bond_id=item["bond_id"]) or {}
        secured = item["secured"] if item["secured"] is not None else fact.get("secured")
        seniority = item["seniority"] or fact.get("seniority")
        rating = item["rating"]
        reasons = []
        if rating not in order:
            reasons.append(f"rating {item['rating_raw']!r} is unknown")
        elif order.index(rating) > floor:
            reasons.append(f"rating {rating} is below the floor {profile['min_rating']}")
        if item["tenure_months"] is None:
            reasons.append("tenure is unknown")
        elif item["tenure_months"] > profile["max_tenure_months"]:
            reasons.append(f"tenure {item['tenure_months']} months is over "
                           f"{profile['max_tenure_months']}")
        post_tax = None
        if item["ytm"] is None:
            reasons.append("YTM is unknown")
        else:
            post_tax = round(item["ytm"] * (1 - slab / 100), 2)
            if post_tax < profile["min_post_tax_ytm_pct"]:
                reasons.append(f"post-tax YTM {post_tax}% is under "
                               f"{profile['min_post_tax_ytm_pct']}%")
        if seniority == "subordinated" and not profile["allow_subordinated"]:
            reasons.append("subordinated debt is not allowed by the profile")
        if secured is False and not profile["allow_unsecured"]:
            reasons.append("unsecured paper is not allowed by the profile")
        if (item["sold_pct"] or 0) >= 100 or item["units_left"] == 0:
            reasons.append("sold out")
        minimum = item["min_investment"]
        if minimum is None:
            reasons.append("minimum investment is unknown")
        elif cash is not None and minimum > cash:
            reasons.append(f"minimum {minimum} is above available cash {cash}")
        rooms = [_room(profile["max_issuer_share_pct"], total,
                       by_issuer.get(item["issuer"].casefold(), 0))]
        bucket = portfolio.rating_bucket(rating if rating in order else None)
        bucket_cap = profile["max_rating_bucket_share_pct"].get(bucket)
        rooms.append(_room(bucket_cap, total, by_bucket.get(bucket, 0)))
        if minimum is not None:
            if rooms[0] is not None and rooms[0] < minimum:
                reasons.append(f"the minimum would take this issuer over the "
                               f"{profile['max_issuer_share_pct']}% cap")
            if rooms[1] is not None and rooms[1] < minimum:
                reasons.append(f"the minimum would take {bucket}-rated bonds over the "
                               f"{bucket_cap}% cap")
        if reasons:
            rejected.append({"issuer": item["issuer"], "key": item["key"], "reasons": reasons})
            continue
        limits = [r for r in rooms if r is not None]
        security = ("unsecured" if secured is False else "secured" if secured is True
                    else "security unconfirmed")
        shortlist.append({
            "issuer": item["issuer"], "key": item["key"], "url": item["url"],
            "bond_id": item["bond_id"], "rating": rating,
            "risk_bucket": f"{rating} / {security} / {seniority or 'seniority unconfirmed'}",
            "security": security, "ytm": item["ytm"],
            "ytm_is_upper_bound": item["ytm_is_upper_bound"], "post_tax_ytm": post_tax,
            "tenure_months": item["tenure_months"],
            "interest_frequency": item["interest_frequency"],
            "principal_type": item["principal_type"], "min_investment": minimum,
            "max_buy": float(int(min(limits))) if limits else None,
            "sold_pct": item["sold_pct"], "units_left": item["units_left"], "held": item["held"],
            "tags": item["tags"],
            "_sort": (order.index(rating), secured is False, seniority == "subordinated",
                      profile["prefer_monthly_income"] and item["interest_frequency"] != "Monthly",
                      -post_tax)})
    shortlist.sort(key=lambda row: row.pop("_sort"))
    for rank, row in enumerate(shortlist, start=1):
        row["rank"] = rank
    return {"captured_at": listings_doc["captured_at"], "age_hours": age, "stale": stale,
            "verified": listings_doc.get("verified", False), "cash": cash,
            "counts": {"listed": len(listings_doc["listings"]), "shortlisted": len(shortlist),
                       "rejected": len(rejected)},
            "shortlist": shortlist, "rejected": rejected}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cash", type=float)
    parser.add_argument("--allow-stale", action="store_true")
    parser.add_argument("--root")
    args = parser.parse_args(argv)
    root = common.resolve_root(args.root)
    data = common.skill_data_dir(root)
    listings = common.dated_files(data, "listings-")
    snapshots = common.dated_files(data, "snapshot-")
    if not listings or not snapshots:
        print("Need a snapshot and a listings capture. Run ingest.py reports and "
              "ingest.py listings first.", file=sys.stderr)
        return 1
    try:
        profile = common.load_profile(root)
    except (FileNotFoundError, ValueError) as err:
        print(err, file=sys.stderr)
        return 1
    config = common.load_config()
    snapshot = common.load_json(snapshots[-1])
    cash = args.cash
    if cash is None:
        cash = cashflows.idle_cash(snapshot, snapshot["as_of"], profile["lookahead_days"])["total"]
        cash = cash or None
    try:
        result = screen(common.load_json(listings[-1]), snapshot,
                        bond_facts.load(bond_facts.facts_path(root)), profile, config,
                        dt.datetime.now(dt.timezone.utc), cash=cash, allow_stale=args.allow_stale)
    except StaleCapture as err:
        print(err, file=sys.stderr)
        return 2
    for warning in common.stale_config_warnings(config, dt.date.today().isoformat()):
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
