# Resume Studio

Double-click `start.command` on macOS, then use http://127.0.0.1:8765. Keep the terminal open; press Control-C to stop.

Alternatively, run `python3 server.py` from this directory. Use `--port 8766` if the default port is occupied, then open that port in your browser.

- Edit standard JSON Resume sections, add/remove/reorder entries, and see a live preview.
- Advanced JSON supports custom fields. Unknown data is preserved in JSON; custom sections are rendered as text in document exports. Profile images and metadata are not rendered in documents.
- **Save changes** writes the parent `resume.json`, with timestamped originals in `backups/`. It refuses to overwrite a file changed externally since loading. Reload to pick up external changes, exporting your draft first if necessary.
- **Export** downloads the current draft as JSON, Markdown, standalone printable HTML, or an actual PDF. Exporting does not save the source file.
- Blank optional form fields are omitted on save/export. Dates should use YYYY, YYYY-MM, or YYYY-MM-DD. Omit end dates for ongoing work.
- HTML and PDF share the reference resume.html theme. PDF export requires Google Chrome (or RESUME_CHROME pointing to a Chromium executable), Node.js, and Playwright. The installed Codex runtime is used when available; otherwise install Playwright with `npm install playwright` in this directory. Print backgrounds are preserved.

The app binds only to 127.0.0.1 and uses no CDN, remote service, or telemetry. Basic structural validation is included; this is not a full JSON Resume schema validator. Drafts remain in the browser tab until saved; closing warns about unsaved edits.

The shared HTML/PDF theme follows the original resume.html. The header subtitle comes from Basics → Label. Full JSON text is retained, so page count may differ from the shorter reference.
