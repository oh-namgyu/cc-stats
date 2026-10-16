# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-02

Initial public release.

### Added

- `python -m cc_stats` scans every Claude Code transcript under
  `~/.claude/projects` (or `CLAUDE_CONFIG_DIR`) and writes one self-contained
  HTML dashboard, `stats.html` by default. stdout is exactly the written path.
- Dashboard: daily tokens (in, out, cache read, cache created), tool
  distribution, tool error rate, sessions per project, a weekday-by-hour
  heatmap, session length and turns. The metric rules (deduplication by
  message, tool-use and event ids, sidechain handling) are documented in the
  README.
- Options: `-o`, `--days N`, `--project`, `--utc`, `--no-redact`.
- Day and hour buckets follow the local clock, or UTC with `--utc`.
- No message content, tool input or tool output in the page: only counts,
  dates, tool names and project labels. Labels are redacted by default.
- Charts are inline SVG; the page has no `<script>` element and makes no
  network requests.
- Unparseable lines, a truncated final line and unreadable files are skipped
  and reported instead of aborting the scan.
- Exit codes `0` (success), `1` (nothing to render) and `2` (usage or
  filesystem error).
- Standard library only, Python 3.9+. The transcript parser and redactor are
  vendored from cc-replay at commit `04618de`.
