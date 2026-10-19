# shared

Scripts more than one skill uses. Each has one master copy here and its tests in
`scripts/tests/`.

A skill that uses a shared script ships its own identical copy in its `scripts/` folder, so it
works wherever it is installed: as part of this repository, as a plugin, or as a single uploaded
folder. Never edit a copy. Edit the master here, then run `shared/sync-copies.sh` and stage the
copies it updates. `hooks/pre-commit` blocks a commit in which any copy differs from the master.

## drive_sync.py

Plans a sync between a local folder and its copy in cloud file storage, without touching the
network: Claude lists the cloud folder and moves files with a file-storage connector, and the script
decides what moves and keeps the record of the last sync. See its docstring for the commands.

A skill opts in by shipping `scripts/drive-sync.json` beside its copy:

```json
{
 "marker": "example-skill-sync.json",
 "root_env": "EXAMPLE_ROOT",
 "data_dir": "data",
 "kinds": {
  "note": {"patterns": ["notes/*.md"]},
  "document": {"patterns": ["*.pdf"], "upload": false}
 },
 "scopes": {"named": ["note:named"]}
}
```

- `marker`: the manifest's name in the cloud folder, found by exact name.
- `root_env`, `data_dir`: the working root is `--root`, else that environment variable, else the
  working directory; the synced folder is `data_dir` inside it.
- `kinds`: glob patterns, matched at the same folder depth and checked in order. `"upload": false`
  makes a kind download-only.
- `scopes`: which kinds a `plan --scope S` downloads; `kind:named` limits a kind to files named on
  the command line. Scope `all` always exists. `plan --direction down|up` keeps only one direction.
