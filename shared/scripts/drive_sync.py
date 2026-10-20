#!/usr/bin/env python3
"""Plans the two-way sync between a local data folder and its copy in cloud
file storage. It never touches the network: the model lists the cloud folder
and moves files with the file-storage connector, and this script decides
every action and keeps the record of the last sync.

Shared by several skills. The master copy is shared/scripts/drive_sync.py in
the skills repo; each skill that uses it ships an identical copy beside its
own drive-sync.json, which says what that skill syncs (see load_config).
Edit the master, then run shared/sync-copies.sh.

Why a script: which file goes which way, and what is a conflict, has one
right answer given the listing, the local files and the last sync. A model
deciding that by eye would re-upload unchanged files (tokens) or overwrite
an edit made elsewhere (data).

Global options, before the command:
  --root DIR      the working root (default: the config's root_env variable, else the
                  working directory); the data folder is the config's data_dir inside it
  --config F      the skill's drive-sync.json (default: the one beside this script)

Commands (all print JSON):
  init --root-id ID                 first sync on a machine whose cloud folder exists
  listing-query                     the one search query that lists every known folder
  plan --listing F [--listing F...] [--manifest F] [--scope S] [NAME ...]
       [--direction both|down|up]   down: only what comes from the cloud; up: only what goes
       [--adopt-same-size]          once, after a first upload by hand: adopt same-size files
  folder PATH --id ID               register a folder the model just created
  put PATH B64FILE --id ID --modified TS     write a downloaded file, record it
                                    (PATH .manifest-in.json for the manifest: written, not recorded)
  uploaded PATH --id ID --modified TS [--size N]  record a file the model just uploaded;
                                    with --size, refuse if it differs from the local file
  resolve-local PATH --id ID --modified TS  after a conflict kept the local copy: the next
                                    plan uploads it over the remote one
  conflict-copy PATH COPY           move the local losing copy aside
  manifest                          write data/.manifest-out.json for upload

`plan` reads the listing pages (`data/.listing-*.json`) and the downloaded manifest
(`data/.manifest-in.json`) from the data folder unless given other files; `listing-query`
clears old pages. The folder type and the query syntax are the connector's own.
"""
import argparse
import base64
import fnmatch
import glob
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone

FOLDER_MIME = "application/vnd.google-apps.folder"
MIME = {".md": "text/markdown", ".json": "application/json", ".csv": "text/csv",
        ".jsonl": "text/plain", ".txt": "text/plain", ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel"}
CONFIG_NAME = "drive-sync.json"

# The skill's drive-sync.json:
#   marker    the manifest's file name in the cloud folder, found by exact name
#   root_env  environment variable naming the working root
#   data_dir  the synced folder, relative to the working root ("." for the root)
#   kinds     {kind: {"patterns": [glob, ...], "upload": true}}, checked in order;
#             a path is synced if a pattern of some kind matches it at the same
#             depth. "upload": false makes a kind download-only (documents the
#             user puts in the cloud; never retyped back up).
#   scopes    {scope: [kind, ...]}: which kinds a plan downloads in that scope;
#             "kind:named" limits that kind to files whose name, before the first
#             dot, is one of the plan's NAME arguments. "all" always exists and
#             covers every kind.
CFG = None


def load_config(path):
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    for key in ("marker", "kinds"):
        if key not in cfg:
            raise ValueError(f"{path}: missing {key!r}")
    cfg.setdefault("root_env", None)
    cfg.setdefault("data_dir", ".")
    cfg.setdefault("scopes", {})
    for kinds in cfg["scopes"].values():
        for k in kinds:
            if k.split(":")[0] not in cfg["kinds"]:
                raise ValueError(f"{path}: scope names unknown kind {k!r}")
    return cfg


def configure(cfg):
    global CFG
    CFG = cfg


def _cfg():
    if CFG is None:
        configure(load_config(os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_NAME)))
    return CFG


def _match(rel, patterns):
    # fnmatch's * crosses "/", so require the same depth as the pattern.
    return any(fnmatch.fnmatch(rel, p) and rel.count("/") == p.count("/") for p in patterns)


def scope_of(rel):
    """The kind a path belongs to, or None if it is not synced. Hidden files
    (this script's own .sync-base.json, listing pages) never are, nor is the
    manifest: it has its own commands."""
    if os.path.basename(rel).startswith(".") or rel == _cfg()["marker"]:
        return None
    for kind, spec in _cfg()["kinds"].items():
        if _match(rel, spec["patterns"]):
            return kind
    return None


def synced(rel):
    return scope_of(rel) is not None


def uploads(rel):
    return _cfg()["kinds"][scope_of(rel)].get("upload", True)


def in_scope(rel, scope, names):
    kind = scope_of(rel)
    if scope == "all":
        return True
    for entry in _cfg()["scopes"].get(scope, []):
        k, _, qual = entry.partition(":")
        if k != kind:
            continue
        if qual != "named":
            return True
        stem = os.path.basename(rel).split(".")[0].upper()
        if stem in {t.upper() for t in names}:
            return True
    return False


def norm_ts(value):
    """One spelling per instant, so a time from an upload result and the same
    time from a listing compare equal: UTC, whole seconds, a trailing Z."""
    if not value:
        return value
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    by_path = {}
    for f in entries.values():
        if f.get("mimeType") == FOLDER_MIME or f.get("parentId") not in by_id:
            continue
        parent = by_id[f["parentId"]]
        rel = f"{parent}/{f['title']}" if parent else f["title"]
        if synced(rel):
            item = {"id": f["id"], "modified": norm_ts(f.get("modifiedTime"))}
            if f.get("fileSize") is not None:
                item["size"] = int(f["fileSize"])
            by_path.setdefault(rel, []).append(item)
    # Two files on one path happen when an overwrite (create, then bin the old
    # one) was interrupted, or two copies uploaded at once. The newest is the
    # file; the others are reported so they can be kept as conflict copies.
    files = {}
    for rel, items in by_path.items():
        items.sort(key=lambda x: (x["modified"] or "", x["id"]), reverse=True)
        files[rel] = dict(items[0])
        if len(items) > 1:
            files[rel]["dups"] = items[1:]
    return files, folders


def _conflict_copy(rel, today, taken):
    """A conflict copy name no other file uses: .conflict-<date>, then -2, -3..."""
    stem, ext = os.path.splitext(rel)
    name, n = f"{stem}.conflict-{today}{ext}", 1
    while name in taken:
        n += 1
        name = f"{stem}.conflict-{today}-{n}{ext}"
    taken.add(name)
    return name


def plan(local, remote, base, manifest_files, scope, names, local_mtimes=None, today=None,
         local_sizes=None, adopt_same_size=False):
    """adopt_same_size: a first upload done by hand (drag and drop) has no base
    entry and no manifest hash, so it would read as a conflict. With the flag,
    a never-synced file the listing reports at the local file's exact size is
    adopted as that copy. Opt-in, because size alone is not proof of content."""
    today = today or date.today().isoformat()
    local_mtimes = local_mtimes or {}
    local_sizes = local_sizes or {}
    folders = base.get("folders", {})
    bfiles = base.get("files", {})
    out = {k: [] for k in ("download", "upload", "mkdir", "conflict", "duplicate", "unchanged", "adopt",
                           "local_only")}
    taken = set(local) | set(remote)
    for rel in sorted(set(local) | set(remote)):
        L, B, M = local.get(rel), bfiles.get(rel), manifest_files.get(rel)
        R = remote.get(rel)
        if R is not None:
            for d in R.get("dups", []):
                out["duplicate"].append({"path": rel, "id": d["id"], "modified": d["modified"],
                                         "copy": _conflict_copy(rel, today, taken)})
            size = R.get("size")
            R = {"id": R["id"], "modified": norm_ts(R["modified"])}
        if B:
            B = dict(B, modified=norm_ts(B.get("modified")))
        if M:
            M = dict(M, modified=norm_ts(M.get("modified")))
        if R is None:
            if not uploads(rel):
                out["local_only"].append(rel)
                continue
            parent_path = os.path.dirname(rel)
            if parent_path in folders:
                out["upload"].append({"path": rel, "old_id": None, "parent": folders[parent_path],
                                      "mime": MIME.get(os.path.splitext(rel)[1], "text/plain")})
            else:
                _need_folder(parent_path, folders, out["mkdir"])
            continue
        if L is None:
            if in_scope(rel, scope, names):
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
        if (adopt_same_size and not B and remote_sha is None and size is not None
                and local_sizes.get(rel) == size):
            out["adopt"].append({"path": rel, **R})
            continue
        local_changed = not B or L != B.get("sha")
        remote_changed = not B or R["id"] != B.get("id") or R["modified"] != B.get("modified")
        if not local_changed and not remote_changed:
            out["unchanged"].append(rel)
        elif local_changed and not remote_changed and not uploads(rel):
            out["local_only"].append(rel)
        elif local_changed and not remote_changed:
            out["upload"].append({"path": rel, "old_id": R["id"], "parent": folders.get(os.path.dirname(rel)),
                                  "mime": MIME.get(os.path.splitext(rel)[1], "text/plain")})
        elif remote_changed and not local_changed:
            if in_scope(rel, scope, names):
                out["download"].append({"path": rel, **R})
        else:
            keep = "remote" if (R["modified"] or "") > local_mtimes.get(rel, "") else "local"
            out["conflict"].append({"path": rel, "keep": keep, "copy": _conflict_copy(rel, today, taken), **R})
    return out


def by_direction(out, direction):
    """down: only what the cloud sends here; up: only what goes to the cloud.
    Conflicts and duplicates stay in both: either way they need resolving."""
    if direction == "down":
        out["upload"], out["mkdir"] = [], []
    elif direction == "up":
        out["download"] = []
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


def load_base(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {"root_id": None, "folders": {}, "files": {}}


def save_base(base, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(base, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


MANIFEST_IN = ".manifest-in.json"


def _safe_path(data_dir, rel):
    if not synced(rel) and rel != MANIFEST_IN:
        raise ValueError(f"not a synced path: {rel}")
    full = os.path.abspath(os.path.join(data_dir, rel))
    if not full.startswith(os.path.abspath(data_dir) + os.sep):
        raise ValueError(f"path escapes the data folder: {rel}")
    return full


def put(data_dir, base, rel, b64_text, file_id, modified):
    full = _safe_path(data_dir, rel)
    raw = base64.b64decode("".join(b64_text.split()), validate=True)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as fh:
        fh.write(raw)
    sha = sha256(full)
    if rel == MANIFEST_IN:
        # The manifest is not a synced file. It tells a cold root where every
        # folder is, so the first listing can cover them all, and its id is the
        # one to bin when this run uploads the next manifest.
        with open(full, encoding="utf-8") as fh:
            manifest = json.load(fh)
        base["root_id"] = base.get("root_id") or manifest.get("root_id")
        folders = base.setdefault("folders", {})
        for path, fid in (manifest.get("folders") or {}).items():
            folders.setdefault(path, fid)
        base["manifest_id"] = file_id
    elif ".conflict-" not in rel:
        # A conflict copy is new here; it goes up as a new file, not as the
        # remote file it was downloaded from.
        base.setdefault("files", {})[rel] = {"sha": sha, "id": file_id, "modified": norm_ts(modified)}
    return sha


def record_upload(data_dir, base, rel, file_id, modified):
    full = _safe_path(data_dir, rel)
    base.setdefault("files", {})[rel] = {"sha": sha256(full), "id": file_id, "modified": norm_ts(modified)}


def resolve_local(base, rel, file_id, modified):
    """A conflict kept the local copy: take the remote file as seen, keep the
    old base hash, so the next plan reads local-changed, remote-unchanged and
    uploads the local copy over it."""
    old = base.get("files", {}).get(rel, {})
    base.setdefault("files", {})[rel] = {"sha": old.get("sha", ""), "id": file_id, "modified": norm_ts(modified)}


def apply_adopt(base, data_dir, adopts):
    for a in adopts:
        record_upload(data_dir, base, a["path"], a["id"], a["modified"])


def build_manifest(base):
    return {"schema": 1, "root_id": base.get("root_id"), "folders": base.get("folders", {}),
            "files": {rel: {"sha": v["sha"], "id": v["id"], "modified": v["modified"]}
                      for rel, v in base.get("files", {}).items()}}


def listing_query(folders):
    return " or ".join(f"parentId = '{fid}'" for _, fid in sorted(folders.items()))


def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None, data_dir=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root")
    p.add_argument("--config")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init")
    s.add_argument("--root-id", required=True)
    sub.add_parser("listing-query")
    s = sub.add_parser("plan")
    s.add_argument("--listing", action="append", default=[])
    s.add_argument("--manifest")
    s.add_argument("--scope", default="all")
    s.add_argument("--direction", choices=["both", "down", "up"], default="both")
    s.add_argument("--adopt-same-size", action="store_true",
                   help="once, after a first upload done by hand: adopt never-synced files "
                        "the listing reports at the local file's size")
    s.add_argument("names", nargs="*")
    s = sub.add_parser("folder")
    s.add_argument("path")
    s.add_argument("--id", required=True)
    s = sub.add_parser("put")
    s.add_argument("path")
    s.add_argument("b64file")
    s.add_argument("--id", required=True)
    s.add_argument("--modified", required=True)
    s = sub.add_parser("uploaded")
    s.add_argument("path")
    s.add_argument("--id", required=True)
    s.add_argument("--modified", required=True)
    s.add_argument("--size", type=int, help="the uploaded file's size from the connector's result")
    s = sub.add_parser("resolve-local")
    s.add_argument("path")
    s.add_argument("--id", required=True)
    s.add_argument("--modified", required=True)
    s = sub.add_parser("conflict-copy")
    s.add_argument("path")
    s.add_argument("copy")
    sub.add_parser("manifest")
    a = p.parse_args(argv)

    if a.config:
        configure(load_config(a.config))
    cfg = _cfg()
    if data_dir is None:
        root = a.root or (cfg["root_env"] and os.environ.get(cfg["root_env"])) or os.getcwd()
        data_dir = os.path.normpath(os.path.join(os.path.abspath(os.path.expanduser(root)),
                                                 cfg["data_dir"]))
    base_path = os.path.join(data_dir, ".sync-base.json")
    if a.cmd == "plan" and a.scope != "all" and a.scope not in cfg["scopes"]:
        p.error("--scope must be " + " or ".join(["all", *cfg["scopes"]]))

    base = load_base(base_path)
    if a.cmd == "init":
        base.update({"root_id": a.root_id})
        base.setdefault("folders", {})[""] = a.root_id
        out = {"root_id": a.root_id}
    elif a.cmd == "listing-query":
        for old in glob.glob(os.path.join(data_dir, ".listing-*.json")):
            os.remove(old)
        out = {"query": listing_query(base.get("folders", {})),
               "save_pages_as": os.path.join(data_dir, ".listing-N.json")}
    elif a.cmd == "plan":
        manifest_path = a.manifest or os.path.join(data_dir, MANIFEST_IN)
        manifest = _load_json(manifest_path) if os.path.exists(manifest_path) else {}
        if manifest.get("folders"):
            merged = dict(manifest["folders"])
            merged.update(base.get("folders", {}))
            base["folders"] = merged
            base["root_id"] = base.get("root_id") or manifest.get("root_id")
        pages = a.listing or sorted(glob.glob(os.path.join(data_dir, ".listing-*.json")))
        listed = set(base.get("folders", {}).values())
        remote, base["folders"] = parse_listings([_load_json(f) for f in pages], base.get("folders", {}))
        local = local_files(data_dir)
        out = plan(local, remote, base, manifest.get("files", {}), a.scope, a.names,
                   local_mtimes=local_mtimes(data_dir, local),
                   local_sizes={rel: os.path.getsize(os.path.join(data_dir, rel)) for rel in local},
                   adopt_same_size=a.adopt_same_size)
        by_direction(out, a.direction)
        apply_adopt(base, data_dir, out["adopt"])
        # Folders found in this listing were not in its query, so their files
        # are missing from it: list again before acting on the plan.
        out["relist"] = sorted(set(base["folders"].values()) - listed)
    elif a.cmd == "folder":
        base.setdefault("folders", {})[a.path] = a.id
        out = {"folder": a.path, "id": a.id}
    elif a.cmd == "put":
        with open(a.b64file, encoding="ascii") as fh:
            out = {"path": a.path, "sha": put(data_dir, base, a.path, fh.read(), a.id, a.modified)}
    elif a.cmd == "uploaded":
        # The model retypes a file to upload it; a size that differs from the
        # local file means the cloud copy is not this file, so it is not recorded.
        local_size = os.path.getsize(_safe_path(data_dir, a.path))
        if a.size is not None and a.size != local_size:
            raise ValueError(f"{a.path}: uploaded {a.size} bytes, local file is {local_size}; "
                             "bin the upload and upload again")
        record_upload(data_dir, base, a.path, a.id, a.modified)
        out = {"path": a.path, "id": a.id}
    elif a.cmd == "resolve-local":
        resolve_local(base, a.path, a.id, a.modified)
        out = {"path": a.path, "upload_next": True}
    elif a.cmd == "conflict-copy":
        src, dst = _safe_path(data_dir, a.path), _safe_path(data_dir, a.copy)
        if os.path.exists(dst):
            raise ValueError(f"{a.copy} already exists; plan again for a free name")
        os.replace(src, dst)
        base.get("files", {}).pop(a.path, None)
        out = {"moved": a.path, "to": a.copy}
    else:  # manifest
        with open(os.path.join(data_dir, ".manifest-out.json"), "w", encoding="utf-8") as fh:
            json.dump(build_manifest(base), fh, indent=1, sort_keys=True)
        out = {"manifest": os.path.join(data_dir, ".manifest-out.json"), "name": cfg["marker"],
               "parent": base.get("root_id"), "old_id": base.get("manifest_id")}
    save_base(base, base_path)
    if argv is None:
        print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    main()
