# JSON Resume schema reference

Source: https://github.com/jsonresume/jsonresume.org/tree/master/packages/schema

The maintained schema is `schema.json`; its example is `sample.resume.json`. The source is a draft-07 JSON Schema and allows extra properties, but use its documented fields for portability.

## Top-level fields

`$schema`, `basics`, `work`, `volunteer`, `education`, `awards`, `certificates`, `publications`, `skills`, `languages`, `interests`, `references`, `projects`, and `meta`.

No top-level fields are required. All date-like fields using `iso8601` accept only `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`; do not use `Present` or an empty string for an ongoing role—omit `endDate`.

## Key structures

- `basics`: `name`, `label`, `image`, `email`, `phone`, `url`, `summary`, `location`, `profiles`.
  - `location`: `address`, `postalCode`, `city`, `countryCode` (ISO 3166-1 alpha-2), `region`.
  - Each profile: `network`, `username`, `url`.
- `work`: `name`, `location`, `description`, `position`, `url`, `startDate`, `endDate`, `summary`, `highlights`.
- `volunteer`: `organization`, `position`, `url`, `startDate`, `endDate`, `summary`, `highlights`.
- `education`: `institution`, `url`, `area`, `studyType`, `startDate`, `endDate`, `score`, `courses`.
- `awards`: `title`, `date`, `awarder`, `summary`.
- `certificates`: `name`, `date`, `url`, `issuer`.
- `publications`: `name`, `publisher`, `releaseDate`, `url`, `summary`.
- `skills`: `name`, `level`, `keywords`.
- `languages`: `language`, `fluency`.
- `interests`: `name`, `keywords`.
- `references`: `name`, `reference`.
- `projects`: `name`, `description`, `highlights`, `keywords`, `startDate`, `endDate`, `url`, `roles`, `entity`, `type`.
- `meta`: `canonical`, `version`, `lastModified`.

`email` must be email-formatted. Fields declared as URLs must be absolute URI-formatted strings. `meta.lastModified` is described as ISO 8601 date-time. The schema permits additional properties, but themes and resume tooling may not display them.
