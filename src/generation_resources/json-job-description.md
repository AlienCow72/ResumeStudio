---
name: json-job-description
description: Create, update, or validate structured job-description JSON using JSON Resume's draft job schema. Use for job posting data, not resume tailoring or prose-only job descriptions.
---

# JSON Job Description

Turn a job posting into structured data that is faithful to the source and compatible with the JSON Resume draft job-description schema.

## Workflow

- Treat the original job posting as the source of truth. Do not add benefits, compensation, work-location terms, qualifications, or application instructions that it does not state.
- Preserve requirements and responsibilities as separate items where the source distinguishes them. Retain qualifiers such as years of experience, degree level, location, employment type, and eligibility.
- Omit unknown optional fields instead of guessing. Preserve wording for legally or operationally material conditions; otherwise normalize only enough to make the JSON clear and consistent.
- Use arrays for multiple qualifications, responsibilities, and skills. For `remote`, use exactly `Full`, `Hybrid`, or `None`; keep output valid, human-readable JSON with two-space indentation.
- The job schema is explicitly a draft rather than a finalized standard. If downstream compatibility matters, identify the schema revision and validate against the checked-in `job-schema.json` before delivery.

Read [the schema reference](references/schema.md) before creating or restructuring a job JSON. It gives the current source location and handling guidance for the unstable draft.
