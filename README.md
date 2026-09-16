# Resume Studio

Double-click `start.command` on macOS and open http://127.0.0.1:8765. The launcher stops the existing instance of this editor (including instances in other Git worktrees of this repository) and restarts on the same port. Unrelated applications using the port are left running. Keep its terminal open; Control-C stops the server.

## Repository layout

```text
src/                 Application code, UI assets, and rendering helpers
tests/               Automated tests using temporary résumé data
output/              Generated version JSON and rendered résumé files
data/
  resume.json        Active master résumé
  versions.json      Version selections, stable IDs, and formatting settings
  backups/           Timestamped save backups (ignored by Git)
  jobs/              Application records and per-job backups
  originals/         Preserved original JSON and Markdown source documents
README.md            Setup and usage
start.command        macOS launcher
requirements.txt     Python application dependencies
```

## Setup and development

Double-click `start.command`, or run `./start.command` from the repository root.
The launcher creates a local `.venv` and installs `requirements.txt` on first
launch (internet required). It checks dependencies on subsequent launches and
installs updates when requirements change. The shared Codex runtime is not modified.
To run the server directly without opening a browser:

```sh
.venv/bin/python3 src/server.py --port 8765
```

Python uses the standard library for editing and HTML/JSON/Markdown exports.
PDF export additionally requires Google Chrome, Node.js, and Playwright. The
installed Codex runtime is used when available. Otherwise install Playwright
with `npm install --no-save --package-lock=false playwright` at the repository
root. For manual setup, install Python application dependencies with
`python3 -m pip install -r requirements.txt` in your Python environment.
Set `RESUME_CHROME` to use another Chromium executable.

Run tests from the repository root:

```sh
PYTHONPATH=src .venv/bin/python3 -m unittest discover -s tests -v
```

Paths resolve relative to the application files, so the server can also be
started from another working directory using its absolute path. The server
binds only to 127.0.0.1. Editing and rendering stay local. Application generation
sends the captured posting and a snapshot of your master résumé to OpenAI
through your ChatGPT-signed-in Codex CLI.

## Job tracker

Open **Job tracker** from the editor header, or visit http://127.0.0.1:8765/jobs.
Add a posting link and choose **Save & generate**. Company and role are extracted
automatically when left blank. Optional notes
and an application date are editable from each card's title or **View details**.
Search matches company, role, and notes.

The board has three stages: **Applying**, **Waiting on response**, and
**Interview**. Use each card's stage selector to move it. **Mark applied** moves
a job to Waiting on response and fills today's date if no application date is
recorded. Selecting Waiting on response has the same date behavior. You can
correct the date in job details. Stage changes are recorded in the detail view.
These actions track your progress; they do not submit an application.

Records persist in `data/jobs/<id>/application.json`, independently of the
master résumé. Each edit backs up the previous record in that job's `backups/`
directory and rejects stale saves from another tab. Use **Refresh** to reload
the board. Duplicate posting links are flagged; you can open the existing job
or explicitly save a separate application. Requisition query parameters are
preserved when comparing links.

Generation runs in the background in this order:

1. Retrieve the public posting and use the bundled `json-job-description` skill
   to create and validate `job-description.json`.
2. Only after the description is saved, automatically generate job-specific résumé
   JSON using `json-resume`, plus a job-specific cover letter. Candidate
   facts come from the saved master snapshot. The master is never overwritten.
3. Stop at editable drafts. Open **Review & edit documents** on the job card.
   Edit résumé fields and cover-letter text with live HTML previews. **Save drafts**
   saves application-specific changes; neither saving nor previewing renders PDFs.
4. Click **Download application ZIP** after review. The app saves any current edits,
   then renders PDFs and downloads exactly `job-description.json`, `resume.pdf`,
   and `cover-letter.pdf` in one ZIP. The cover-letter header uses the reviewed
   résumé contact details. PDFs are created only for this explicit download.

Drafts are saved atomically in each run's `draft.json`, with revision conflict
checks and backups under `draft-history/`. Generated originals and the master
remain intact. Manual corrections are checked against the résumé schema; users
can intentionally correct facts. A rendering failure preserves the saved draft;
retry the download without generating new content. Older runs with existing PDFs
also open in the draft editor; downloads render from the current reviewed draft.

Existing tracked jobs have a **Generate documents** button. For blocked or
JavaScript-only postings, open **Paste posting text**, supply the full description,
and choose **Retry generation**. Cancellation retains saved progress. Retrying
an interrupted/failed run reuses its saved posting and document data, including
the original master snapshot; a download failure does not consume another AI run.
**Generate new set** takes a fresh master snapshot and preserves older run files.
If the posting link changes, generate a new set; the tracker flags files based
on the previous link. Older run files remain on disk.

Install [Codex CLI](https://learn.chatgpt.com/docs/cli) and run `codex login` to
sign in with ChatGPT. `codex login status` must report ChatGPT authentication.
The app uses non-interactive `codex exec`, with saved subscription authentication,
no shell tools, a read-only sandbox, and no API-key billing fallback. Subscription
usage limits apply. Install the Python requirements with
`python3 -m pip install -r requirements.txt`; Chrome, Node, and Playwright are
required for PDFs as described above. Each AI step has a ten-minute timeout;
one application is processed at a time.

Run data lives in `data/jobs/<id>/runs/<run-id>/`: captured source text/metadata,
the master snapshot, validated job and résumé JSON, cover-letter text, editable drafts,
and a progress manifest. PDFs are rendered in memory when downloading the ZIP. `generation.json` identifies the latest run. Old runs
are retained; generated files are not tied to later changes in the master.
Schemas and skill snapshots are pinned in `src/generation_resources/`, with the
upstream schema commit recorded in `provenance.json`. The job schema is a draft.
Automated schema and identity/date/skill checks complement review; they do not
prove every generated prose claim is supported.

The broader [roadmap](docs/job-application-roadmap.md) also covers attaching exact document revisions to application submissions.
See the [numbered workflow](docs/application-workflow.md) to refer to individual
steps when discussing changes.

## Master and versions

`data/resume.json` is the complete editable master, including the default
objective. Keep it together with `data/versions.json`, which stores stable
field/entry IDs, version names, exclusions, summary overrides, and highlight
indentation.

Saving regenerates `output/resume-{version}.json` for every saved version.
These are portable outputs, not editable sources. Existing `output/resume.html`
and `output/resume.pdf` are preserved rendered artifacts; saving in the editor
does not regenerate them.

`data/originals/` preserves the earlier source documents. If both active save
files are absent, first launch copies `data/originals/resume.json` into
`data/resume.json` and creates version settings. Relaunching never overwrites an
existing master. Backups live in `data/backups/{timestamp}/` and contain the
previous master, settings, and affected generated JSON files.

Use **Master — All information** to add, edit, remove, or reorder facts. **Advanced JSON** supports custom fields and checks JSON syntax and structure before applying changes; exact matches keep IDs, while rewritten list text is treated as a new item. Use form fields when rewriting highlights or keywords to retain their selections. Stable IDs follow items through form edits and reordering. New items are included by default in every version. Removing a master item removes it from every version.

Use the centered version dropdown and **New / Duplicate / Rename / Delete** buttons to manage versions. Changes are saved explicitly. Switching with unsaved edits offers Save, Discard, or Cancel. Deleting a version does not remove master information.

Within a version:

- Check or uncheck entire sections, entries, fields, highlights, and keywords. Excluded content stays visible but dimmed. Turning a parent back on restores the children's previous selections.
- Content is read-only. **Edit in Master** switches to the source fields.
- The objective can use **Customize for this version** or **Reset to master**. A custom objective does not change when the master objective changes.
- Work highlights have indent/outdent arrows for levels 0–3. Exports use nested bullets; if exclusions remove a parent, indentation is normalized so the first remaining bullet is not orphaned.
- Highlights, keywords, courses, profiles, and other nested lists are collapsible.

Saving backs up the prior files, saves the master/settings, and regenerates every named version JSON. Renamed/deleted output filenames are retired after backing them up. Saving rejects stale revisions. Use the UI for master edits: editing `resume.json` externally bypasses stable IDs and is detected. To restore a backup, restore its `resume.json` and `versions.json` together into `data/`. Generated version JSON can be restored into `output/`, or regenerated on the next save.

## Exports

**Export** downloads the active draft as JSON, Markdown, printable HTML, or PDF, without saving. Downloads go to your browser’s download location; choose `output/` when you want to keep an export in this repository. Named versions download as `resume-{version}.{format}`; master downloads as `resume.{format}`. JSON contains only selected content, with the summary override in `basics.summary`. Editor IDs, selection settings, and indentation stay in `versions.json`.

HTML and PDF share the original navy/teal two-column design, with Education above Skills. The header subtitle comes from Basics → Label. All selected text is retained, so page count can vary.

The objective uses the standard JSON Resume `basics.summary` field. `basics.profiles` contains account links such as GitHub and LinkedIn.

## Preview modes

The preview has HTML and PDF tabs. PDF shows rasterized pages from the actual export, with the US Letter page count and a notice when it exceeds one page. It updates after edits, without saving. PDF preview requires `pypdfium2` and `Pillow` (included in the Codex Python runtime); otherwise install them in the Python environment running the server.
