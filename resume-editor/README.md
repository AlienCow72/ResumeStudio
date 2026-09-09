# Resume Studio

Double-click `start.command` on macOS and open http://127.0.0.1:8765. The launcher stops the existing instance of this editor and restarts on the same port. Keep its terminal open; Control-C stops the server.

## Master and versions

All working files now live inside `resume-editor/`:

- `resume.json`: the complete master, including the default objective.
- `versions.json`: stable field/entry IDs, version names, exclusions, summary overrides, and highlight indentation. Keep this file together with the master.
- `resume-{version}.json`: generated, portable JSON Resume content for each saved version. These are outputs, not editable sources.
- `backups/{timestamp}/`: previous master, settings, and affected generated files. Earlier timestamped backups are also retained.

On first launch the parent `resume.json` is copied into this directory without changing the original. Future saves use only the copy inside `resume-editor/`. Relaunching never overwrites an existing local master.

Use **Master — All information** to add, edit, remove, or reorder facts. **Advanced JSON** supports custom fields and checks JSON syntax and structure before applying changes; exact matches keep IDs, while rewritten list text is treated as a new item. Use form fields when rewriting highlights or keywords to retain their selections. Stable IDs follow items through form edits and reordering. New items are included by default in every version. Removing a master item removes it from every version.

Use the centered version dropdown and **New / Duplicate / Rename / Delete** buttons to manage versions. Changes are saved explicitly. Switching with unsaved edits offers Save, Discard, or Cancel. Deleting a version does not remove master information.

Within a version:

- Check or uncheck entire sections, entries, fields, highlights, and keywords. Excluded content stays visible but dimmed. Turning a parent back on restores the children's previous selections.
- Content is read-only. **Edit in Master** switches to the source fields.
- The objective can use **Customize for this version** or **Reset to master**. A custom objective does not change when the master objective changes.
- Work highlights have indent/outdent arrows for levels 0–3. Exports use nested bullets; if exclusions remove a parent, indentation is normalized so the first remaining bullet is not orphaned.
- Highlights, keywords, courses, profiles, and other nested lists are collapsible.

Saving backs up the prior files, saves the master/settings, and regenerates every named version JSON. Renamed/deleted output filenames are retired after backing them up. Saving rejects stale revisions. Use the UI for master edits: editing `resume.json` externally bypasses stable IDs and is detected. To restore a backup, restore its `resume.json` and `versions.json` together.

## Exports

**Export** downloads the active draft as JSON, Markdown, printable HTML, or PDF, without saving. Named versions download as `resume-{version}.{format}`; master downloads as `resume.{format}`. JSON contains only selected content, with the summary override in `basics.summary`. Editor IDs, selection settings, and indentation stay in `versions.json`.

HTML and PDF share the original navy/teal two-column design, with Education above Skills. The header subtitle comes from Basics → Label. All selected text is retained, so page count can vary.

Python uses the standard library. PDF export additionally requires Google Chrome, Node.js, and Playwright. The installed Codex runtime is used when available; otherwise install Playwright with `npm install playwright` in this directory. Set `RESUME_CHROME` to use another Chromium executable. Alternatively run `python3 server.py --port 8765` here.

The server binds only to 127.0.0.1. Resume content is not sent to an external service. Tests use temporary copies: `python3 -m unittest test_server -v` from this directory.

The objective uses the standard JSON Resume `basics.summary` field. `basics.profiles` contains account links such as GitHub and LinkedIn.
