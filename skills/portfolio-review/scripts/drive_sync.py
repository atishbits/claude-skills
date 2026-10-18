#!/usr/bin/env python3
"""Plans the two-way sync between the local data folder and its master copy
in cloud file storage. It never touches the network: the model lists the
cloud folder and moves files with the file-storage connector, and this
script decides every action and keeps the record of the last sync.

Why a script: which file goes which way, and what is a conflict, has one
right answer given the listing, the local files and the last sync. A model
deciding that by eye would re-upload unchanged files (tokens) or overwrite
an edit made elsewhere (data).

Commands (all print JSON):
  init --root-id ID                 first sync on a machine whose cloud folder exists
  listing-query                     the one search query that lists every known folder
  plan --listing F [--listing F...] [--manifest F] --scope ticker|sweep|scan|all [TICKER ...]
  folder PATH --id ID               register a folder the model just created
  put PATH B64FILE --id ID --modified TS     write a downloaded file, record it
                                    (PATH .manifest-in.json for the manifest: written, not recorded)
  uploaded PATH --id ID --modified TS        record a file the model just uploaded
  conflict-copy PATH COPY           move the local losing copy aside
  manifest                          write data/.manifest-out.json for upload
"""
import argparse
import base64
import fnmatch
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
DATA_DIR = os.path.join(ROOT, "data")
BASE_PATH = os.path.join(DATA_DIR, ".sync-base.json")
MANIFEST_OUT = os.path.join(DATA_DIR, ".manifest-out.json")
MANIFEST_NAME = "portfolio-review-sync.json"
FOLDER_MIME = "application/vnd.google-apps.folder"

SHARED = ["*holdings*.csv", "broker-portfolio-*.md", "slug-overrides.json",
          "skill-data/digest.json", "skill-data/PORTFOLIO.md",
          "skill-data/entry-budgets.json", "skill-data/calendar.md",
          "skill-data/ratings-ledger/*.jsonl",
          "*.conflict-*", "skill-data/*.conflict-*"]
NOTES = ["skill-data/stocks/*.md"]
SCANS = ["skill-data/scan-history/*.jsonl"]
MIME = {".md": "text/markdown", ".json": "application/json", ".csv": "text/csv",
        ".jsonl": "text/plain"}


def _match(rel, patterns):
    # fnmatch's * crosses "/", so require the same depth as the pattern.
    return any(fnmatch.fnmatch(rel, p) and rel.count("/") == p.count("/") for p in patterns)


def scope_of(rel):
    if _match(rel, NOTES):
        return "note"
    if _match(rel, SCANS):
        return "scan"
    if _match(rel, SHARED):
        return "shared"
    return None


def synced(rel):
    return scope_of(rel) is not None


def in_scope(rel, scope, tickers):
    kind = scope_of(rel)
    if scope == "all" or kind == "shared":
        return True
    if kind == "note":
        if scope == "sweep":
            return True
        if scope == "ticker":
            stem = os.path.basename(rel).split(".")[0].upper()
            return stem in {t.upper() for t in tickers}
        return False
    if kind == "scan":
        return scope == "scan"
    return False


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def local_files(data_dir):
    out = {}
    for dirpath, dirnames, filenames in os.walk(data_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), data_dir).replace(os.sep, "/")
            if synced(rel):
                out[rel] = sha256(os.path.join(dirpath, name))
    return out


def local_mtimes(data_dir, rels):
    return {rel: datetime.fromtimestamp(os.path.getmtime(os.path.join(data_dir, rel)),
                                        timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            for rel in rels if os.path.exists(os.path.join(data_dir, rel))}


def parse_listings(pages, folders):
    folders = dict(folders)
    entries = {}
    for page in pages:
        for f in page.get("files", []):
            entries[f["id"]] = f
    # Folders first, repeatedly, so a folder listed before its parent resolves.
    by_id = {v: k for k, v in folders.items()}
    changed = True
    while changed:
        changed = False
        for f in entries.values():
            if f.get("mimeType") == FOLDER_MIME and f["id"] not in by_id and f.get("parentId") in by_id:
                parent = by_id[f["parentId"]]
                path = f"{parent}/{f['title']}" if parent else f["title"]
                folders[path] = f["id"]
                by_id[f["id"]] = path
                changed = True
    files = {}
    for f in entries.values():
        if f.get("mimeType") == FOLDER_MIME or f.get("parentId") not in by_id:
            continue
        parent = by_id[f["parentId"]]
        rel = f"{parent}/{f['title']}" if parent else f["title"]
        if synced(rel):
            files[rel] = {"id": f["id"], "modified": f.get("modifiedTime")}
    return files, folders


def _conflict_copy(rel, today):
    stem, ext = os.path.splitext(rel)
    return f"{stem}.conflict-{today}{ext}"


def plan(local, remote, base, manifest_files, scope, tickers, local_mtimes=None, today=None):
    today = today or date.today().isoformat()
    local_mtimes = local_mtimes or {}
    folders = base.get("folders", {})
    bfiles = base.get("files", {})
    out = {k: [] for k in ("download", "upload", "mkdir", "conflict", "unchanged", "adopt")}
    for rel in sorted(set(local) | set(remote)):
        L, R, B, M = local.get(rel), remote.get(rel), bfiles.get(rel), manifest_files.get(rel)
        if R is None:
            parent_path = os.path.dirname(rel)
            if parent_path in folders:
                out["upload"].append({"path": rel, "old_id": None, "parent": folders[parent_path],
                                      "mime": MIME.get(os.path.splitext(rel)[1], "text/plain")})
            else:
                _need_folder(parent_path, folders, out["mkdir"])
            continue
        if L is None:
            if in_scope(rel, scope, tickers):
                out["download"].append({"path": rel, **R})
            continue
        remote_sha = (M["sha"] if M and M.get("id") == R["id"] and M.get("modified") == R["modified"]
                      else None)
        if remote_sha == L:
            if not B or B.get("sha") != L or B.get("id") != R["id"] or B.get("modified") != R["modified"]:
                out["adopt"].append({"path": rel, **R})
            else:
                out["unchanged"].append(rel)
            continue
        local_changed = not B or L != B.get("sha")
        remote_changed = not B or R["id"] != B.get("id") or R["modified"] != B.get("modified")
        if not local_changed and not remote_changed:
            out["unchanged"].append(rel)
        elif local_changed and not remote_changed:
            out["upload"].append({"path": rel, "old_id": R["id"], "parent": folders.get(os.path.dirname(rel)),
                                  "mime": MIME.get(os.path.splitext(rel)[1], "text/plain")})
        elif remote_changed and not local_changed:
            if in_scope(rel, scope, tickers):
                out["download"].append({"path": rel, **R})
        else:
            keep = "remote" if (R["modified"] or "") > local_mtimes.get(rel, "") else "local"
            out["conflict"].append({"path": rel, "keep": keep, "copy": _conflict_copy(rel, today), **R})
    return out


def _need_folder(path, folders, mkdirs):
    """Queue the shallowest missing folder on the way to `path`."""
    parts = path.split("/")
    for i in range(1, len(parts) + 1):
        sub = "/".join(parts[:i])
        if sub not in folders:
            parent = "/".join(parts[:i - 1])
            if parent in folders:
                item = {"path": sub, "parent": folders[parent]}
                if item not in mkdirs:
                    mkdirs.append(item)
            return
