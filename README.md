# Resume Studio

Double-click `start.command` on macOS and open http://127.0.0.1:8765. The launcher stops the existing instance of this editor and restarts on the same port. Keep its terminal open; Control-C stops the server.

## Repository layout

```text
src/                 Application code, UI assets, and rendering helpers
tests/               Automated tests using temporary résumé data
output/              Generated version JSON and rendered résumé files
data/
  resume.json        Active master résumé
  versions.json      Version selections, stable IDs, and formatting settings
  backups/           Timestamped save backups (ignored by Git)
  originals/         Preserved original JSON and Markdown source documents
README.md            Setup and usage
start.command        macOS launcher
requirements.txt     Python preview dependencies
```

## Setup and development

Double-click `start.command`, or run `./start.command` from the repository root.
To run the server directly without opening a browser:

```sh
python3 src/server.py --port 8765
```

Python uses the standard library for editing and HTML/JSON/Markdown exports.
PDF export additionally requires Google Chrome, Node.js, and Playwright. The
installed Codex runtime is used when available. Otherwise install Playwright
with `npm install --no-save --package-lock=false playwright` at the repository
root and install PDF preview dependencies with
`python3 -m pip install -r requirements.txt` in your Python environment.
Set `RESUME_CHROME` to use another Chromium executable.

Run tests from the repository root:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Paths resolve relative to the application files, so the server can also be
started from another working directory using its absolute path. The server
binds only to 127.0.0.1. Resume content is not sent to an external service.

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
