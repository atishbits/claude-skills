#!/usr/bin/env python3
"""Keep a copy of this skill's outputs in a Google Drive folder, and bring back
what another Claude surface left there -- so a session with no access to this
machine can read the latest portfolio state, and can hand notes back.

Optional: the skill works without it, and `sync` exits quietly when it has not
been set up. Standard library only; it talks to the Drive API directly.

Two directions, both in one `sync`:

  1. Push. PORTFOLIO.md, every stocks/<TICKER>.md, the ratings ledger, the entry
     budgets and the calendar candidates are uploaded to the folder, each file
     overwritten in place, and only when its content changed since the last
     sync. The local data folder stays the source of truth: anything edited in
     those remote copies is overwritten by the next push.

  2. Pull. New files in the folder's `from-cowork` subfolder are downloaded to
     data/skill-data/from-cowork/ and listed as pending. That subfolder is the
     only place another surface should write: a trade it was told about, a
     decision, a piece of research. SKILL.md 3a reads the pending ones and folds
     them into the real note, ledger and budgets, then marks them merged.

    python3 scripts/drive_mirror.py set-folder FOLDER_ID_OR_LINK   # once
    python3 scripts/drive_mirror.py auth                           # once, opens a browser
    python3 scripts/drive_mirror.py sync [--with-snapshot]         # end of every run
    python3 scripts/drive_mirror.py pending                        # inbox files not merged yet
    python3 scripts/drive_mirror.py merged NAME [NAME ...]         # after folding them in

Setup needs an OAuth client of type "Desktop app" from Google Cloud Console,
saved as data/drive-mirror/client.json (README has the steps). The sign-in
token, the folder id and the sync state live beside it, all under the
gitignored data/ folder. The token is a credential: it is written owner-only
and must never be copied out of that folder.

The requested scope is full Drive access, because the narrower per-file scope
cannot see files another surface created, which is the whole of the pull
direction. The script itself only ever writes inside the configured folder.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = os.path.abspath(os.environ.get("PORTFOLIO_ROOT") or os.getcwd())
DATA_DIR = os.path.join(ROOT, "data", "skill-data")
CONF_DIR = os.path.join(ROOT, "data", "drive-mirror")
CLIENT_PATH = os.path.join(CONF_DIR, "client.json")
TOKEN_PATH = os.path.join(CONF_DIR, "token.json")
CONFIG_PATH = os.path.join(CONF_DIR, "config.json")
STATE_PATH = os.path.join(CONF_DIR, "state.json")

INBOX_NAME = "from-cowork"
SCOPE = "https://www.googleapis.com/auth/drive"
API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"
DOC_MIME = "application/vnd.google-apps.document"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
# Native documents have no bytes of their own; they are exported as text.
EXPORTS = {DOC_MIME: ("text/markdown", ".md"), SHEET_MIME: ("text/csv", ".csv")}
FIELDS = "id,name,mimeType,modifiedTime"

# Optional outputs: mirrored when present, never an error when absent.
TOP_LEVEL = ["PORTFOLIO.md", "calendar.md", "ratings-ledger.jsonl", "entry-budgets.json"]

README_TEXT = f"""# portfolio-review — mirrored outputs

This folder is a copy of what the portfolio-review skill last wrote on the
owner's own machine. That machine is the source of truth.

- `PORTFOLIO.md` — every holding, its signal row and current rating.
- `stocks/<TICKER>.md` — the latest research note per stock.
- `ratings-ledger.jsonl` — every rating recorded, with its price and reason.
- `entry-budgets.json` — the budget saved per stock for staged buying.
- `calendar.md` — next-result windows and price levels to re-check.

**Read these; do not edit them.** The next sync overwrites any change.

**To hand something back, create a new file in `{INBOX_NAME}/`** — one file per
piece of work, named with the date and the ticker, for example
`2026-01-15-ABC-trade.md`. Say plainly what happened: a trade (ticker, shares,
price, date), a decision, a budget, or research with its sources. The skill
picks the file up on its next run and folds it into the notes above.
"""


class DriveError(Exception):
    pass


class NotFound(DriveError):
    pass


# --- what to mirror ---------------------------------------------------------

def collect(data_dir, include_snapshot=False):
    """(relative name, content) for every file to mirror, in a stable order.
    The fetch cache, dated snapshots and the inbox are never included."""
    files = [("README.md", README_TEXT.encode("utf-8"))]
    names = [n for n in TOP_LEVEL if os.path.isfile(os.path.join(data_dir, n))]
    names += [os.path.join("stocks", os.path.basename(p))
              for p in sorted(glob.glob(os.path.join(data_dir, "stocks", "*.md")))]
    for name in names:
        with open(os.path.join(data_dir, name), "rb") as f:
            files.append((name.replace(os.sep, "/"), f.read()))
    if include_snapshot:
        snapshots = sorted(glob.glob(os.path.join(data_dir, "snapshot-*.json")))
        if snapshots:
            with open(snapshots[-1], "rb") as f:
                files.append(("snapshot-latest.json", f.read()))
    return files


def mime_for(name):
    if name.endswith(".md"):
        return "text/markdown"
    if name.endswith(".json"):
        return "application/json"
    return "text/plain"


def empty_state():
    return {"files": {}, "inbox": {}}


# --- push -------------------------------------------------------------------

def push(drive, folder_id, data_dir, state, include_snapshot=False):
    """Upload what changed since the last sync. Each file keeps one remote id,
    so a change overwrites it instead of leaving a second copy."""
    uploaded, unchanged, folders = [], 0, {}
    for rel, content in collect(data_dir, include_snapshot):
        digest = hashlib.sha256(content).hexdigest()
        known = state["files"].get(rel)
        if known and known["sha256"] == digest:
            unchanged += 1
            continue
        subdir, _, name = rel.rpartition("/")
        parent = folder_id
        if subdir:
            if subdir not in folders:
                folders[subdir] = drive.ensure_folder(folder_id, subdir)
            parent = folders[subdir]
        file_id = known["id"] if known else None
        if not file_id:
            # State lost or first run on a folder that already has a copy.
            existing = drive.find_child(parent, name)
            file_id = existing["id"] if existing else None
        if file_id:
            try:
                drive.update_file(file_id, content, mime_for(name))
            except NotFound:
                file_id = None
        if not file_id:
            file_id = drive.create_file(parent, name, content, mime_for(name))
        state["files"][rel] = {"id": file_id, "sha256": digest}
        uploaded.append(rel)
    return {"uploaded": uploaded, "unchanged": unchanged}


# --- pull -------------------------------------------------------------------

def local_name(remote_name, mime, taken):
    """A safe file name for a remote file. The remote name is someone else's
    text, so it is reduced to a bare name that cannot leave the inbox folder."""
    name = remote_name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    name = name or "untitled"
    ext = EXPORTS.get(mime, (None, ""))[1]
    if ext and not name.endswith(ext):
        name += ext
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    candidate, n = name, 1
    while candidate in taken:
        n += 1
        candidate = f"{stem}-{n}" + (f".{suffix}" if dot else "")
    return candidate


def pull_inbox(drive, folder_id, inbox_dir, state):
    """Download inbox files that are new, or changed since they were fetched.
    Returns their local names. A re-fetched file goes back to pending."""
    remote_inbox = drive.ensure_folder(folder_id, INBOX_NAME)
    fetched = []
    for meta in drive.list_children(remote_inbox):
        mime = meta.get("mimeType", "")
        if mime == FOLDER_MIME or (mime.startswith("application/vnd.google-apps.") and mime not in EXPORTS):
            continue
        seen = state["inbox"].get(meta["id"])
        if seen and seen["modified"] == meta.get("modifiedTime"):
            continue
        if seen:
            name = seen["local"]
        else:
            name = local_name(meta["name"], mime, {e["local"] for e in state["inbox"].values()})
        content = drive.download(meta)
        os.makedirs(inbox_dir, exist_ok=True)
        with open(os.path.join(inbox_dir, name), "wb") as f:
            f.write(content)
        state["inbox"][meta["id"]] = {"local": name, "modified": meta.get("modifiedTime"), "merged": False}
        fetched.append(name)
    return fetched


def pending(state):
    return sorted(e["local"] for e in state["inbox"].values() if not e["merged"])


def mark_merged(state, names):
    """Mark inbox files as folded in. Returns the names that were found."""
    done = []
    for entry in state["inbox"].values():
        if entry["local"] in names and not entry["merged"]:
            entry["merged"] = True
            done.append(entry["local"])
    return sorted(done)


# --- Drive API --------------------------------------------------------------

def http_transport(method, url, headers, body):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class Drive:
    def __init__(self, get_token, transport=http_transport):
        self.get_token = get_token
        self.transport = transport

    def _call(self, method, url, body=None, content_type=None):
        headers = {"Authorization": f"Bearer {self.get_token()}"}
        if content_type:
            headers["Content-Type"] = content_type
        status, data = self.transport(method, url, headers, body)
        if status == 404:
            raise NotFound(url)
        if status >= 400:
            raise DriveError(f"Drive returned HTTP {status}: {data[:300].decode('utf-8', 'replace')}")
        return data

    def list_children(self, parent_id):
        files, page = [], None
        while True:
            params = {"q": f"'{parent_id}' in parents and trashed = false",
                      "fields": f"nextPageToken,files({FIELDS})", "pageSize": 200}
            if page:
                params["pageToken"] = page
            reply = json.loads(self._call("GET", f"{API}/files?{urlencode(params)}"))
            files += reply.get("files", [])
            page = reply.get("nextPageToken")
            if not page:
                return files

    def find_child(self, parent_id, name):
        for f in self.list_children(parent_id):
            if f.get("name") == name:
                return f
        return None

    def ensure_folder(self, parent_id, name):
        found = self.find_child(parent_id, name)
        if found:
            return found["id"]
        meta = json.dumps({"name": name, "parents": [parent_id], "mimeType": FOLDER_MIME}).encode()
        return json.loads(self._call("POST", f"{API}/files?fields=id", meta, "application/json"))["id"]

    def create_file(self, parent_id, name, content, mime):
        boundary = "mirror" + secrets.token_hex(12)
        meta = json.dumps({"name": name, "parents": [parent_id]})
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
                f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() + content \
            + f"\r\n--{boundary}--\r\n".encode()
        reply = self._call("POST", f"{UPLOAD_API}/files?uploadType=multipart&fields=id", body,
                           f"multipart/related; boundary={boundary}")
        return json.loads(reply)["id"]

    def update_file(self, file_id, content, mime):
        self._call("PATCH", f"{UPLOAD_API}/files/{file_id}?uploadType=media&fields=id", content, mime)

    def download(self, meta):
        export = EXPORTS.get(meta.get("mimeType"))
        if export:
            return self._call("GET", f"{API}/files/{meta['id']}/export?{urlencode({'mimeType': export[0]})}")
        return self._call("GET", f"{API}/files/{meta['id']}?alt=media")


# --- sign-in ----------------------------------------------------------------

def client_from(raw):
    """The OAuth client out of the JSON file the console hands out."""
    client = raw.get("installed") or raw.get("web") or raw
    if "client_id" not in client:
        raise DriveError("client.json has no client_id -- download the OAuth client of type 'Desktop app'")
    return client


def auth_url(client, redirect_uri, state):
    params = {"client_id": client["client_id"], "redirect_uri": redirect_uri, "response_type": "code",
              "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state}
    return f"{client.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth')}?{urlencode(params)}"


def _token_request(client, fields, transport):
    body = urlencode({"client_id": client["client_id"], "client_secret": client.get("client_secret", ""),
                      **fields}).encode()
    return transport("POST", client.get("token_uri", "https://oauth2.googleapis.com/token"),
                     {"Content-Type": "application/x-www-form-urlencoded"}, body)


def access_token(client, token, transport=http_transport, now=None):
    """A usable access token, refreshing `token` in place when it has expired."""
    now = time.time() if now is None else now
    if token.get("access_token") and token.get("expires_at", 0) - 60 > now:
        return token["access_token"]
    status, data = _token_request(client, {"grant_type": "refresh_token",
                                           "refresh_token": token.get("refresh_token", "")}, transport)
    if status >= 400:
        raise DriveError("the saved sign-in was rejected -- run `drive_mirror.py auth` again "
                         f"(HTTP {status}: {data[:200].decode('utf-8', 'replace')})")
    reply = json.loads(data)
    token["access_token"] = reply["access_token"]
    token["expires_at"] = now + reply.get("expires_in", 3600)
    return token["access_token"]


def sign_in(client, transport=http_transport):
    """Browser sign-in on a loopback port. Returns the token to save."""
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.update({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Signed in. You can close this tab.")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    expected = secrets.token_urlsafe(16)
    url = auth_url(client, redirect, expected)
    print("Opening the browser to sign in. If it does not open, visit:\n  " + url)
    webbrowser.open(url)
    while "code" not in received and "error" not in received:
        server.handle_request()
    server.server_close()
    if received.get("error") or received.get("state") != expected:
        raise DriveError(f"sign-in was not completed: {received.get('error', 'state mismatch')}")
    status, data = _token_request(client, {"grant_type": "authorization_code", "code": received["code"],
                                           "redirect_uri": redirect}, transport)
    if status >= 400:
        raise DriveError(f"could not exchange the sign-in code (HTTP {status})")
    reply = json.loads(data)
    if "refresh_token" not in reply:
        raise DriveError("no refresh token returned -- remove this app's access in your Google account and retry")
    return {"refresh_token": reply["refresh_token"], "access_token": reply["access_token"],
            "expires_at": time.time() + reply.get("expires_in", 3600)}


# --- files on disk ----------------------------------------------------------

def folder_id_from(text):
    """A folder id, given the id itself or a link to the folder."""
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", text):
        return text
    raise ValueError(f"not a folder id or folder link: {text!r}")


def load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, value, private=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def load_state():
    return {**empty_state(), **(load_json(STATE_PATH) or {})}


def missing_setup():
    """What still has to be done before `sync` can run, as instructions."""
    steps = []
    if not os.path.isfile(CLIENT_PATH):
        steps.append(f"save the OAuth client JSON as {os.path.relpath(CLIENT_PATH, ROOT)}")
    if not (load_json(CONFIG_PATH) or {}).get("folder_id"):
        steps.append("run `drive_mirror.py set-folder FOLDER_ID_OR_LINK`")
    if not os.path.isfile(TOKEN_PATH):
        steps.append("run `drive_mirror.py auth`")
    return steps


def print_pending(state):
    names = pending(state)
    if names:
        print(f"Inbox: {len(names)} file(s) not merged yet, in {os.path.relpath(os.path.join(DATA_DIR, INBOX_NAME), ROOT)}/")
        for n in names:
            print(f"  {n}")
    else:
        print("Inbox: nothing pending.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth", help="one-time browser sign-in")
    p = sub.add_parser("set-folder", help="the Drive folder to mirror into")
    p.add_argument("folder")
    p = sub.add_parser("sync", help="push changed outputs, pull new inbox files")
    p.add_argument("--with-snapshot", action="store_true", help="also mirror the newest snapshot JSON")
    sub.add_parser("pending", help="inbox files not merged yet")
    p = sub.add_parser("merged", help="mark inbox files as folded in")
    p.add_argument("names", nargs="+")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "set-folder":
            save_json(CONFIG_PATH, {**(load_json(CONFIG_PATH) or {}), "folder_id": folder_id_from(args.folder)})
            print(f"Folder saved to {os.path.relpath(CONFIG_PATH, ROOT)}.")
        elif args.cmd == "auth":
            if not os.path.isfile(CLIENT_PATH):
                sys.exit(f"No OAuth client at {os.path.relpath(CLIENT_PATH, ROOT)} -- see the README's setup steps.")
            save_json(TOKEN_PATH, sign_in(client_from(load_json(CLIENT_PATH))), private=True)
            print(f"Signed in. Token saved to {os.path.relpath(TOKEN_PATH, ROOT)} (keep it out of git and backups).")
        elif args.cmd == "pending":
            print_pending(load_state())
        elif args.cmd == "merged":
            state = load_state()
            done = mark_merged(state, args.names)
            save_json(STATE_PATH, state)
            print("Marked merged: " + (", ".join(done) or "nothing"))
            unknown = sorted(set(args.names) - set(done))
            if unknown:
                sys.exit("Not a pending inbox file: " + ", ".join(unknown))
        elif args.cmd == "sync":
            steps = missing_setup()
            if steps:
                print("Drive mirror not set up -- skipped. To enable it: " + "; then ".join(steps) + ".")
                return
            client, token = client_from(load_json(CLIENT_PATH)), load_json(TOKEN_PATH)

            def get_token():
                before = token.get("access_token")
                value = access_token(client, token)
                if value != before:
                    save_json(TOKEN_PATH, token, private=True)
                return value

            drive, state = Drive(get_token), load_state()
            folder_id = load_json(CONFIG_PATH)["folder_id"]
            try:
                result = push(drive, folder_id, DATA_DIR, state, args.with_snapshot)
                fetched = pull_inbox(drive, folder_id, os.path.join(DATA_DIR, INBOX_NAME), state)
            finally:
                # Whatever did upload is recorded, so a failed run does not re-send it.
                save_json(STATE_PATH, state)
            print(f"Pushed {len(result['uploaded'])} file(s), {result['unchanged']} unchanged"
                  + (": " + ", ".join(result["uploaded"]) if result["uploaded"] else "."))
            print(f"Pulled {len(fetched)} new inbox file(s)" + (": " + ", ".join(fetched) if fetched else "."))
            print_pending(state)
    except (DriveError, ValueError) as e:
        sys.exit(f"drive_mirror: {e}")
    except urllib.error.URLError as e:
        sys.exit(f"drive_mirror: could not reach Drive ({e.reason})")


if __name__ == "__main__":
    main()
