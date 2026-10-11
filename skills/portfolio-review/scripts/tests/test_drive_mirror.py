import json
import os
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drive_mirror as dm


class FakeDrive:
    """An in-memory stand-in for dm.Drive: same methods, a dict for storage."""

    def __init__(self):
        self.files = {}   # id -> {"id", "name", "parent", "mimeType", "modifiedTime", "content"}
        self.n = 0
        self.calls = []

    def _add(self, parent, name, content, mime, modified="2026-01-01T00:00:00Z"):
        self.n += 1
        fid = f"id{self.n}"
        self.files[fid] = {"id": fid, "name": name, "parent": parent, "mimeType": mime,
                           "modifiedTime": modified, "content": content}
        return fid

    def list_children(self, parent_id):
        return [{k: f[k] for k in ("id", "name", "mimeType", "modifiedTime")}
                for f in self.files.values() if f["parent"] == parent_id]

    def find_child(self, parent_id, name):
        for f in self.list_children(parent_id):
            if f["name"] == name:
                return f
        return None

    def ensure_folder(self, parent_id, name):
        found = self.find_child(parent_id, name)
        return found["id"] if found else self._add(parent_id, name, b"", dm.FOLDER_MIME)

    def create_file(self, parent_id, name, content, mime):
        self.calls.append(("create", name))
        return self._add(parent_id, name, content, mime)

    def update_file(self, file_id, content, mime):
        self.calls.append(("update", file_id))
        if file_id not in self.files:
            raise dm.NotFound(file_id)
        self.files[file_id]["content"] = content

    def download(self, meta):
        return self.files[meta["id"]]["content"]

    def by_name(self, name):
        return [f for f in self.files.values() if f["name"] == name]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class DataDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = os.path.join(self.tmp.name, "skill-data")
        write(os.path.join(self.data, "PORTFOLIO.md"), "# book\n")
        write(os.path.join(self.data, "stocks", "AAA.md"), "# AAA\n")
        write(os.path.join(self.data, "stocks", "BBB.md"), "# BBB\n")
        write(os.path.join(self.data, "ratings-ledger.jsonl"), "{}\n")
        write(os.path.join(self.data, "snapshot-2026-01-01.json"), "{\"old\": 1}")
        write(os.path.join(self.data, "snapshot-2026-01-02.json"), "{\"new\": 1}")
        write(os.path.join(self.data, ".cache", "AAA.html"), "<html>")
        self.inbox = os.path.join(self.data, dm.INBOX_NAME)


class CollectTests(DataDirCase):
    def test_collects_the_outputs_a_reader_needs_and_no_cache_or_snapshot(self):
        rels = [rel for rel, _ in dm.collect(self.data)]
        self.assertEqual(rels, ["README.md", "PORTFOLIO.md", "ratings-ledger.jsonl",
                                "stocks/AAA.md", "stocks/BBB.md"])

    def test_missing_optional_files_are_left_out_not_an_error(self):
        os.remove(os.path.join(self.data, "ratings-ledger.jsonl"))
        self.assertNotIn("ratings-ledger.jsonl", [rel for rel, _ in dm.collect(self.data)])

    def test_snapshot_flag_adds_only_the_newest_under_a_fixed_name(self):
        files = dict(dm.collect(self.data, include_snapshot=True))
        self.assertEqual(files["snapshot-latest.json"], b"{\"new\": 1}")
        self.assertFalse([r for r in files if r.startswith("snapshot-2026")])

    def test_inbox_files_are_never_pushed_back(self):
        write(os.path.join(self.inbox, "note.md"), "from the other side")
        self.assertFalse([rel for rel, _ in dm.collect(self.data) if "note.md" in rel])


class PushTests(DataDirCase):
    def test_first_push_creates_every_file_with_stocks_in_a_subfolder(self):
        drive, state = FakeDrive(), dm.empty_state()
        result = dm.push(drive, "ROOT", self.data, state)
        self.assertEqual(len(result["uploaded"]), 5)
        stocks = drive.find_child("ROOT", "stocks")
        self.assertEqual(stocks["mimeType"], dm.FOLDER_MIME)
        self.assertEqual(drive.find_child(stocks["id"], "AAA.md")["name"], "AAA.md")
        self.assertEqual(drive.by_name("PORTFOLIO.md")[0]["content"], b"# book\n")

    def test_second_push_with_nothing_changed_uploads_nothing(self):
        drive, state = FakeDrive(), dm.empty_state()
        dm.push(drive, "ROOT", self.data, state)
        drive.calls.clear()
        result = dm.push(drive, "ROOT", self.data, state)
        self.assertEqual(result["uploaded"], [])
        self.assertEqual(result["unchanged"], 5)
        self.assertEqual(drive.calls, [])

    def test_changed_file_is_overwritten_in_place_not_duplicated(self):
        drive, state = FakeDrive(), dm.empty_state()
        dm.push(drive, "ROOT", self.data, state)
        write(os.path.join(self.data, "stocks", "AAA.md"), "# AAA v2\n")
        result = dm.push(drive, "ROOT", self.data, state)
        self.assertEqual(result["uploaded"], ["stocks/AAA.md"])
        copies = drive.by_name("AAA.md")
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0]["content"], b"# AAA v2\n")

    def test_lost_state_reuses_the_remote_file_of_the_same_name(self):
        drive = FakeDrive()
        dm.push(drive, "ROOT", self.data, dm.empty_state())
        dm.push(drive, "ROOT", self.data, dm.empty_state())
        self.assertEqual(len(drive.by_name("PORTFOLIO.md")), 1)

    def test_file_deleted_remotely_is_created_again(self):
        drive, state = FakeDrive(), dm.empty_state()
        dm.push(drive, "ROOT", self.data, state)
        gone = drive.by_name("PORTFOLIO.md")[0]["id"]
        del drive.files[gone]
        write(os.path.join(self.data, "PORTFOLIO.md"), "# book v2\n")
        dm.push(drive, "ROOT", self.data, state)
        self.assertEqual(drive.by_name("PORTFOLIO.md")[0]["content"], b"# book v2\n")


class InboxTests(DataDirCase):
    def setUp(self):
        super().setUp()
        self.drive = FakeDrive()
        self.remote_inbox = self.drive.ensure_folder("ROOT", dm.INBOX_NAME)
        self.state = dm.empty_state()

    def pull(self):
        return dm.pull_inbox(self.drive, "ROOT", self.inbox, self.state)

    def test_creates_the_remote_inbox_folder_when_absent(self):
        drive = FakeDrive()
        dm.pull_inbox(drive, "ROOT", self.inbox, dm.empty_state())
        self.assertEqual(drive.find_child("ROOT", dm.INBOX_NAME)["mimeType"], dm.FOLDER_MIME)

    def test_new_file_is_downloaded_and_listed_as_pending(self):
        self.drive._add(self.remote_inbox, "trade.md", b"bought 3", "text/markdown")
        self.assertEqual(self.pull(), ["trade.md"])
        with open(os.path.join(self.inbox, "trade.md"), "rb") as f:
            self.assertEqual(f.read(), b"bought 3")
        self.assertEqual(dm.pending(self.state), ["trade.md"])

    def test_file_already_fetched_is_not_fetched_again(self):
        self.drive._add(self.remote_inbox, "trade.md", b"bought 3", "text/markdown")
        self.pull()
        self.assertEqual(self.pull(), [])

    def test_merged_file_leaves_pending_and_stays_merged_on_the_next_pull(self):
        self.drive._add(self.remote_inbox, "trade.md", b"bought 3", "text/markdown")
        self.pull()
        self.assertEqual(dm.mark_merged(self.state, ["trade.md"]), ["trade.md"])
        self.pull()
        self.assertEqual(dm.pending(self.state), [])

    def test_file_edited_remotely_after_merge_is_fetched_and_pending_again(self):
        fid = self.drive._add(self.remote_inbox, "trade.md", b"bought 3", "text/markdown")
        self.pull()
        dm.mark_merged(self.state, ["trade.md"])
        self.drive.files[fid].update(content=b"bought 5", modifiedTime="2026-02-01T00:00:00Z")
        self.assertEqual(self.pull(), ["trade.md"])
        self.assertEqual(dm.pending(self.state), ["trade.md"])

    def test_native_document_is_saved_as_markdown(self):
        self.drive._add(self.remote_inbox, "TESTCO decision", b"# x", dm.DOC_MIME)
        self.assertEqual(self.pull(), ["TESTCO decision.md"])

    def test_remote_name_cannot_escape_the_inbox_folder(self):
        self.drive._add(self.remote_inbox, "../../PORTFOLIO.md", b"evil", "text/markdown")
        (name,) = self.pull()
        self.assertEqual(os.path.dirname(os.path.join(self.inbox, name)), self.inbox)
        with open(os.path.join(self.data, "PORTFOLIO.md")) as f:
            self.assertEqual(f.read(), "# book\n")

    def test_two_remote_files_with_one_name_do_not_overwrite_each_other(self):
        self.drive._add(self.remote_inbox, "note.md", b"one", "text/markdown")
        self.drive._add(self.remote_inbox, "note.md", b"two", "text/markdown")
        names = self.pull()
        self.assertEqual(len(set(names)), 2)
        contents = set()
        for n in names:
            with open(os.path.join(self.inbox, n), "rb") as f:
                contents.add(f.read())
        self.assertEqual(contents, {b"one", b"two"})

    def test_subfolders_and_unreadable_native_types_are_skipped(self):
        self.drive._add(self.remote_inbox, "sub", b"", dm.FOLDER_MIME)
        self.drive._add(self.remote_inbox, "deck", b"", "application/vnd.google-apps.presentation")
        self.assertEqual(self.pull(), [])

    def test_marking_an_unknown_name_reports_nothing_merged(self):
        self.assertEqual(dm.mark_merged(self.state, ["nope.md"]), [])


class LocalNameTests(unittest.TestCase):
    def test_keeps_an_ordinary_name(self):
        self.assertEqual(dm.local_name("2026-10-20 TESTCO-decision.md", "text/markdown", set()),
                         "2026-10-20 TESTCO-decision.md")

    def test_hidden_and_empty_names_become_visible(self):
        self.assertEqual(dm.local_name(".env", "text/plain", set()), "env")
        self.assertEqual(dm.local_name("///", "text/plain", set()), "untitled")

    def test_collision_gets_a_numbered_suffix_before_the_extension(self):
        self.assertEqual(dm.local_name("note.md", "text/markdown", {"note.md"}), "note-2.md")


class FolderIdTests(unittest.TestCase):
    def test_accepts_a_bare_id(self):
        self.assertEqual(dm.folder_id_from("1AbC_d-9"), "1AbC_d-9")

    def test_extracts_the_id_from_a_folder_link(self):
        self.assertEqual(dm.folder_id_from("https://drive.google.com/drive/folders/1AbC_d-9?usp=sharing"),
                         "1AbC_d-9")

    def test_rejects_anything_else(self):
        with self.assertRaises(ValueError):
            dm.folder_id_from("ROOT FOLDER/claude")


class Transport:
    """Records requests and replays canned (status, body) responses in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, method, url, headers, body):
        self.requests.append({"method": method, "url": url, "headers": headers, "body": body})
        return self.responses.pop(0)


class DriveRequestTests(unittest.TestCase):
    def drive(self, *responses):
        self.t = Transport(*responses)
        return dm.Drive(lambda: "TOKEN", self.t)

    def test_every_request_carries_the_bearer_token(self):
        self.drive((200, b'{"files": []}')).list_children("P")
        self.assertEqual(self.t.requests[0]["headers"]["Authorization"], "Bearer TOKEN")

    def test_listing_asks_for_live_children_of_the_parent_and_follows_pages(self):
        d = self.drive((200, json.dumps({"files": [{"id": "a"}], "nextPageToken": "T2"}).encode()),
                       (200, json.dumps({"files": [{"id": "b"}]}).encode()))
        self.assertEqual([f["id"] for f in d.list_children("P")], ["a", "b"])
        q = parse_qs(urlparse(self.t.requests[0]["url"]).query)
        self.assertEqual(q["q"], ["'P' in parents and trashed = false"])
        self.assertEqual(parse_qs(urlparse(self.t.requests[1]["url"]).query)["pageToken"], ["T2"])

    def test_create_sends_name_parent_and_content_in_one_multipart_upload(self):
        d = self.drive((200, b'{"id": "NEW"}'))
        self.assertEqual(d.create_file("P", "a.md", b"hello", "text/markdown"), "NEW")
        r = self.t.requests[0]
        self.assertEqual(r["method"], "POST")
        self.assertIn("uploadType=multipart", r["url"])
        self.assertIn(b'"name": "a.md"', r["body"])
        self.assertIn(b'"parents": ["P"]', r["body"])
        self.assertIn(b"hello", r["body"])
        boundary = r["headers"]["Content-Type"].split("boundary=")[1]
        self.assertTrue(r["body"].rstrip().endswith(f"--{boundary}--".encode()))

    def test_update_overwrites_the_content_of_the_same_file_id(self):
        d = self.drive((200, b'{"id": "X"}'))
        d.update_file("X", b"v2", "text/markdown")
        r = self.t.requests[0]
        self.assertEqual(r["method"], "PATCH")
        self.assertIn("/files/X?", r["url"])
        self.assertIn("uploadType=media", r["url"])
        self.assertEqual(r["body"], b"v2")

    def test_update_of_a_missing_file_raises_not_found(self):
        with self.assertRaises(dm.NotFound):
            self.drive((404, b"{}")).update_file("X", b"v2", "text/markdown")

    def test_other_http_errors_raise_with_the_status(self):
        with self.assertRaises(dm.DriveError) as ctx:
            self.drive((403, b'{"error": "nope"}')).list_children("P")
        self.assertIn("403", str(ctx.exception))

    def test_plain_file_downloads_as_media_and_native_document_as_an_export(self):
        d = self.drive((200, b"raw"), (200, b"# md"))
        self.assertEqual(d.download({"id": "F", "mimeType": "text/markdown"}), b"raw")
        self.assertEqual(d.download({"id": "G", "mimeType": dm.DOC_MIME}), b"# md")
        self.assertIn("/files/F?alt=media", self.t.requests[0]["url"])
        self.assertIn("/files/G/export?", self.t.requests[1]["url"])
        self.assertEqual(parse_qs(urlparse(self.t.requests[1]["url"]).query)["mimeType"], ["text/markdown"])

    def test_ensure_folder_reuses_an_existing_folder(self):
        d = self.drive((200, json.dumps({"files": [{"id": "S", "name": "stocks",
                                                    "mimeType": dm.FOLDER_MIME}]}).encode()))
        self.assertEqual(d.ensure_folder("P", "stocks"), "S")
        self.assertEqual(len(self.t.requests), 1)


class TokenTests(unittest.TestCase):
    CLIENT = {"client_id": "CID", "client_secret": "SEC", "token_uri": "https://example.test/token"}

    def test_auth_url_asks_for_offline_access_on_the_loopback_redirect(self):
        q = parse_qs(urlparse(dm.auth_url({**self.CLIENT, "auth_uri": "https://example.test/auth"},
                                          "http://127.0.0.1:8123", "STATE")).query)
        self.assertEqual(q["client_id"], ["CID"])
        self.assertEqual(q["redirect_uri"], ["http://127.0.0.1:8123"])
        self.assertEqual(q["access_type"], ["offline"])
        self.assertEqual(q["scope"], [dm.SCOPE])
        self.assertEqual(q["state"], ["STATE"])

    def test_unexpired_access_token_is_used_without_a_network_call(self):
        t = Transport()
        token = {"access_token": "A", "refresh_token": "R", "expires_at": 2000}
        self.assertEqual(dm.access_token(self.CLIENT, token, t, now=1000), "A")
        self.assertEqual(t.requests, [])

    def test_expired_access_token_is_refreshed_and_the_refresh_token_kept(self):
        t = Transport((200, b'{"access_token": "B", "expires_in": 3600}'))
        token = {"access_token": "A", "refresh_token": "R", "expires_at": 900}
        self.assertEqual(dm.access_token(self.CLIENT, token, t, now=1000), "B")
        self.assertEqual(token["refresh_token"], "R")
        self.assertEqual(token["expires_at"], 4600)
        sent = parse_qs(t.requests[0]["body"].decode())
        self.assertEqual(sent["grant_type"], ["refresh_token"])
        self.assertEqual(sent["refresh_token"], ["R"])

    def test_rejected_refresh_says_to_sign_in_again(self):
        t = Transport((400, b'{"error": "invalid_grant"}'))
        with self.assertRaises(dm.DriveError) as ctx:
            dm.access_token(self.CLIENT, {"refresh_token": "R", "expires_at": 0}, t, now=1000)
        self.assertIn("auth", str(ctx.exception))

    def test_client_file_is_read_from_the_installed_app_section(self):
        self.assertEqual(dm.client_from({"installed": self.CLIENT})["client_id"], "CID")


if __name__ == "__main__":
    unittest.main()
