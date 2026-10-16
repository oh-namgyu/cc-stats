# Contributing to cc-stats

Thanks for your interest! Bug reports and pull requests are welcome.

## Development setup

There is nothing to build and nothing to install at runtime.

```sh
python -m pip install pytest          # the only tool the suite needs
python -m pytest tests/ -q            # or: python -m unittest discover -s tests -v
python -m cc_stats --help
```

CI runs the suite on Python 3.9 and 3.12; please keep both working.

## Guidelines

- **Zero runtime dependencies.** Standard library only. Do not add a
  third-party import.
- **No message content in the dashboard.** Only counts, dates, tool names and
  redacted project labels may reach the page; see [SECURITY.md](SECURITY.md).
- **No JavaScript, no network.** Charts stay inline SVG and every asset stays
  inlined.
- **Metric rules are documented.** If you change how a number is counted,
  update the Metrics table in the README in the same PR.
- **Synthetic fixtures only.** A test must never read a real transcript.
- **Do not edit `cc_stats/_vendor/`.** Those files are copies from
  [cc-replay](https://github.com/oh-namgyu/cc-replay); fix them upstream and
  re-sync.
- Add a regression test for any bug fix.

## Pull requests

Keep PRs focused on one change, describe what changed and how you verified
it, and make sure the test suite is green before opening one.
