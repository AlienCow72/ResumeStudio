# JSON Job Description schema reference

Source: https://github.com/jsonresume/jsonresume.org/tree/master/packages/schema

The JSON Resume repository provides `job-schema.json` with `sample.job.json`, but describes this job-description schema as a draft that is not finalized. The current checked-in schema is draft-07, permits extra properties, and has no required fields. Inspect the specific revision before exact validation because this is not a stable contract.

## Current top-level fields

`title`, `company`, `type`, `date`, `description`, `location`, `remote`, `salary`, `experience`, `responsibilities`, `qualifications`, `skills`, and `meta`.

- `date` uses the same constrained date format as the resume schema: `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`.
- `location` contains `address`, `postalCode`, `city`, `countryCode` (ISO 3166-1 alpha-2), and `region`.
- `remote` must be one of `Full`, `Hybrid`, or `None`.
- `responsibilities` and `qualifications` are arrays of strings.
- Each `skills` item has `name`, `level`, and `keywords` (an array of strings).
- `meta` contains `canonical` (URI), `version`, and `lastModified` (ISO 8601 date-time by description).

## Operational guidance

- Retrieve the same revision of `job-schema.json` and `sample.job.json` together when grounding a new job record.
- Treat JSON Schema requirements, formats, enums, and array item definitions in that file as authoritative for the target revision.
- Keep source capture distinct from interpretation: record textual qualifications and conditions accurately; add derived tags or normalizations only if the target schema explicitly supports them or the user requests them.
- If schema retrieval or validation is unavailable, produce syntactically valid JSON and clearly avoid representing it as schema-validated.

Repository README context: `schema.json` and `sample.resume.json` represent the stable resume schema, while the job schema is a draft. Source URL: https://github.com/jsonresume/jsonresume.org/tree/master/packages/schema
