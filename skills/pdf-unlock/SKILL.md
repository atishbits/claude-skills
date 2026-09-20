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
---

Request for this run: **$ARGUMENTS**

Run `remove_password.py <path> <password>` from this skill's folder (or with its full path). It
writes `<input>_unlocked.pdf` next to the input file by default; pass `-o <path>` to change that.

If `pypdf` isn't installed, install it with `pip install --user --break-system-packages pypdf` (this
environment's Python is externally managed) and retry.

Never write the PDF's contents, extracted text, or the password itself into this repo or into any
committed file — the input and output files live wherever the user's PDF already lives, never here.
