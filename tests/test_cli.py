"""CLI tests against a synthetic CLAUDE_CONFIG_DIR; no real transcript is read."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from cc_stats import cli
from cc_stats.scanner import ENV_CONFIG_DIR


def canary() -> str:
    """Fictional account name, assembled rather than written as a path."""
    return "al" + "ice"


def session(stamp="2026-01-01T10:00:00Z", cwd=None, out_tokens=5):
    cwd = cwd or "/Users/%s/code/dev-tools" % canary()
    return [
        {"type": "user", "uuid": "u1", "timestamp": stamp, "cwd": cwd,
         "message": {"role": "user", "content": "hello"}},
        {"type": "assistant", "uuid": "a1", "timestamp": stamp, "cwd": cwd,
         "message": {"role": "assistant", "id": "m1",
                     "content": [{"type": "text", "text": "hi"}],
                     "usage": {"input_tokens": 1, "output_tokens": out_tokens}}},
    ]


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cc-stats-cli-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.projects = self.tmp / "config" / "projects"
        self.projects.mkdir(parents=True)
        self.previous = os.environ.get(ENV_CONFIG_DIR)
        os.environ[ENV_CONFIG_DIR] = str(self.tmp / "config")
        self.addCleanup(self.restore)
        self.out, self.err = io.StringIO(), io.StringIO()

    def restore(self):
        if self.previous is None:
            os.environ.pop(ENV_CONFIG_DIR, None)
        else:
            os.environ[ENV_CONFIG_DIR] = self.previous

    def seed(self, project, name, events=None):
        folder = self.projects / project
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        rows = session() if events is None else events
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    def run_cli(self, argv):
        return cli.main(argv, out=self.out, err=self.err)

    def target(self, name="stats.html"):
        return self.tmp / name

    def test_writes_the_dashboard_and_prints_only_the_path(self):
        self.seed("-Users-%s-code-dev-tools" % canary(), "s1.jsonl")
        output = self.target()
        self.assertEqual(self.run_cli(["-o", str(output)]), 0)
        self.assertTrue(output.is_file())
        # stdout must stay usable verbatim, so the path is never redacted.
        self.assertEqual(self.out.getvalue().strip(), str(output.resolve()))
        self.assertNotIn("REDACTED", self.out.getvalue())
        self.assertIn("scanned 1 transcripts", self.err.getvalue())
        self.assertIn("1 sessions", self.err.getvalue())

    def test_stdout_stays_one_line_while_warnings_go_to_stderr(self):
        self.seed("-Users-%s-code-dev-tools" % canary(), "s1.jsonl")
        broken = self.seed("-Users-%s-code-dev-tools" % canary(), "s2.jsonl")
        broken.chmod(0o000)
        if os.access(str(broken), os.R_OK):
            self.skipTest("file permissions are not enforced for this user")
        self.assertEqual(self.run_cli(["-o", str(self.target())]), 0)
        self.assertEqual(len(self.out.getvalue().strip().splitlines()), 1)
        self.assertIn("warning:", self.err.getvalue())
        self.assertIn("1 unreadable", self.err.getvalue())

    def test_empty_projects_directory_exits_1(self):
        self.assertEqual(self.run_cli(["-o", str(self.target())]), 1)
        self.assertIn("no transcripts found", self.err.getvalue())
        self.assertEqual(self.out.getvalue(), "")

    def test_unknown_project_exits_1_naming_the_project(self):
        self.seed("-Users-%s-code-dev-tools" % canary(), "s1.jsonl")
        code = self.run_cli(["--project=-nope", "-o", str(self.target())])
        self.assertEqual(code, 1)
        self.assertIn("-nope", self.err.getvalue())

    def test_project_filter_selects_one_directory(self):
        # Project names start with a dash, so the equals form is required.
        keep = "-Users-%s-code-dev-tools" % canary()
        self.seed(keep, "s1.jsonl")
        self.seed("-Users-%s-code-other" % canary(), "s2.jsonl",
                  events=session(out_tokens=999))
        self.assertEqual(self.run_cli(["--project=" + keep, "-o", str(self.target())]), 0)
        page = self.target().read_text(encoding="utf-8")
        self.assertIn("<b>5</b><span>tokens out</span>", page)
        self.assertNotIn("999", page)

    def test_days_window_can_leave_nothing_to_render(self):
        self.seed("-Users-%s-code-dev-tools" % canary(), "s1.jsonl",
                  events=session(stamp="2020-01-01T10:00:00Z"))
        self.assertEqual(self.run_cli(["--days", "1", "-o", str(self.target())]), 1)
        self.assertIn("no sessions in the selected window", self.err.getvalue())
        self.assertFalse(self.target().is_file())

    def test_bad_days_value_exits_2(self):
        self.assertEqual(self.run_cli(["--days", "0"]), 2)
        self.assertIn("--days must be 1 or more", self.err.getvalue())

    def test_bad_argument_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                self.run_cli(["--nonsense"])
        self.assertEqual(caught.exception.code, 2)

    def test_unwritable_output_exits_2(self):
        self.seed("-Users-%s-code-dev-tools" % canary(), "s1.jsonl")
        blocked = self.tmp / "locked"
        blocked.mkdir()
        blocked.chmod(0o500)
        if os.access(str(blocked), os.W_OK):
            self.skipTest("directory permissions are not enforced for this user")
        self.addCleanup(blocked.chmod, 0o700)
        self.assertEqual(self.run_cli(["-o", str(blocked / "out.html")]), 2)
        self.assertIn("could not write", self.err.getvalue())

    def test_atomic_write_keeps_the_old_file_when_replace_fails(self):
        self.seed("-Users-%s-code-dev-tools" % canary(), "s1.jsonl")
        output = self.target()
        output.write_text("PREVIOUS", encoding="utf-8")
        original = os.replace

        def explode(source, destination):
            raise OSError("injected failure")

        os.replace = explode
        try:
            self.assertEqual(self.run_cli(["-o", str(output)]), 2)
        finally:
            os.replace = original
        self.assertEqual(output.read_text(encoding="utf-8"), "PREVIOUS")
        leftovers = [item.name for item in self.tmp.iterdir()
                     if item.name.startswith(".cc-stats-")]
        self.assertEqual(leftovers, [])

    def test_redaction_is_on_by_default_and_can_be_disabled(self):
        raw = "-Users-%s-code-dev-tools" % canary()
        self.seed(raw, "s1.jsonl")
        masked = self.target("masked.html")
        self.assertEqual(self.run_cli(["-o", str(masked)]), 0)
        page = masked.read_text(encoding="utf-8")
        self.assertNotIn(canary(), page)
        self.assertIn("code-dev-tools", page)

        plain = self.target("plain.html")
        self.assertEqual(self.run_cli(["-o", str(plain), "--no-redact"]), 0)
        self.assertIn(raw, plain.read_text(encoding="utf-8"))

    def test_utc_flag_is_accepted(self):
        self.seed("-Users-%s-code-dev-tools" % canary(), "s1.jsonl")
        self.assertEqual(self.run_cli(["--utc", "-o", str(self.target())]), 0)
        self.assertIn("2026-01-01", self.target().read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
