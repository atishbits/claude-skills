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

    def test_menu_navigation_allowed(self):
        for s in ["Opens the Cards menu", "Opens the Credit Cards section",
                  "Selects the second credit card", "Opens the transaction history page"]:
            self.assertTrue(click(s)[0], s)

    def test_period_range_value_allowed(self):
        f = lambda v: g.decide(C + "form_input", {"ref": "r1", "value": v, "tabId": 1,
                                                  "action_summary": "Sets the statement period"})[0]
        self.assertTrue(f("16/8/2026-15/9/2026"))
        self.assertFalse(f("4000111122223333"))
        self.assertFalse(f("16/8/2026-15/9/2026 and pay"))

    def test_menu_clicks_that_act_denied(self):
        for s in ["Opens Pay Bills for the credit card", "Blocks the card", "Opens card limit settings",
                  "Opens the Cards menu and adds a payee", "Converts the transaction to EMI"]:
            self.assertFalse(click(s)[0], s)

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


class TestHookCommand(unittest.TestCase):
    """The command SKILL.md registers must find the guard however the skill is
    installed, and block (exit 2) when it cannot."""

    def command(self):
        import re
        with open(os.path.join(os.path.dirname(SCRIPT), "..", "SKILL.md"), encoding="utf-8") as f:
            front = f.read().split("---")[1]
        m = re.search(r"command: '(.+)'", front)
        self.assertIsNotNone(m, "hook command must be a single-quoted YAML string")
        return m.group(1).replace("''", "'")

    def run_cmd(self, env):
        inp = json.dumps({"tool_name": C + "javascript_tool", "tool_input": {}})
        full = {"PATH": os.environ["PATH"], "HOME": env.pop("HOME", "/nonexistent")}
        full.update(env)
        return subprocess.run(["sh", "-c", self.command()], input=inp, capture_output=True,
                              text=True, env=full)

    def test_finds_guard_via_skill_dir(self):
        skill = os.path.abspath(os.path.join(os.path.dirname(SCRIPT), ".."))
        out = self.run_cmd({"CLAUDE_SKILL_DIR": skill})
        self.assertIn('"deny"', out.stdout)

    def test_finds_guard_via_plugin_root(self):
        repo = os.path.abspath(os.path.join(os.path.dirname(SCRIPT), "..", "..", ".."))
        out = self.run_cmd({"CLAUDE_PLUGIN_ROOT": repo})
        self.assertIn('"deny"', out.stdout)

    def test_blocks_when_guard_missing(self):
        out = self.run_cmd({})
        self.assertEqual(out.returncode, 2)


class TestReviewFindings(unittest.TestCase):
    def test_honest_money_steps_denied(self):
        for s in ["Click Proceed to complete the transaction", "Click Close account on the account page",
                  "Click Open FD on account page", "Click Cancel card", "Click Yes on the card page dialog",
                  "Click Continue on card page", "Clicks Save on the account settings",
                  "Opens the account page", "Clicks Submit"]:
            self.assertFalse(click(s)[0], s)

    def test_statement_steps_still_allowed(self):
        for s in ["Opens the View Statement page", "Clicks OK in the date picker",
                  "Opens the account dropdown on the statement page",
                  "Selects the previous month in the calendar", "Closes the statement dialog"]:
            self.assertTrue(click(s)[0], s)

    def test_bare_numbers_only_years(self):
        t = lambda x: g.decide(C + "computer", {"action": "type", "text": x, "tabId": 1})[0]
        self.assertTrue(t("2026"))
        self.assertFalse(t("1234"))
        self.assertFalse(t("50000"))

    def test_form_values_constrained(self):
        f = lambda s, v: g.decide(C + "form_input", {"ref": "r", "value": v, "action_summary": s})[0]
        self.assertFalse(f("Sets amount on the account page", "50000"))
        self.assertFalse(f("Sets the statement field", "123456"))
        self.assertTrue(f("Sets the statement start date", "25/04/2026"))
        self.assertTrue(f("Sets the statement format", "XLS"))
        self.assertTrue(f("Sets the statement month", "April"))
        self.assertTrue(f("Sets the statement period", "Last 6 months"))

    def test_script_urls_denied(self):
        for u in ["javascript:alert(1)", " JavaScript:void(0)", "data:text/html,<b>x</b>"]:
            self.assertFalse(g.decide(C + "navigate", {"url": u})[0], u)
        self.assertTrue(g.decide(C + "navigate", {"url": "https://bank.example/statement"})[0])

    def test_other_browser_servers_guarded(self):
        self.assertFalse(g.decide("mcp__playwright__browser_click", {})[0])
        self.assertFalse(g.decide("mcp__chrome-devtools__evaluate_script", {})[0])
        self.assertTrue(g.decide("mcp__remote-devices__Claude_Browser__read_page", {})[0])
        self.assertFalse(g.decide("mcp__remote-devices__Claude_Browser__javascript_tool", {})[0])

    def test_crash_fails_closed(self):
        inp = json.dumps({"tool_name": C + "computer", "tool_input": {"action": "left_click",
                                                                      "action_summary": 5}})
        out = subprocess.run([sys.executable, SCRIPT], input=inp, capture_output=True, text=True)
        self.assertTrue(out.returncode == 2 or '"deny"' in out.stdout)
