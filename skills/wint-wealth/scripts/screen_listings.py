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
  3. Post-tax YTM = YTM x (1 - tax rate), since bond interest is taxed at slab.
     The rate is the profile's effective_tax_rate_pct if set (slab plus cess and
     surcharge), else the bare slab. It is an approximation, good for ranking.
  4. Concentration: how much could be bought before the issuer (or its group)
     or its rating bucket goes over the profile's cap. Nothing fits -> rejected.
     Caps are a share of the Wint portfolio, or of the profile's
     total_investable if that is set.
     The rating used throughout is the one recorded in bond-facts.json when
     there is one; the listing card's rating is only the fallback.
  5. Rank within risk buckets: better rating first, then secured before
     unsecured, senior before subordinated; only then monthly income (if the
     profile prefers it) and post-tax YTM. Never by YTM across the whole list.

--cash AMOUNT drops bonds whose minimum is above the money available. Without
it nothing is filtered on cash; the output's cash_arriving shows the principal
and interest due within the profile's lookahead_days (cashflows.idle_cash), so
a shortlist can be sized to money that is actually coming back. A bond whose security status no tag or recorded fact
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


def _room(cap_pct, total, held, fixed_base=None):
    """Rupees that can be added before held/total exceeds cap_pct. None = no limit.
    With a fixed base (the profile's total_investable) the base does not grow
    with the purchase, because the money comes from elsewhere in it."""
    if cap_pct is None or cap_pct >= 100:
        return None
    if fixed_base:
        return max(0.0, cap_pct / 100 * fixed_base - held)
    if total <= 0:
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
    common.validate_profile(profile, config)
    order = config["rating_order"]
    floor = order.index(profile["min_rating"])
    slab = common.tax_rate(profile)
    base = profile.get("total_investable")
    warnings = []
    budget = None
    if profile.get("annual_investment_budget"):
        since = common.financial_year_start(snapshot["as_of"])
        spent = round(sum(p.get("invested") or 0 for p in snapshot.get("purchases", [])
                          if p.get("date") and p["date"] >= since), 2)
        budget = {"annual": profile["annual_investment_budget"], "financial_year_from": since,
                  "invested_so_far": spent,
                  "remaining": round(max(0.0, profile["annual_investment_budget"] - spent), 2)}
    held = [h for h in snapshot["holdings"] if (h["current_value"] or 0) > 0]
    total = sum(h["current_value"] for h in held)
    by_issuer, by_bucket = {}, {}
    for h in held:
        fact = bond_facts.lookup(facts, isin=h["isin"]) or {}
        name = (fact.get("group") or bond_facts.group_of(facts, h["issuer"])).casefold()
        by_issuer[name] = by_issuer.get(name, 0) + h["current_value"]
        bucket = portfolio.rating_bucket(fact.get("rating"))
        by_bucket[bucket] = by_bucket.get(bucket, 0) + h["current_value"]

    shortlist, rejected = [], []
    for item in listings_doc["listings"]:
        fact = bond_facts.lookup(facts, bond_id=item["bond_id"]) or {}
        secured = item["secured"] if item["secured"] is not None else fact.get("secured")
        seniority = item["seniority"] or fact.get("seniority")
        # A rating recorded from the agency's own document outranks the card's.
        rating = fact.get("rating") or item["rating"]
        if fact.get("rating") and fact["rating"] != item["rating"]:
            warnings.append(f"{item['issuer']} ({item['key']}): the card shows "
                            f"{item['rating_raw']} but the recorded rating is {rating}; "
                            "the recorded rating is used")
        reasons = []
        if rating not in order:
            reasons.append(f"rating {rating or item['rating_raw']!r} is unknown")
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
            floor_ytm = profile.get("min_ytm_pct")
            if floor_ytm is not None and item["ytm"] < floor_ytm:
                reasons.append(f"YTM {item['ytm']}% is under the {floor_ytm}% floor")
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
        group = fact.get("group") or bond_facts.group_of(facts, item["issuer"])
        rooms = [_room(profile["max_issuer_share_pct"], total,
                       by_issuer.get(group.casefold(), 0), base)]
        bucket = portfolio.rating_bucket(rating if rating in order else None)
        bucket_cap = profile["max_rating_bucket_share_pct"].get(bucket)
        rooms.append(_room(bucket_cap, total, by_bucket.get(bucket, 0), base))
        if budget is not None:
            rooms.append(budget["remaining"])
            if minimum is not None and budget["remaining"] < minimum:
                reasons.append(f"this financial year's investment budget has "
                               f"{budget['remaining']} left, under the minimum {minimum}")
        if minimum is not None:
            if rooms[0] is not None and rooms[0] < minimum:
                who = ("this issuer" if group.casefold() == item["issuer"].casefold()
                       else f"this issuer's group ({group})")
                reasons.append(f"the minimum would take {who} over the "
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
            "bond_id": item["bond_id"], "rating": rating, "rating_on_card": item["rating_raw"],
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
    unrated = round(by_bucket.get("unrated", 0), 2)
    if unrated > 0:
        warnings.append(
            f"{unrated} of holdings is unrated (no rating in bond-facts.json), so the "
            "rating-bucket caps cannot count it; max_buy reflects the issuer cap only for "
            "those buckets. Record the ratings to make the bucket caps real.")
    shortlist.sort(key=lambda row: row.pop("_sort"))
    for rank, row in enumerate(shortlist, start=1):
        row["rank"] = rank
    return {"captured_at": listings_doc["captured_at"], "age_hours": age, "stale": stale,
            "verified": listings_doc.get("verified", False), "cash": cash,
            "unrated_held_value": unrated, "warnings": warnings,
            "post_tax_basis": f"YTM x (1 - {slab}%): an approximation that treats the whole "
                              "yield as interest taxed at one rate. Set effective_tax_rate_pct "
                              "in the profile to include cess and surcharge.",
            "cap_basis": common.cap_basis(profile), "budget": budget,
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
    arriving = cashflows.idle_cash(snapshot, snapshot["as_of"], profile["lookahead_days"])
    try:
        result = screen(common.load_json(listings[-1]), snapshot,
                        bond_facts.load(bond_facts.facts_path(root)), profile, config,
                        dt.datetime.now(dt.timezone.utc), cash=args.cash,
                        allow_stale=args.allow_stale)
    except StaleCapture as err:
        print(err, file=sys.stderr)
        return 2
    except (ValueError, TypeError) as err:
        print(f"screen_listings: {err}", file=sys.stderr)
        return 1
    for warning in common.stale_config_warnings(config, dt.date.today().isoformat()):
        print(f"warning: {warning}", file=sys.stderr)
    result["cash_arriving"] = {k: arriving[k] for k in ("window_days", "total", "available_by")}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
