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

NAMESPACES = ("mcp__claude-in-chrome__", "mcp__Claude_Browser__", "mcp__remote-devices__",
              "mcp__computer-use__")
READ_TOOLS = {"tabs_context_mcp", "tabs_create_mcp", "tabs_close_mcp", "navigate", "read_page",
              "find", "get_page_text", "list_connected_browsers", "select_browser"}
LOOK_ACTIONS = {"screenshot", "zoom", "scroll", "scroll_to", "wait", "hover"}
NAV_KEYS = {"escape", "tab", "shift+tab", "up", "down", "left", "right", "page_up", "page_down",
            "home", "end"}

ALLOW = re.compile(
    r"\b(statements?|download|dates?|month|year|period|from|format|pdf|xlsx?|csv|excel|"
    r"transactions?|history|view|card|account|ok|done|close|cancel|previous|next|calendar|"
    r"filter|select)", re.I)
DENY = re.compile(
    r"\b(pay|pays|paid|paying|payments?|payee|transfer|send|beneficiar|otp|pin\b|cvv|password|"
    r"authori[sz]|confirm|approve|submit|mandate|auto ?pay|auto ?debit|standing instruction|"
    r"limit|block|unblock|hotlist|appl(y|ies|ication)|buy|invest|redeem|loan|emi|upgrade|"
    r"activate|deactivate|enable|disable|settings?|profile|nominee|address|e-?mail|mobile|"
    r"log ?out|sign ?out|delete|remove|add\b|adds\b|adding)", re.I)
DATE_TEXT = re.compile(r"^(\d{1,2}[ /.-](\d{1,2}|[A-Za-z]{3,9})[ /.-]\d{2,4}|\d{1,4})$")


def _deny(tool, why):
    return False, (f"my-spendings read-only guard: {tool} blocked ({why}). "
                   "Stop and ask the user to do this themselves.")


def _words_ok(text):
    return bool(text) and bool(ALLOW.search(text)) and not DENY.search(text)


def decide(tool_name, tool_input):
    """(allowed, reason) for one tool call."""
    ns = next((n for n in NAMESPACES if tool_name.startswith(n)), None)
    if ns is None:
        return True, ""
    tool = tool_name[len(ns):]
    ti = tool_input or {}
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
        s = f"{ti.get('action_summary', '')} {ti.get('value', '')}".strip()
        if ti.get("action_summary") and _words_ok(s):
            return True, ""
        return _deny(tool, f"form value: {s!r}")
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


if __name__ == "__main__":
    main()
