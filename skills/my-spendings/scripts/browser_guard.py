#!/usr/bin/env python3
"""Read-only rail for bank and card websites: a Claude Code PreToolUse hook
that my-spendings declares while it is active.

Browser tools get an allowlist: reading pages, opening and closing tabs, and
clicks or form choices whose own description is about statements, dates and
file formats. Anything that could move money, change a setting or reveal a
secret is denied, and so is any tool the list does not know (page scripts,
batched actions, uploads). The decision keys off Claude's own description of
each action, so it stops mistakes and instructions planted in a page, not a
model that mislabels on purpose; the user still watches.

Reads the hook's JSON on stdin; prints a deny decision, or nothing to allow.
"""
import json
import re
import sys

# Browser-driving servers: the four Claude ones plus any MCP server whose name
# says it drives a browser or a desktop. Matched on the server part of the name.
GUARDED = re.compile(r"chrome|browser|playwright|puppeteer|selenium|devtools|computer", re.I)
READ_TOOLS = {"tabs_context_mcp", "tabs_create_mcp", "tabs_close_mcp", "navigate", "read_page",
              "find", "get_page_text", "list_connected_browsers", "select_browser"}
LOOK_ACTIONS = {"screenshot", "zoom", "scroll", "scroll_to", "wait", "hover"}
NAV_KEYS = {"escape", "tab", "shift+tab", "up", "down", "left", "right", "page_up", "page_down",
            "home", "end"}

# A click or form choice must be about getting a statement: these words say so.
INTENT = re.compile(r"\b(statements?|download|dates?|month|year|period|format|pdf|xlsx?|csv|excel|"
                    r"calendar)", re.I)
# Anything that commits, moves money, changes a setting or touches a secret.
DENY = re.compile(
    r"\b(pay|pays|paid|paying|payments?|payee|transfer|send|beneficiar|otp|pin\b|m-?pin|cvv|password|"
    r"authori[sz]|confirm|approve|submit|proceed|continue|complete|yes\b|accept|agree|save|update|"
    r"change|request|stop|freeze|lock|unlock|convert|book|create|register|verify|reset|dispute|"
    r"mandate|auto ?pay|auto ?debit|standing instruction|limit|block|unblock|hotlist|"
    r"appl(y|ies|ication)|buy|invest|redeem|withdraw|loan|emi\b|upgrade|activate|deactivate|"
    r"enable|disable|settings?|profile|nominee|address|e-?mail|mobile|log ?out|sign ?out|delete|"
    r"remove|cancel|close (the )?(account|card|fd|deposit)|fd\b|fixed deposit|deposit|amount|"
    r"recipient|upi\b|rupees|add\b|adds\b|adding)|₹", re.I)
DATE_TEXT = re.compile(r"^(\d{1,2}[ /.-](\d{1,2}|[A-Za-z]{3,9})[ /.-]\d{2,4}|(19|20)\d\d)$")
VALUE_OK = re.compile(
    r"^((\d{1,2}[ /.-](\d{1,2}|[A-Za-z]{3,9})[ /.-]\d{2,4})|(\d{4}-\d{2}-\d{2})|((19|20)\d\d)|"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*( (19|20)\d\d)?|pdf|xlsx?|csv|excel|"
    r"((last|previous|current|this) ([0-9]{1,2} )?(days?|weeks?|months?|quarters?|years?|financial year)))$",
    re.I)
BAD_URL = re.compile(r"^\s*(javascript|data|vbscript|file):", re.I)


def _deny(tool, why):
    return False, (f"my-spendings read-only guard: {tool} blocked ({why}). "
                   "Stop and ask the user to do this themselves.")


def _words_ok(text):
    return bool(text) and bool(INTENT.search(text)) and not DENY.search(text)


def decide(tool_name, tool_input):
    """(allowed, reason) for one tool call."""
    parts = tool_name.split("__")
    if len(parts) < 3 or parts[0] != "mcp" or not GUARDED.search("__".join(parts[1:-1])):
        return True, ""
    tool = tool_name.split("__")[-1]
    ti = tool_input or {}
    if tool == "navigate":
        url = str(ti.get("url", ""))
        return _deny(tool, f"script URL {url[:30]!r}") if BAD_URL.match(url) else (True, "")
    if tool in READ_TOOLS:
        return True, ""
    if tool == "computer":
        action = ti.get("action", "")
        if action in LOOK_ACTIONS:
            return True, ""
        if action == "left_click":
            s = ti.get("action_summary", "")
            return (True, "") if _words_ok(s) else _deny(f"{tool}/{action}", f"click: {s!r}")
        if action == "type":
            t = str(ti.get("text", "")).strip()
            return (True, "") if DATE_TEXT.match(t) else _deny(f"{tool}/{action}", "only dates may be typed")
        if action == "key":
            keys = str(ti.get("text", "")).lower().split()
            if keys and all(k in NAV_KEYS for k in keys):
                return True, ""
            return _deny(f"{tool}/{action}", "only navigation keys")
        return _deny(f"{tool}/{action}", "action not on the read-only list")
    if tool == "form_input":
        summary, value = ti.get("action_summary", ""), str(ti.get("value", "")).strip()
        if _words_ok(summary) and VALUE_OK.match(value) and not DENY.search(value):
            return True, ""
        return _deny(tool, f"form value {value[:30]!r} for {summary!r}")
    return _deny(tool, "tool not on the read-only list")


def main():
    try:
        data = json.load(sys.stdin)
        ok, why = decide(data.get("tool_name", ""), data.get("tool_input") or {})
    except Exception as e:  # fail closed
        ok, why = _deny("hook", f"unreadable hook input: {e}")
    if not ok:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": why}}))


def _main_fail_closed():
    try:
        main()
    except BaseException as e:  # any crash blocks the call (exit 2) rather than letting it through
        print(f"my-spendings read-only guard crashed: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    _main_fail_closed()
