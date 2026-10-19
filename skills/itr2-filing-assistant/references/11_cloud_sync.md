# Cloud sync

Read this only when a sync is due (see *Cloud storage* in `SKILL.md`). It moves files between the
local working folder and a folder in the user's cloud file storage, through whichever file-storage
connector is connected.

**`scripts/drive_sync.py` makes every decision about what moves; never decide by eye.** It compares
each file's local copy, its cloud copy and the state at the last sync, so an unchanged file is never
moved and an edit made on one side is not overwritten by the other. It never touches the network:
you do the moving with the connector.

What it moves, from `scripts/drive-sync.json`:

- **Up and down:** the skill's own files: `00_Document_Review*.md`, every `ITR2_*.md` conclusions
  file and the worksheet, and `sbi-tt-rates.json`.
- **Down only:** the user's documents (`.pdf`, `.json`, `.csv`, `.xlsx`, `.xls`, `.txt`) at the
  top of the cloud folder or one subfolder down. A document is never uploaded; the plan lists one
  that exists only here under `local_only`. Tell the user to put it in the cloud folder themselves
  if they want it there.

Run every command from the folder holding `SKILL.md`, with `--root` set to the working folder
(written WORKDIR below). The script keeps its own state in hidden files there (`.sync-base.json`,
`.listing-N.json`, `.manifest-in.json`).

## 1. Find the cloud folder

Search the cloud storage for files named exactly `itr2-filing-assistant-sync.json`. Each marks one
assessee's folder for one AY.

- **One match, or one whose folder is clearly this assessee and AY:** download it (base64), write it
  to a temporary file, and run
  `python3 scripts/drive_sync.py --root WORKDIR put .manifest-in.json TEMPFILE --id ID --modified TS`.
- **Several and it is unclear which:** ask the user.
- **None:** the first sync for this assessee and AY. Ask the user which cloud folder to use; suggest
  one folder per assessee per AY, and create it if they want. Then run
  `python3 scripts/drive_sync.py --root WORKDIR init --root-id FOLDER_ID`.

## 2. List

`python3 scripts/drive_sync.py --root WORKDIR listing-query` prints one search query and where to
save its results. Run the query with the connector asking for metadata only (no content), page
through every result, and save each raw page as `.listing-1.json`, `.listing-2.json`, … where it
says.

## 3. Plan

`python3 scripts/drive_sync.py --root WORKDIR plan --direction D`, where D is:

- `down` for a pull ("get my documents", "pull from the cloud");
- `up` for a push ("sync", "upload the results");
- `both` in a session with no folder of the user's, where the cloud copy is the only one that lasts.

If `relist` in the output is not empty, go back to step 2: the listing found folders its query did
not cover.

## 4. Carry out the plan

- **`download`:** fetch the file's content (base64), write it to a temporary file, then
  `python3 scripts/drive_sync.py --root WORKDIR put PATH TEMPFILE --id ID --modified TS`.
- **`conflict`** (changed in both places since the last sync): if `keep` is `remote`, run
  `python3 scripts/drive_sync.py --root WORKDIR conflict-copy PATH COPY`, then download PATH as
  above. If `keep` is `local`, download the remote file into COPY with `put`, then run
  `python3 scripts/drive_sync.py --root WORKDIR resolve-local PATH --id ID --modified TS`; the
  next `up` plan uploads the local copy. Tell the user about every conflict copy: it needs
  reconciling by hand before filing.
- **`duplicate`** (two cloud files with one name): download the older one into its `copy` with
  `put`, then move that file to the bin. Tell the user.
- **`mkdir`:** create the folder with the connector, then
  `python3 scripts/drive_sync.py --root WORKDIR folder PATH --id ID`, and plan again.
- **`upload`:** read the local file and create it in `parent` with the connector (content type
  `mime`, no conversion to a native document type). Then run
  `python3 scripts/drive_sync.py --root WORKDIR uploaded PATH --id NEWID --modified TS --size BYTES`
  with the values from the result. If it refuses because the size differs, bin the new file and
  upload again. Otherwise move `old_id`, if there is one, to the bin.

Never change a file's or folder's sharing.

## 5. Write the manifest

After any upload: `python3 scripts/drive_sync.py --root WORKDIR manifest`, upload the file it names
as `itr2-filing-assistant-sync.json` into `parent`, then move `old_id`, if there is one, to the bin.

## 6. Report

One line: how many files came down and went up, any conflict copies, and any documents listed
under `local_only`.

If the connector fails partway, say so and stop the sync. The next sync picks up what is left.
