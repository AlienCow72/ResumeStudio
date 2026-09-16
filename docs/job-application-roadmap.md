# Job application workflow — proposed roadmap

Date: 2026-09-15. Implemented: tracker, posting capture and schema validation,
subscription-backed generation, automatic résumé/cover-letter generation
after posting JSON, PDF/source downloads, progress, cancellation, checkpointed
retry, and preserved generation runs. A live WEC application exercised the full
pipeline. Job-specific draft editing/preview and attaching an exact document
revision to “Mark applied” remain future work. The design below records the
broader roadmap; current usage is documented in the README.

## Intended experience

Add a job posting URL, capture the posting as JSON, generate a job-specific résumé and cover letter, review/edit the documents, download them, and track the application through **Applying → Waiting on response → Interview**.

Only job descriptions, résumés, and cover letters are in scope. Generated content must not invent facts.

## Current foundation

- `src/server.py`: local Python HTTP server, résumé save, preview, and export routes.
- `src/versions.py`: master data, stable item IDs, version selections, objective overrides, backups, and revision conflict checks.
- `src/app.js` / `src/index.html`: existing editor UI.
- `src/render.py` / `src/pdf.cjs`: HTML and Chrome-based PDF rendering.
- `data/resume.json`: current master; `data/versions.json`: selections and formatting.

Current named versions select shared master content and override only the objective. They cannot independently rewrite experience bullets. Job documents therefore need separate editable snapshots, with the master revision recorded. Reuse the editor/rendering components, while keeping existing named versions compatible.

## Subscription-backed generation

Recommended first implementation: a local generation adapter that invokes the installed Codex CLI with ChatGPT authentication. The current machine has `codex-cli 0.154.0`; `codex login status` reports **Logged in using ChatGPT**. No generation request was made during planning.

OpenAI documents ChatGPT sign-in for subscription access and API-key sign-in for separately billed usage. Non-interactive execution reuses saved CLI authentication and can return structured output. This makes a local subscription-backed workflow a viable design, subject to account access and usage limits. The full pipeline still needs an integration test. Sources: [authentication](https://learn.chatgpt.com/docs/auth), [non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode).

Keep generation behind an adapter so the [Codex App Server](https://learn.chatgpt.com/docs/app-server), which supports managed ChatGPT login and account-limit reporting, can replace the CLI bridge if an integrated sign-in experience becomes useful. Do not silently switch to paid API usage when subscription access fails.

Run generation outside HTTP request handling. Show progress, allow cancellation, and retry failed steps independently. Pass inputs through structured process arguments/stdin, validate outputs in Python, and let the application commit files. Give generation only the input files and tools needed for its task. Treat posting content as untrusted source text, not instructions.

## Delivery sequence

| Update | Deliverable | Acceptance criteria |
| --- | --- | --- |
| 1. Tracker and storage | Jobs screen; add URL and basic details; three stages; persistent job records; posting links. | Jobs and stages survive restart; duplicate URLs are flagged without merging distinct requisitions; existing résumé editing still works. |
| 2. Posting capture | Fetch posting; preserve source text, URL, and capture time; use `json-job-description`; save `job.json`. | Validate against a pinned draft job schema; preserve requirements and responsibilities separately; omit unknown facts; blocked/expired pages offer pasted-text import. |
| 3. Generation foundation | Local Codex adapter, explicit skill inputs, background runs, progress/errors/cancel/retry. | Verify ChatGPT authentication, run one end-to-end generation, handle missing CLI, expired login, usage limits, invalid output, and interruption without losing saved work. |
| 4. Résumé drafts | Generate a job-specific JSON Resume document from a saved master snapshot and the captured job; add independent editing and preview. | Drafts validate against a pinned résumé schema; dates/titles/credentials stay factual; master remains intact; review highlights changed wording and unsupported job requirements. |
| 5. Cover letter and downloads | Generate editable letter from job and verified experience; render both application documents; add quick PDF downloads. | Separate résumé and cover-letter buttons deliver the correct job's saved revision; filenames identify company, role, and document; visually verify representative PDFs. |
| 6. Submission history and reliability | “Mark applied” records application date and document revision; stage history, notes, search/filter; recovery checks. | Later master edits or regeneration cannot change submitted files; missing PDFs can be rerendered from saved sources; partial failures do not erase good artifacts. |

Updates 2 and 3 connect to form the automated extraction workflow. The tracker can be useful before generation is integrated, using manual job details and imported documents.

## Screens and behavior

**Jobs:** a three-column board with company, role, date added/applied, generation progress, posting link, and Résumé / Cover letter PDF actions. Include search and a stage selector usable without dragging. Unavailable downloads explain whether generation or review is still needed.

**Job detail:** source posting and captured description; editable documents with preview; generation/retry actions; notes and stage history. JSON and Markdown source downloads can live here without crowding the board.

**Stages:** new jobs start in Applying. “Mark applied” moves a job to Waiting on response and records the chosen document revision. Interview is a user-selected stage. Generating/downloading documents does not imply the application was submitted. Allow corrections to stages and dates; preserve their history.

**Review:** generated documents are drafts. Users can accept them together or edit them individually. Regeneration creates a new revision instead of overwriting edited or submitted content. Downloads identify whether they are the current draft or the submitted version.

Generation state is separate from application stage: queued, running, needs input, ready for review, failed, cancelled. A job can remain Applying while extraction is blocked or its documents are being edited.

## Proposed persistence

Keep local files for the first release, consistent with the current app. Use stable job IDs unrelated to company/title changes. Keep tracking metadata outside the portable job and résumé schemas.

```text
data/jobs/<job-id>/
  application.json                 # Stage, dates, history, notes, selected revisions
  captures/<capture-id>/
    source.txt                     # Preserved posting text
    source.json                    # Original/final URL, capture time/method, schema revision
    job.json                       # Structured job description
  documents/<revision-id>/
    master-snapshot.json           # Verified source facts used for this revision
    resume.json
    cover-letter.md
    manifest.json                  # Input hashes, capture ID, model/skill versions, review state
  runs/<run-id>.json                # Progress and recoverable failure state
output/jobs/<job-id>/<revision-id>/
  resume.pdf
  cover-letter.pdf
```

Use atomic writes, per-job revision checks, and backups. Build the board from application records initially; add an index only if needed. Submitted revisions are immutable. Draft saves create revisions so downloaded files remain traceable. Edits invalidate derived PDF caches; rerender only from the requested saved revision.

## Generation contract

- Read and version the `json-job-description` and `json-resume` skill instructions and schema references as explicit generation inputs. Skills guide behavior; the app must separately implement orchestration and validation.
- Pin schema files and their upstream revisions in the repository. The job schema is a draft; schema validity alone does not establish source fidelity or useful extraction.
- Capture the posting before tailoring. Missing essential title/company/body information requires review or pasted text instead of guessed content.
- Generate résumés from verified master facts, using the job to choose emphasis and wording. Surface qualification gaps for review; do not insert missing skills into the master or drafts.
- Generate the cover letter from the same facts and captured job. Avoid invented company motivations, recruiter names, or unsupported claims.
- Store model/skill/schema identifiers and input hashes with each run. Require both valid structured output and application-level completeness checks before declaring a step successful.
- Protect the local URL fetcher against private-network targets and unsafe redirects; support ordinary HTTP(S) postings only. Escape imported/generated content in previews.
- Update the README's current claim that résumé data is never sent externally: AI generation sends selected inputs to OpenAI when invoked.

## Validation and boundaries

Use temporary application data in tests. Cover persistence and revision conflicts, allowed stages, blocked imports, schema failures, retry/cancel behavior, master preservation, independent job drafts, submitted-file immutability, and job/document download routing. Run the existing regression suite after code changes and inspect representative résumé and cover-letter PDFs for clipping, page breaks, and text retention.

First release is a personal local app. Automatic submission, email sending, account creation on job sites, hosted multi-user access, and additional application stages are outside this plan. Archive/outcome tracking can be added later without changing the three active stages.

Next implementation step: Update 1, followed by the posting capture and Codex integration needed for Updates 2–3.
