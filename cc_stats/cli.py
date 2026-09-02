"""Command line interface for cc-stats.

stdout carries exactly one line, the output path, so the command composes in a
pipeline. Progress, scan counts and warnings all go to stderr.

Exit codes: 0 success (possibly with skipped files), 1 nothing to render, 2 a
usage or filesystem error.
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import IO, List, Optional

from . import __version__
from .aggregator import Options, aggregate
from .labels import pretty_path
from .renderer import render
from .scanner import ScanStats, find_transcripts, projects_dir

DEFAULT_OUTPUT = "stats.html"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cc-stats",
        description="Build an HTML dashboard from every Claude Code session on "
                    "this machine.")
    parser.add_argument("-o", "--output", type=Path, default=Path(DEFAULT_OUTPUT),
                        help="output HTML file (default: %s)" % DEFAULT_OUTPUT)
    parser.add_argument("--days", type=int, default=None, metavar="N",
                        help="only count events from the last N days, including today")
    # Project directory names begin with a dash, which argparse would read as
    # another flag, so the equals form is the one to document.
    parser.add_argument("--project", default=None, metavar="NAME",
                        help="limit to one project directory name; names start "
                             "with a dash, so write --project=-Users-you-code")
    parser.add_argument("--utc", action="store_true",
                        help="bucket days and hours in UTC instead of local time")
    parser.add_argument("--no-redact", action="store_true",
                        help="show raw project directory names (redaction is on by default)")
    parser.add_argument("--version", action="version", version="cc-stats " + __version__)
    return parser


def write_atomic(target: Path, text: str) -> None:
    """Write through a temp file in the same directory, then rename over.

    The rename is atomic, so an interrupted or failed run can never leave a
    half-written dashboard behind: either the old file survives or the new one
    replaces it whole.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(target.parent), prefix=".cc-stats-",
        suffix=".tmp", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(target))
    except BaseException:  # includes KeyboardInterrupt, so Ctrl-C cleans up too
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _report(stats: ScanStats, err: IO[str]) -> None:
    err.write("scanned %d transcripts: %d read, %d skipped\n"
              % (stats.found, stats.included, stats.skipped))
    if stats.skipped:
        details = ", ".join("%s %s" % (count, reason)
                            for reason, count in sorted(stats.reasons.items()))
        err.write("warning: %d transcripts could not be read (%s)\n"
                  % (stats.skipped, details))


def main(argv: Optional[List[str]] = None, out: Optional[IO[str]] = None,
         err: Optional[IO[str]] = None) -> int:
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    args = build_parser().parse_args(argv)
    redact = not args.no_redact

    if args.days is not None and args.days < 1:
        err.write("cc-stats: --days must be 1 or more\n")
        return 2

    stats = ScanStats()
    refs = find_transcripts(project=args.project, stats=stats)
    if not refs:
        where = pretty_path(projects_dir(), redact)
        scope = " for project %s" % args.project if args.project else ""
        err.write("cc-stats: no transcripts found%s under %s\n" % (scope, where))
        return 1

    metrics = aggregate(refs, Options(days=args.days, project=args.project,
                                      utc=args.utc), stats)
    _report(stats, err)
    if not stats.included:
        err.write("cc-stats: every transcript failed to read\n")
        return 1
    if not metrics.sessions:
        err.write("cc-stats: no sessions in the selected window\n")
        return 1

    try:
        write_atomic(args.output, render(metrics, redact=redact))
    except OSError as failure:
        err.write("cc-stats: could not write %s (%s)\n"
                  % (pretty_path(args.output, redact), failure))
        return 2

    # The caller chose this path and needs it back verbatim to open or pipe it;
    # redaction protects the dashboard's contents, not the user's own argument.
    out.write("%s\n" % args.output.resolve())
    err.write("%d sessions, %d turns, %d tool calls across %d projects\n"
              % (metrics.sessions, metrics.turns, sum(metrics.tools.values()),
                 len(metrics.projects)))
    return 0
