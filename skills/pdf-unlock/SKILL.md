---
name: pdf-unlock
description: >-
  Remove the open password from a password-protected PDF, given the correct password. Use when the
  user has an encrypted/password-protected PDF (e.g. a bank statement, e-Aadhaar, a bill) and wants
  a copy that opens without a password.
argument-hint: "<path to PDF> <password>"
allowed-tools:
  - Bash(python3 *remove_password.py*)
  - Bash(pip install *pypdf*)
  - Bash(python3 -m pip install *pypdf*)
---

Request for this run: **$ARGUMENTS**

Run `python3 ${CLAUDE_SKILL_DIR}/remove_password.py <path> <password>`. It writes
`<input>_unlocked.pdf` next to the input file by default; pass `-o <path>` to change that.

If pypdf is missing, the script uses the `qpdf` command when it is installed. If it exits with
status 3, it is missing a package, and its message names it. Install `pypdf[crypto]` and retry. The
`[crypto]` extra matters: without it pypdf cannot open AES-256 PDFs, which many banks use. Try these
in order and stop at the first that works:

1. `pip install 'pypdf[crypto]'`
2. `pip install --user --break-system-packages 'pypdf[crypto]'` (for a Python that refuses with
   "externally-managed-environment")

If neither works (no network or no pip in this environment), tell the user that this environment
cannot install pypdf, and that the script runs anywhere with Python and `pypdf[crypto]`, or with
`qpdf`. Do not try other ways of decrypting the PDF.

Never write the PDF's contents, extracted text, or the password itself into this repo or into any
committed file — the input and output files live wherever the user's PDF already lives, never here.
