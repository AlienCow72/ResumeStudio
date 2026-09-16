# Document layouts

Edit `resume.html` and `cover-letter.html` independently. Both embed
`src/resume.css` for shared fonts, colors, and print styling. Scope any
letter-only CSS to `.cover-letter` to keep résumé styling unchanged.

Templates use Python `string.Template` placeholders:

- Both: `$name`, `$contact`, `$styles`.
- Résumé: `$label`, `$aside`, `$main`.
- Cover letter: `$paragraphs`.

Text is escaped before insertion; content placeholders contain rendered HTML.
Use `$$` for a literal dollar sign in a template. The contact formatter omits
profiles for cover letters. The job/company heading is intentionally absent.
