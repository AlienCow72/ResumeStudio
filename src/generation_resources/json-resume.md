---
name: json-resume
description: Create, update, or validate a resume.json that follows the JSON Resume schema. Use for structured resume data, not for rendered resume layout.
---

# JSON Resume

Create portable, factual resume data in the current JSON Resume schema.

## Workflow

- First locate the source material and preserve facts, dates, employers, titles, and links. Never invent metrics, credentials, dates, or contact data.
- Make the smallest schema-appropriate representation. Omit unavailable or non-useful optional fields rather than using placeholder strings, empty arrays, or null.
- Keep experience in `work`; use `volunteer`, `education`, `awards`, `certificates`, `publications`, and `projects` only for their corresponding content.
- Put concise achievement bullets in `highlights`; use `summary` for a short role or project overview. Preserve the source's meaning rather than mechanically copying prose.
- Use strings for dates in `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` format. Use valid absolute URLs and email addresses when those fields are present.
- Return valid, human-readable JSON with two-space indentation. When a local JSON Schema validator is available, validate the result before delivery; otherwise check JSON syntax and field types carefully.

Read [the schema reference](references/schema.md) before creating or substantially restructuring a resume. It records the source schema's top-level fields, nested structures, validation constraints, and source URLs.
