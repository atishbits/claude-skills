import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import browser_guard as g  # noqa: E402

C = "mcp__claude-in-chrome__"
SCRIPT = os.path.join(os.path.dirname(__file__), "..", "browser_guard.py")


def click(summary):
    return g.decide(C + "computer", {"action": "left_click", "coordinate": [1, 1],
                                     "action_summary": summary, "tabId": 1})


class TestGuard(unittest.TestCase):
    def test_statement_clicks_allowed(self):
        for s in ["Opens the Download statement panel", "Selects 25 April as start date",
                  "Opens the statement period date picker", "Selects XLS as the download format"]:
            self.assertTrue(click(s)[0], s)
        ok, _ = g.decide(C + "form_input", {"ref": "r1", "value": "XLS",
                                           "action_summary": "Sets format to XLS", "tabId": 1})
        self.assertTrue(ok)

    def test_money_actions_denied(self):
        for s in ["Pays the credit card bill", "Adds a new payee", "Confirms the transfer",
                  "Opens the Download statement panel and confirm payment", "Enters the OTP",
                  "Sets up autopay for the card", "Applies for the card offer", ""]:
            ok, why = click(s)
            self.assertFalse(ok, s)
            self.assertIn("read-only guard", why)

    def test_type_only_dates(self):
        t = lambda x: g.decide(C + "computer", {"action": "type", "text": x, "tabId": 1})[0]
        self.assertTrue(t("25/04/2026"))
        self.assertTrue(t("25 Apr 2026"))
        self.assertFalse(t("123456"))
        self.assertFalse(t("hunter2"))

    def test_keys(self):
        k = lambda x: g.decide(C + "computer", {"action": "key", "text": x, "tabId": 1})[0]
        self.assertTrue(k("Escape"))
        self.assertTrue(k("Tab Tab"))
        self.assertFalse(k("Enter"))
        self.assertFalse(k("ctrl+v"))

    def test_read_only_actions_allowed(self):
        for a in ["screenshot", "zoom", "scroll", "wait", "hover", "scroll_to"]:
            self.assertTrue(g.decide(C + "computer", {"action": a, "tabId": 1})[0], a)
        for t in ["tabs_context_mcp", "tabs_create_mcp", "navigate", "read_page", "find", "get_page_text"]:
            self.assertTrue(g.decide(C + t, {})[0], t)
        self.assertTrue(g.decide("mcp__Claude_Browser__read_page", {})[0])

    def test_batch_and_unknown_tools_denied(self):
        for t in ["browser_batch", "javascript_tool", "file_upload", "new_tool"]:
            self.assertFalse(g.decide(C + t, {})[0], t)
        self.assertFalse(g.decide(C + "computer", {"action": "double_click", "action_summary": "Download"})[0])
        self.assertFalse(g.decide("mcp__computer-use__left_click", {})[0])

    def test_other_tools_untouched(self):
        self.assertTrue(g.decide("Bash", {"command": "ls"})[0])
        self.assertTrue(g.decide("mcp__claude_ai_Gmail__search_threads", {})[0])

    def test_cli_deny_json(self):
        inp = json.dumps({"tool_name": C + "javascript_tool", "tool_input": {"text": "1"}})
        out = subprocess.run([sys.executable, SCRIPT], input=inp, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        d = json.loads(out.stdout)["hookSpecificOutput"]
        self.assertEqual(d["permissionDecision"], "deny")
        self.assertEqual(d["hookEventName"], "PreToolUse")

    def test_cli_allow_silent(self):
        inp = json.dumps({"tool_name": C + "read_page", "tool_input": {}})
        out = subprocess.run([sys.executable, SCRIPT], input=inp, capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, ""))

    def test_cli_bad_json_denies(self):
        out = subprocess.run([sys.executable, SCRIPT], input="not json", capture_output=True, text=True)
        self.assertEqual(json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
