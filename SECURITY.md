# Security

## What this tool does

cc-stats runs entirely on your machine. It reads transcript files, writes one HTML file, and makes
no network request — neither the CLI nor the generated page, which inlines all of its CSS, charts
and favicon and contains no JavaScript at all.

Transcripts are only ever read. The scan does not follow symlinks and does not descend past one
directory level under the projects directory.

## What ends up in the output

**No message content.** Nothing you or Claude wrote, and no tool input or output, is written to the
dashboard. It holds counts, dates, tool names and prettified project labels.

It still describes your working patterns: which hours and weekdays you work, how many projects you
have, how long sessions run, how much you use each tool. **Treat a generated dashboard as personal**
and review it before sharing.

## Redaction is best effort

Redaction is on by default. Project directories are decoded to their meaningful tail with the home
prefix stripped, and every label is then run through a redactor covering account names, email
addresses, API keys and tokens, and home paths.

It is **pattern-based and not a guarantee**. A value in a shape the patterns do not cover can pass
through. Always review a dashboard before sharing it.

Running with `--no-redact` shows raw project directory names, which include your account name.

## Reporting a problem

Please report security issues — in particular any way transcript content could reach the generated
page, or a shape of personal data that redaction misses — through GitHub issues on this repository.
Describe the shape of the input rather than pasting the real value.
