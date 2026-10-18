"""Append-only logs as a folder of small files, one per writer per day.

A log that lives in cloud storage cannot be appended to in place: the
file-storage connector can only create a file or bin one. So each local root
(a machine's data folder, a Cowork session's folder) writes its own
`<date>-<writer id>.jsonl`, and readers take every file in the folder. Two
writers never touch the same file, so the log cannot conflict.
"""
import json
import os
import secrets


def writer_id(root):
    """Six hex characters, made once per root and kept in data/.writer-id."""
    path = os.path.join(root, "data", ".writer-id")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            value = fh.read().strip()
        if value:
            return value
    value = secrets.token_hex(3)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(value + "\n")
    return value


def append(log_dir, record, root, asof):
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"{asof}-{writer_id(root)}.jsonl")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def _read_file(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def read(log_dir, legacy_path=None):
    """Every record in the folder (file names sorted), plus a not-yet-migrated
    legacy single file if one is given and still exists."""
    records = []
    if legacy_path and os.path.exists(legacy_path):
        records.extend(_read_file(legacy_path))
    if os.path.isdir(log_dir):
        for name in sorted(os.listdir(log_dir)):
            if name.endswith(".jsonl"):
                records.extend(_read_file(os.path.join(log_dir, name)))
    return records


def migrate(legacy_path, log_dir, root):
    """Move a legacy single-file log into the folder as legacy-<writer>.jsonl.
    Returns the new path, or None if there was nothing to move."""
    if not os.path.exists(legacy_path):
        return None
    os.makedirs(log_dir, exist_ok=True)
    dest = os.path.join(log_dir, f"legacy-{writer_id(root)}.jsonl")
    os.replace(legacy_path, dest)
    return dest
