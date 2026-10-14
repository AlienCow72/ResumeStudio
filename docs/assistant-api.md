# Local assistant API

Start Resume Studio with `./start.command`. The server binds to `127.0.0.1`
(default port 8765). Send JSON to existing job endpoints. Browser writes must be
same-origin. No application is submitted or employer contacted by these actions.

## Create and poll

Company, title, notes, and pasted posting text are optional. Creation queues
posting extraction and document generation and returns immediately (`201`).
Generation uses the user's ChatGPT-authenticated Codex CLI. Explicit
`"generate": false` saves without generation.

```sh
curl -s http://127.0.0.1:8765/api/jobs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: assistant-job-123' \
  -d '{"job":{"url":"https://example.com/careers/job-123","notes":"Added by an assistant"}}'
```

The returned `id` is stable. Poll it rather than repeatedly creating jobs:

```sh
curl -s http://127.0.0.1:8765/api/jobs/JOB_ID
curl -s http://127.0.0.1:8765/api/jobs
curl -sG http://127.0.0.1:8765/api/jobs \
  --data-urlencode 'url=https://example.com/careers/job-123'
```

Single-job lookup returns `404` if absent. Lists and URL lookups always return
`{"jobs": [...]}`, including `{"jobs": []}` for no matches.

Each job response includes:

| Field | Meaning |
| --- | --- |
| `stage` | `applying`, `waiting`, `interview`, or `rejected` |
| `generationStatus` | `not_started`, `queued`, `extracting`, `writing`, `ready`, `failed`, `needs_input`, `cancelled`, or `interrupted` (legacy active states may also appear) |
| `generation` | Run ID, progress message, files, errors, source-link changes, and any `importError` |
| `versionId` | Linked Studio version ID, or null before import |
| `reviewStatus` | `unreviewed` or `reviewed`; independent of generation and application stage |
| `links` | Job polling URL, board details, linked Studio editor, and explicit generation retry |
| `revision` | Required for editing existing job details |

`ready` means generated files are retained. If `generation.importError` is
present, automatic Studio import needs reconciliation. It does not mean the
résumé is reviewed. Downloads remain available for unreviewed content.

## Duplicate applications and idempotency

URL matching strips fragments and known tracking parameters (`utm_*`, `gclid`,
`fbclid`, `msclkid`, `dclid`, `mc_cid`, `mc_eid`), sorts query parameters, and
normalizes the host/default port. Requisition identifiers and other query
parameters are preserved.

- One matching posting returns the existing job (`200`) without regeneration.
- Multiple matches return `409` with `duplicates` containing IDs, company, and
  title. Fetch the intended ID explicitly.
- `"allowDuplicate": true` creates a separate application.
- An optional `Idempotency-Key` (1–200 characters) durably associates the original
  request with its job. Repeating the same key and payload returns that job
  (`200`), including when duplicates exist. Changing the payload under that key
  returns `409`. Retry with the same complete payload; do not alter flags/notes.

```sh
curl -s http://127.0.0.1:8765/api/jobs \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: separate-application-123' \
  -d '{"job":{"url":"https://example.com/careers/job-123"},"allowDuplicate":true}'
```

## Explicit generation retry and stage updates

Creation retries do not restart failed generation. Retry explicitly (`202`):

```sh
curl -s http://127.0.0.1:8765/api/jobs/JOB_ID/generate \
  -H 'Content-Type: application/json' -d '{}'
```

This continues saved progress when possible. To capture a fresh master and
create a new run, send `{"regenerate":true}`. For blocked postings, send
`{"sourceText":"Full posting text including responsibilities and qualifications..."}`.
Pasted text must be at least 150 characters. Older files remain available.

```sh
curl -s http://127.0.0.1:8765/api/jobs/JOB_ID \
  -H 'Content-Type: application/json' \
  -d '{"job":{"stage":"rejected"},"revision":"CURRENT_JOB_REVISION"}'
```

Rejected means the employer declined the application. Subsequent moves preserve
application dates, stage history, and documents. Stale revisions return `409`.

## Historical import and reconciliation

New runs automatically import into Studio. Historical runs require an explicit
preview; migration does not import them. The latest saved job draft takes
precedence over the generated original.

```sh
curl -s http://127.0.0.1:8765/api/jobs/JOB_ID/preview-import \
  -H 'Content-Type: application/json' -d '{"runId":"RUN_ID"}'
```

Inspect `resume`, `additions`, and `conflicts`. Use the returned `revision` and
`draftRevision` to commit the preview:

```sh
curl -s http://127.0.0.1:8765/api/jobs/JOB_ID/import-studio \
  -H 'Content-Type: application/json' \
  -d '{"runId":"RUN_ID","revision":"STUDIO_REVISION","draftRevision":"DRAFT_REVISION"}'
```

Ambiguous entries need an `entryMap`, such as `{"work/0":"MASTER_ENTRY_ID"}`;
preview `entries` supplies candidate IDs. After explicitly reviewing changed
source content, `"acknowledgeChanges": true` allows reconciliation. Missing
source highlights then become separate unreviewed highlights retaining the
original source references. Unsupported identity/factual fields still need
correction in Master before import. Concurrent saves return `409`; preview
again. Reimporting an already imported run returns its existing `versionId`.

Studio owns the linked résumé. Cover-letter editing remains in job drafts.
Preview and ZIP endpoints use the saved Studio projection and indentation;
concurrent changes reject stale saves/downloads without clearing browser edits.
