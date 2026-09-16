# Application workflow

These numbers describe the current implementation and can be used when requesting changes.

1. **Enter a posting.** Add its URL, optionally company, role, notes, and pasted posting text. Choose **Save & generate**.
2. **Save and queue.** Save the application in Applying (or the selected stage), check for duplicate links, and create a generation run with a snapshot of the master résumé.
3. **Capture the source.** Retrieve the posting text from its public URL, or use the supplied text. Save the source and capture metadata. If retrieval is blocked, request pasted text.
4. **Extract the job description.** Invoke the ChatGPT-signed-in Codex CLI with the bundled `json-job-description` skill and pinned schema to turn the source into structured JSON.
5. **Validate and save the description.** Check the job schema and essential content, then save `job-description.json`. Fill in company and role when they were left blank. Document generation starts only after this succeeds.
6. **Generate the résumé and cover letter.** In one subsequent AI request, use the saved job description and master snapshot to generate résumé JSON (following `json-resume`), cover-letter text, and tailoring notes.
7. **Validate and save the drafts.** Validate résumé schema and protected facts such as identity, dates, titles, and skills. Check basic cover-letter completeness, then save `resume.json` and `cover-letter.md`. These checks do not replace factual review of prose.
8. **Review and edit in the app.** Generation stops after step 7. Open **Review & edit documents** to edit résumé fields and cover-letter text with live HTML previews. **Save drafts** persists changes without creating PDFs. The master résumé is not changed.
9. **Download the application ZIP.** Click **Download application ZIP** once. The app saves the current edits, renders both PDFs on demand, and downloads one ZIP containing exactly `job-description.json`, `resume.pdf`, and `cover-letter.pdf`. Conflicting edits in another tab prevent an outdated export. If rendering fails, the saved drafts remain available for another download attempt.
10. **Track the application.** After applying externally, use **Mark applied** to move to Waiting on response and record the application date. Move to Interview when appropriate. Generating or downloading files does not change the application stage.

## Recovery and regeneration

- **Blocked posting:** paste its full text and retry from source capture (step 3).
- **Failed or cancelled run:** retry using saved checkpoints and the original master snapshot; completed AI work need not repeat. PDF failures are retried with the download button, without invoking AI.
- **Generate new set:** create a new run with a fresh master snapshot. Reuse previously pasted source text for the same URL; otherwise capture the URL again. Preserve previous completed documents.
- **Changed posting URL:** generate a new set; the tracker warns when existing files belong to the prior URL.
