"""Aggregator golden tests: every expected number is hand-computed from the
fixture directly above it. Timezones are always injected (``utc`` or explicit
``tz``) so no assertion depends on the machine's local zone.
"""

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cc_stats.aggregator import Options, aggregate, minute_bucket
from cc_stats.scanner import TranscriptRef

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - zoneinfo is stdlib from 3.9
    ZoneInfo = None

KST = timezone(timedelta(hours=9))


def usage_block(inp=0, out=0, read=0, write=0):
    return {"input_tokens": inp, "output_tokens": out,
            "cache_read_input_tokens": read, "cache_creation_input_tokens": write}


def assistant(uuid, stamp, mid="m1", usage=None, blocks=None, **extra):
    message = {"role": "assistant",
               "content": [{"type": "text", "text": "ok"}] if blocks is None else blocks}
    if mid is not None:
        message["id"] = mid
    if usage is not None:
        message["usage"] = usage
    event = {"type": "assistant", "uuid": uuid, "timestamp": stamp, "message": message}
    event.update(extra)
    return event


def user(uuid, stamp, content="hi", **extra):
    event = {"type": "user", "uuid": uuid, "timestamp": stamp,
             "message": {"role": "user", "content": content}}
    event.update(extra)
    return event


def tool_use(identifier, name="Bash"):
    return {"type": "tool_use", "id": identifier, "name": name, "input": {"command": "ls"}}


def tool_result(identifier, failed=False):
    return {"type": "tool_result", "tool_use_id": identifier, "is_error": failed}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cc-stats-agg-"))
        self.addCleanup(shutil.rmtree, str(self.tmp), True)
        self.made = 0

    def write(self, events, project="-w-demo", tail=None):
        folder = self.tmp / project
        folder.mkdir(parents=True, exist_ok=True)
        self.made += 1
        path = folder / ("s%d.jsonl" % self.made)
        body = "".join(json.dumps(event) + "\n" for event in events)
        path.write_text(body + (tail or ""), encoding="utf-8")
        return TranscriptRef(path=path, project=project, session_id=path.stem)

    def fold(self, *refs, **kwargs):
        return aggregate(list(refs), kwargs.pop("options", None) or Options(utc=True))


class TokenTestCase(Base):
    def test_usage_repeated_identically_counts_once(self):
        block = usage_block(10, 5, 100, 7)
        ref = self.write([assistant("a1", "2026-01-01T10:00:00Z", usage=block),
                          assistant("a2", "2026-01-01T10:00:01Z", usage=block),
                          assistant("a3", "2026-01-01T10:00:02Z", usage=block)])
        metrics = self.fold(ref)
        self.assertEqual(metrics.tokens, {"input": 10, "output": 5,
                                          "cache_read": 100, "cache_creation": 7})
        self.assertEqual(metrics.assistant_messages, 1)
        self.assertEqual(metrics.daily_tokens["2026-01-01"]["cache_read"], 100)
        # One streamed message is one turn; the raw event count is kept apart.
        self.assertEqual(metrics.turns, 1)
        self.assertEqual(metrics.turn_events, 3)
        self.assertEqual(metrics.daily_turns, {"2026-01-01": 1})

    def test_last_usage_snapshot_wins_when_snapshots_grow(self):
        ref = self.write([assistant("a1", "2026-01-01T10:00:00Z", usage=usage_block(10, 5)),
                          assistant("a2", "2026-01-01T10:00:01Z", usage=usage_block(10, 9))])
        metrics = self.fold(ref)
        self.assertEqual(metrics.tokens["output"], 9)
        self.assertEqual(metrics.tokens["input"], 10)

    def test_assistant_without_usage_contributes_no_tokens(self):
        metrics = self.fold(self.write([assistant("a1", "2026-01-01T10:00:00Z")]))
        self.assertEqual((metrics.tokens["input"], metrics.assistant_messages), (0, 1))
        self.assertEqual(metrics.daily_tokens, {})

    def test_missing_message_id_is_counted_and_still_aggregated(self):
        metrics = self.fold(self.write([assistant("a1", "2026-01-01T10:00:00Z",
                                        mid=None, usage=usage_block(3, 4))]))
        self.assertEqual(metrics.warnings["idless"], 1)
        self.assertEqual(metrics.tokens["output"], 4)
        self.assertEqual(metrics.assistant_messages, 1)

    def test_late_tool_use_on_an_already_seen_message_id(self):
        ref = self.write([
            assistant("a1", "2026-01-01T10:00:00Z", usage=usage_block(10, 5)),
            assistant("a2", "2026-01-01T10:00:01Z", usage=usage_block(10, 5),
                      blocks=[tool_use("t1", "Read")])])
        metrics = self.fold(ref)
        self.assertEqual(metrics.tokens["output"], 5)
        self.assertEqual(metrics.tools, {"Read": 1})
        self.assertEqual(metrics.tool_states["pending"], 1)


class ToolTestCase(Base):
    def test_duplicate_tool_use_id_counts_once(self):
        metrics = self.fold(self.write([assistant("a1", "2026-01-01T10:00:00Z",
                                        blocks=[tool_use("t1"), tool_use("t1")])]))
        self.assertEqual(metrics.tools, {"Bash": 1})
        self.assertEqual(metrics.warnings["duplicate_tool_use"], 1)

    def test_unnamed_tool_is_labelled_unknown(self):
        ref = self.write([assistant("a1", "2026-01-01T10:00:00Z",
                                    blocks=[{"type": "tool_use", "id": "t1", "input": {}}])])
        self.assertEqual(self.fold(ref).tools, {"(unknown)": 1})

    def test_states_and_error_rate(self):
        # t1 -> ok, t2 -> error, t3 -> no result, zz -> result with no call.
        ref = self.write([
            assistant("a1", "2026-01-01T10:00:00Z",
                      blocks=[tool_use("t1"), tool_use("t2"), tool_use("t3")]),
            user("u1", "2026-01-01T10:00:01Z", content=[tool_result("t1")]),
            user("u2", "2026-01-01T10:00:02Z", content=[tool_result("t2", failed=True)]),
            user("u3", "2026-01-01T10:00:03Z", content=[tool_result("zz")])])
        metrics = self.fold(ref)
        self.assertEqual(metrics.tool_states,
                         {"ok": 1, "error": 1, "pending": 1, "orphan": 1})
        self.assertAlmostEqual(metrics.error_rate, 0.5)
        self.assertEqual(metrics.daily_errors["2026-01-01"], {"ok": 1, "error": 1})

    def test_duplicate_result_keeps_the_first_and_warns(self):
        ref = self.write([
            assistant("a1", "2026-01-01T10:00:00Z", blocks=[tool_use("t1")]),
            user("u1", "2026-01-01T10:00:01Z", content=[tool_result("t1")]),
            user("u2", "2026-01-01T10:00:02Z", content=[tool_result("t1", failed=True)])])
        metrics = self.fold(ref)
        self.assertEqual(metrics.tool_states["ok"], 1)
        self.assertEqual(metrics.tool_states["error"], 0)
        self.assertEqual(metrics.warnings["duplicate_tool_result"], 1)
        self.assertEqual(metrics.error_rate, 0.0)

    def test_pending_and_orphan_stay_out_of_the_error_denominator(self):
        ref = self.write([
            assistant("a1", "2026-01-01T10:00:00Z", blocks=[tool_use("t1")]),
            user("u1", "2026-01-01T10:00:01Z", content=[tool_result("zz")])])
        metrics = self.fold(ref)
        self.assertEqual(metrics.error_rate, 0.0)
        self.assertEqual(metrics.daily_errors, {})


class TurnTestCase(Base):
    def test_sidechain_feeds_tokens_and_tools_but_not_turns(self):
        ref = self.write([
            user("u1", "2026-01-01T10:00:00Z"),
            assistant("a1", "2026-01-01T10:00:01Z", usage=usage_block(1, 2),
                      blocks=[tool_use("t1")], isSidechain=True)])
        metrics = self.fold(ref)
        self.assertEqual(metrics.tokens["output"], 2)
        self.assertEqual(metrics.tools, {"Bash": 1})
        self.assertEqual(metrics.turns, 1)

    def test_meta_user_and_tool_result_only_events_are_not_turns(self):
        ref = self.write([
            user("u1", "2026-01-01T10:00:00Z", isMeta=True),
            user("u2", "2026-01-01T10:00:01Z", content=[tool_result("t1")]),
            user("u3", "2026-01-01T10:00:02Z", content="a real question")])
        metrics = self.fold(ref)
        self.assertEqual(metrics.turns, 1)
        self.assertEqual(metrics.daily_turns, {"2026-01-01": 1})


class TimeTestCase(Base):
    def test_day_boundary_uses_the_chosen_timezone(self):
        # KST is UTC+9: 14:30Z is 23:30 on the 1st, 15:30Z is 00:30 on the 2nd.
        ref = self.write([
            assistant("a1", "2026-01-01T14:30:00Z", mid="m1", usage=usage_block(0, 1)),
            assistant("a2", "2026-01-01T15:30:00Z", mid="m2", usage=usage_block(0, 2))])
        metrics = self.fold(ref, options=Options(tz=KST))
        self.assertEqual(metrics.daily_tokens["2026-01-01"]["output"], 1)
        self.assertEqual(metrics.daily_tokens["2026-01-02"]["output"], 2)

    def test_dst_transition_shifts_the_hour_bucket(self):
        try:
            zone = ZoneInfo("America/New_York")
        except Exception:  # missing module or missing time zone database
            self.skipTest("time zone database unavailable")
        # 2026-03-08 is a Sunday; the clock jumps 02:00 EST -> 03:00 EDT at 07:00Z.
        ref = self.write([assistant("a1", "2026-03-08T06:30:00Z", mid="m1"),
                          assistant("a2", "2026-03-08T07:30:00Z", mid="m2")])
        metrics = self.fold(ref, options=Options(tz=zone))
        self.assertEqual(metrics.heatmap[6][1], 1)
        self.assertEqual(metrics.heatmap[6][3], 1)
        self.assertEqual(metrics.heatmap[6][2], 0)

    def test_naive_timestamp_is_treated_as_utc(self):
        ref = self.write([assistant("a1", "2026-01-01T10:00:00", mid="m1",
                                    usage=usage_block(0, 3))])
        metrics = self.fold(ref)
        self.assertEqual(metrics.daily_tokens["2026-01-01"]["output"], 3)
        self.assertEqual(metrics.heatmap[3][10], 1)  # 2026-01-01 is a Thursday

    def test_heatmap_counts_each_event_uuid_once(self):
        event = assistant("dup", "2026-01-01T10:00:00Z", mid="m1")
        metrics = self.fold(self.write([event, dict(event)]))
        self.assertEqual(metrics.heatmap[3][10], 1)

    def test_session_length_buckets(self):
        single = self.write([assistant("a1", "2026-01-01T10:00:00Z", mid="m1")])
        spanned = self.write([assistant("b1", "2026-01-01T10:00:00Z", mid="m2"),
                              assistant("b2", "2026-01-01T10:20:00Z", mid="m3")])
        metrics = self.fold(single, spanned)
        self.assertEqual(metrics.session_minutes, {"0": 1, "16-30": 1})

    def test_minute_bucket_edges(self):
        labels = [minute_bucket(value) for value in (0, 5, 5.5, 120, 120.1)]
        self.assertEqual(labels, ["0", "1-5", "6-15", "61-120", "120+"])

    def test_days_window_filters_events_but_keeps_the_full_span(self):
        now = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        stale = self.write([assistant("s1", "2026-01-05T10:00:00Z", mid="m1",
                                      usage=usage_block(0, 100))])
        mixed = self.write([
            assistant("x1", "2026-01-05T10:00:00Z", mid="m2", usage=usage_block(0, 50)),
            assistant("x2", "2026-01-09T10:00:00Z", mid="m3", usage=usage_block(0, 7))])
        metrics = self.fold(stale, mixed, options=Options(utc=True, days=2, now=now))
        # Window is 2026-01-09..2026-01-10, so only the 01-09 event feeds tokens.
        self.assertEqual(metrics.sessions, 1)
        self.assertEqual(metrics.tokens["output"], 7)
        self.assertEqual(sorted(metrics.daily_tokens), ["2026-01-09"])
        # The surviving session still reports its full 4-day span, unclipped.
        self.assertEqual(metrics.session_minutes, {"120+": 1})

    def test_result_for_an_out_of_window_call_is_not_an_orphan(self):
        now = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        ref = self.write([
            assistant("a1", "2026-01-05T10:00:00Z", mid="m1", blocks=[tool_use("t1")]),
            user("u1", "2026-01-09T10:00:00Z", content=[tool_result("t1")])])
        metrics = self.fold(ref, options=Options(utc=True, days=2, now=now))
        self.assertEqual(metrics.tool_states,
                         {"ok": 0, "error": 0, "pending": 0, "orphan": 0})
        self.assertEqual(metrics.sessions, 1)


class ProjectAndFileTestCase(Base):
    def test_per_project_sessions_and_token_sums(self):
        alpha = self.write([assistant("a1", "2026-01-01T10:00:00Z", mid="m1",
                                      usage=usage_block(5, 7))], project="-w-alpha")
        beta1 = self.write([assistant("b1", "2026-01-01T10:00:00Z", mid="m2",
                                      usage=usage_block(1, 2))], project="-w-beta")
        beta2 = self.write([assistant("b2", "2026-01-01T10:00:00Z", mid="m3",
                                      usage=usage_block(3, 4))], project="-w-beta")
        metrics = self.fold(alpha, beta1, beta2)
        self.assertEqual(metrics.sessions, 3)
        self.assertEqual(metrics.projects["-w-alpha"], {
            "input": 5, "output": 7, "cache_read": 0, "cache_creation": 0, "sessions": 1})
        self.assertEqual(metrics.projects["-w-beta"]["sessions"], 2)
        self.assertEqual(metrics.projects["-w-beta"]["output"], 6)

    def test_malformed_and_truncated_lines_are_counted_not_fatal(self):
        ref = self.write([assistant("a1", "2026-01-01T10:00:00Z", mid="m1",
                                    usage=usage_block(0, 1))],
                         tail="{not json at all\n" + '{"type": "assis')
        metrics = self.fold(ref)
        self.assertEqual(metrics.warnings["malformed_lines"], 2)
        self.assertEqual(metrics.tokens["output"], 1)
        self.assertEqual(metrics.scan.included, 1)

    def test_empty_transcript_contributes_nothing(self):
        metrics = self.fold(self.write([]))
        self.assertEqual(metrics.sessions, 0)
        self.assertEqual(metrics.session_minutes, {})
        self.assertEqual(metrics.projects, {})
        self.assertEqual(metrics.scan.included, 1)

    def test_event_without_timestamp_is_ignored(self):
        metrics = self.fold(self.write([{"type": "assistant", "uuid": "a1",
                            "message": {"id": "m1", "usage": usage_block(9, 9)}}]))
        self.assertEqual(metrics.sessions, 0)
        self.assertEqual(metrics.tokens["output"], 0)


if __name__ == "__main__":
    unittest.main()
