# Studio architecture and assistant API implementation plan

Date: 2026-10-14

Status: Implemented. The existing model, stores, renderer, job endpoints, and UI were extended; regression tests use stubbed generation.

## Objective

Make Studio versions the shared source for job résumés, add reusable highlight wording and master indentation, add a Rejected application stage, and formalize the local API for assistants.

## 1. Extend the résumé data model

Keep `data/resume.json` compatible with JSON Resume. Extend the metadata in `data/versions.json` with:

- Stable highlight identities and alternative wording IDs.
- Master indentation defaults, levels 0–3.
- Version selections for wording, content, and ordering.
- Version-specific headline, objective, and entry summary/description overrides.
- Review status and provenance linking generated content to its job, run, and source highlights.

A version selects at most one wording per highlight. Combined or unmatched generated points become separate unreviewed highlights with source references.

Put projection and selection rules in the résumé model layer so the UI, generation, previews, and exports share the same behavior.

## 2. Migrate existing data without changing existing versions

- Back up the current master and settings before migration.
- Preserve existing stable IDs, content selections, ordering, objectives, and effective indentation.
- Seed master indentation from the **Joblinks** version's pattern.
- Preserve each existing version's indentation through explicit overrides where necessary.
- Treat existing highlights as their initial wording.
- Make migration repeatable without creating duplicate metadata.

Verify that each existing version projects to the same content and indentation before and after migration.

## 3. Add master and version editing controls

In Master:

- Group each highlight's alternative wordings.
- Add indentation controls and review/provenance labels.
- Show affected versions before editing shared wording.

In versions:

- Select one wording or exclude the highlight.
- Edit wording by creating or reusing an alternative, selected only in that version.
- Support tailored prose and ordering.
- Allow indentation overrides and **Reset to master**.
- Provide **Mark reviewed**.

New highlights, whether added manually or through generation, start unselected in existing versions. Alternative wording leaves existing wording selections unchanged.

Editing shared wording directly in Master updates versions selecting it and invalidates review for those versions. Editing approved wording makes that wording require review again. Marking a generated version reviewed also approves its selected unreviewed highlight wordings. Downloads remain available for unreviewed content, with a notice.

Retain indentation normalization when excluded bullets would otherwise leave orphaned children. Normalize the rendered result without changing stored master defaults or version overrides, and apply the behavior consistently to all sections containing highlights.

## 4. Import generated résumés automatically

At generation start, capture master content, stable IDs, and relevant metadata.

Extend generation output to identify the source highlights behind each generated point. Validate those references before import. Automatically group clear rewrites; retain combined or unmatched wording as separate unreviewed highlights with source references rather than guessing relationships from similar text alone.

On successful generation:

- Reuse matching wording within the same highlight.
- Add new alternatives or separate unreviewed highlights without replacing original master wording.
- Select generated additions in the version that needs them.
- Create an unreviewed Studio version preserving generated selections, prose, and ordering.
- Link it to the job and generation run.

Import must be idempotent per run. A retry completes missing work without duplicating versions or wording.

If source content changes or disappears during generation, preserve the generated files and pause affected import work for reconciliation. Preserve unsaved browser edits and offer reconciliation instead of silently refreshing them away.

## 5. Connect job review and downloads to Studio

Replace the independent editable job résumé with its linked Studio version.

- The job's résumé action opens that version.
- Preview and application ZIP generation use the shared projection and indentation.
- Cover letters remain editable within the job.
- Downloads use a consistent snapshot of the current saved content while rendering.
- Do **not** add an archive of exported revisions. The linked Studio version remains editable.

Add an explicit historical import action with a preview. Prefer the latest saved job draft, otherwise the generated original. Flag ambiguous relationships for review and prevent repeated imports of the same run. Do not automatically import every historical run during migration.

## 6. Add Rejected and complete the assistant API

### Rejected application stage

Add **Rejected** to backend validation, the board as a fourth visible column, and all stage selectors. Rejected means the employer declined the application. Preserve stage history, application dates, documents, and the ability to move a job back to another stage.

### Local API

Keep API access local to `127.0.0.1`. Reuse and extend the existing job endpoints rather than creating a separate assistant workflow.

| Endpoint | Behavior |
|---|---|
| `POST /api/jobs` | Save a job and automatically queue extraction and document generation |
| `GET /api/jobs` | List jobs with their existing stable IDs and statuses |
| `GET /api/jobs/{id}` | Return one job, or `404` |
| `GET /api/jobs?url={encoded-url}` | Return all matching jobs as `{"jobs": [...]}`, or an empty list |

Preserve the existing creation payload:

```json
{
  "job": {
    "url": "https://example.com/careers/job-123",
    "notes": "Added by an assistant"
  }
}
```

Company, title, and pasted posting text remain optional. Creation returns immediately; generation runs in the background. The existing explicit `generate: false` option remains available.

Responses expose application stage, generation status, linked version ID, review status, and progress/navigation links. Distinguish application stage (`applying`, `waiting`, `interview`, `rejected`) from generation status and version review status.

URL matching ignores known tracking parameters while preserving requisition identifiers. Separate applications for the same posting remain supported.

Add optional `Idempotency-Key` support:

- Repeating the same request returns its original job.
- Reusing a key with different input returns a conflict.
- One matching posting returns the existing job without regenerating.
- Multiple matches return a conflict with their IDs so the caller can choose.
- An explicit duplicate option creates a separate application.
- Retrying failed generation remains an explicit action.

Document creation, lookup, polling, duplicate handling, and explicit generation retry with assistant-friendly examples.

## 7. Verify and deliver

Add targeted regression coverage for:

- Migration preserving existing projections and Joblinks indentation.
- Alternative selection, deduplication, and review invalidation.
- New highlights staying excluded from existing versions.
- Inheritance, overrides, ordering, and orphan normalization.
- Automatic import retries, partial failures, and concurrent edits.
- Shared Studio/job preview and download content.
- Rejected transitions and history.
- API creation, lookups, URL normalization, duplicates, and idempotency.

Use stubbed generation in automated tests. Run the existing suite and inspect the changed UI and rendered résumé output, including mobile layouts.

## Implementation order

Follow the phases above: data model and migration first, editing and generation integration next, then job integration and API completion. This makes generated content importable only after Studio can represent it correctly.

Implementation is complete. See `docs/assistant-api.md` for the local API workflow.
