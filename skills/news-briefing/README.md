# news-briefing

A short, dated news digest in four sections: global, your home country, what you hold, and your
work and interests. It covers the time since you last ran it, seven days at most.

## Your details stay yours

This folder ships tooling only. Everything about you lives in `data/`, which the repo's
`.gitignore` excludes and the pre-commit hook refuses:

```
data/
  profile.json   home country, work, feeds, topics from your holdings, interests
  state.json     when you last ran a briefing
  api.json       optional: one news API, described by URL template, key and field names
  notes.md       the skill's local memory: where your holdings and memory folders are,
                 which feeds and API you chose
```

The profile holds names and topics only. `user_profile.py validate` accepts a fixed set of fields
and rejects everything else, including any name containing five or more digits in a row, so a
quantity, a cost or an account number cannot ride along. `profile-template.json` shows the shape
with invented values.

A copy of the profile, with the last-run time, is kept as `news-briefing-profile.json` in your
cloud file storage so the skill behaves the same where it has no access to this folder. The API
key is never copied there. Company and employer names in the profile are used in feed and search
queries.

## Setup

1. Install the skill by linking this folder into your skills directory.
2. Ask for a briefing. With no profile, the skill runs onboarding: it fills in what it already
   knows about you, shows you that list to correct, and asks only for what is left. You can skip
   any question.
3. In `data/notes.md`, list the holdings files and memory folders it should read, then ask it to
   `refresh`. You approve the result before anything is saved.
4. Optional: copy `api-template.json` to `data/api.json` and fill it in for one news API. The
   template says which parts of the reply to point at.

## Where the headlines come from

`fetch_news.py` reads the RSS and Atom feeds in your profile, an optional search feed fetched once
per topic, and the optional API. It keeps items published inside the window, drops items with no
date, and removes duplicates by link and by headline. Where scripts cannot reach the network, the
skill searches the web instead and keeps only what it can date.

## Other surfaces

```
python3 scripts/package.py
```

writes a ZIP of this folder without `data/`, caches or tests, and prints its contents. Upload that
as a custom skill. There the skill reads the shared copy of your profile through a file-storage
connector.

## Scripts

| Script | What it does |
|---|---|
| `window.py` | The period to cover, from the last run, capped at seven days |
| `fetch_news.py` | Dated, de-duplicated candidate headlines per section |
| `user_profile.py` | Validate the profile, list onboarding gaps, names from holdings, last-run time |
| `package.py` | The upload bundle |

Tests: `python3 -m unittest discover -s tests -p 'test_*.py'` from `scripts/`.
