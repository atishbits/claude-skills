# Cloud sync

Read this only when a sync is due (see *Cloud storage* in `SKILL.md`). It moves files between the
working root's `data/` folder and a folder in the user's cloud file storage, through whichever
file-storage connector is connected. The cloud folder mirrors `data/` itself, not the root.

**`scripts/drive_sync.py` makes every decision about what moves; never decide by eye.** It compares
each file's local copy, its cloud copy and the state at the last sync, so an unchanged file is never
moved and an edit made on one side is not overwritten by the other. It never touches the network:
you do the moving with the connector.

What it moves, from `scripts/drive-sync.json`, all of it both ways:

- the skill's state: `profile.json`, `notes.md`, and in `skill-data/` the bond facts, the ratings
  ledger, `PORTFOLIO.md`, `POSITIONS.md`, `bond-interest.json` and the issuer notes in `bonds/`;
- what a session with a browser pulled from the platform: holdings reports saved as
  `*report-<date>.xlsx`, listings captures, and the snapshots and listings `ingest.py` made of them;
- the saved runs in `skill-data/runs/`.

A holdings report under the platform's own download name does not move (that name can carry a
phone number); rename it as Step 1 says.

Run every command from the folder holding `SKILL.md`, with `--root` set to the working root
(written WORKROOT below, the folder that holds `data/`). The script keeps its own state in hidden
files in `data/` (`.sync-base.json`, `.listing-N.json`, `.manifest-in.json`).

## 1. Find the cloud folder

Search the cloud storage for files named exactly `bond-portfolio-monitor-sync.json`. It marks the
cloud folder.

- **One match:** download it (base64), write it to a temporary file, and run
  `python3 scripts/drive_sync.py --root WORKROOT put .manifest-in.json TEMPFILE --id ID --modified TS`.
- **Several:** ask the user which.
- **None:** the first sync. Ask the user which cloud folder to use (suggest one named
  `bond-portfolio-monitor`), create it if they want, then run
  `python3 scripts/drive_sync.py --root WORKROOT init --root-id FOLDER_ID`.

## 2. List

`python3 scripts/drive_sync.py --root WORKROOT listing-query` prints one search query and where to
save its results. Run the query with the connector asking for metadata only (no content), page
through every result, and save each raw page as `.listing-1.json`, `.listing-2.json`, … where it
says.

## 3. Plan

`python3 scripts/drive_sync.py --root WORKROOT plan --direction D`, where D is `down` for a pull
(including the one at the start of a session with a temporary folder), `up` for a push, and
`both` when the user asks to sync without saying which way.

If `relist` in the output is not empty, go back to step 2.

If `check_first` is set, run that search too (metadata only). Anything it finds is a file the
listing left out: save the results as one more `.listing-N.json` page and plan again.

## 4. Carry out the plan

- **`download`:** fetch the file's content (base64), write it to a temporary file, then
  `python3 scripts/drive_sync.py --root WORKROOT put PATH TEMPFILE --id ID --modified TS`.
- **`conflict`** (changed in both places since the last sync): if `keep` is `remote`, run
  `python3 scripts/drive_sync.py --root WORKROOT conflict-copy PATH COPY`, then download PATH as
  above. If `keep` is `local`, download the remote file into COPY with `put`, then run
  `python3 scripts/drive_sync.py --root WORKROOT resolve-local PATH --id ID --modified TS`; the
  next `up` plan uploads the local copy. Tell the user about every conflict copy: a profile,
  ledger or issuer note in two versions needs reconciling by hand.
- **`duplicate`** (two cloud files with one name): download the older one into its `copy` with
  `put`, then move that file to the bin. Tell the user.
- **`mkdir`:** create the folder with the connector, then
  `python3 scripts/drive_sync.py --root WORKROOT folder PATH --id ID`, and plan again.
- **`upload`:** read the local file and create it in `parent` with the connector (content type
  `mime`, no conversion to a native document type). Send a spreadsheet as base64, never as text. Then run
  `python3 scripts/drive_sync.py --root WORKROOT uploaded PATH --id NEWID --modified TS --size BYTES`
  with the values from the result. If it refuses because the size differs, bin the new file and
  upload again. Otherwise move `old_id`, if there is one, to the bin.

Never change a file's or folder's sharing.

## 5. Write the manifest

After any upload: `python3 scripts/drive_sync.py --root WORKROOT manifest`, upload the file it names
as `bond-portfolio-monitor-sync.json` into `parent`, then move `old_id`, if there is one, to the bin.

## 6. Report

One line: how many files came down and went up, and any conflict copies.

If the connector fails partway, say so and stop the sync. The next sync picks up what is left.
