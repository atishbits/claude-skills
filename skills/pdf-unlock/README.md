# pdf-unlock

Removes the open password from a password-protected PDF, given the correct password, and writes an
unlocked copy next to the original (`<name>_unlocked.pdf`, or wherever `-o` says).

```
python3 remove_password.py <path to PDF> <password> [-o <output path>]
```

It needs Python with `pypdf[crypto]` (the `[crypto]` extra opens the AES-256 PDFs many banks use),
or the `qpdf` command. Without either it exits with status 3 and names the missing package.

## Your files stay yours

The skill keeps no data of its own: no `data/` folder, no cloud copy, no notes. The input and the
unlocked copy stay wherever your PDF already is, and the password is used for that one run only.
Never write either into this repo.

## Where it runs

Anywhere with Python: Claude Code, a desktop app with a folder shared to the session, or the Claude
app with a file attached. Install it as a plugin (see the repository README) or symlink this folder
into `~/.claude/skills/`.
