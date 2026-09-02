"""Fold Claude Code transcripts into dashboard metrics.

Aggregation runs over raw transcript events rather than the vendored parser's
normalized step model, because the metric contract deduplicates on identifiers
that only exist on raw events (``message.id``, ``tool_use`` id, event ``uuid``).

State is per transcript and released before the next one, so peak memory stays
at roughly one transcript: message and tool ids never repeat across files.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .scanner import ScanStats, TranscriptRef, read_events

TOKEN_FIELDS = (("input_tokens", "input"), ("output_tokens", "output"),
                ("cache_read_input_tokens", "cache_read"),
                ("cache_creation_input_tokens", "cache_creation"))
TOKEN_KEYS = tuple(name for _raw, name in TOKEN_FIELDS)
MINUTE_BUCKETS = ((0, "0"), (5, "1-5"), (15, "6-15"), (30, "16-30"),
                  (60, "31-60"), (120, "61-120"))
LONGEST_BUCKET = "120+"
UNKNOWN_TOOL = "(unknown)"


@dataclass
class Options:
    # Aggregation switches; tz/now exist so tests stay deterministic.
    days: Optional[int] = None
    project: Optional[str] = None
    utc: bool = False
    tz: Optional[tzinfo] = None
    now: Optional[datetime] = None


@dataclass
class Metrics:
    tokens: Dict[str, int] = field(default_factory=dict)
    daily_tokens: Dict[str, Dict[str, int]] = field(default_factory=dict)
    tools: Dict[str, int] = field(default_factory=dict)
    tool_states: Dict[str, int] = field(default_factory=dict)
    daily_errors: Dict[str, Dict[str, int]] = field(default_factory=dict)
    error_rate: float = 0.0
    projects: Dict[str, Dict[str, int]] = field(default_factory=dict)
    project_paths: Dict[str, str] = field(default_factory=dict)
    heatmap: List[List[int]] = field(default_factory=list)
    session_minutes: Dict[str, int] = field(default_factory=dict)
    turns: int = 0
    user_turns: int = 0
    turn_events: int = 0
    daily_turns: Dict[str, int] = field(default_factory=dict)
    assistant_messages: int = 0
    sessions: int = 0
    warnings: Dict[str, int] = field(default_factory=dict)
    scan: ScanStats = field(default_factory=ScanStats)


@dataclass
class _FileState:
    # Working set for a single transcript, discarded once it is folded.
    cwd: str = ""
    usage: Dict[str, Tuple[str, Dict[str, int]]] = field(default_factory=dict)
    messages: Set[str] = field(default_factory=set)
    turn_messages: Dict[str, str] = field(default_factory=dict)
    user_turns: Dict[str, int] = field(default_factory=dict)
    turn_events: int = 0
    uses: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    results: Dict[str, bool] = field(default_factory=dict)
    out_of_range: Set[str] = field(default_factory=set)
    seen_events: Set[str] = field(default_factory=set)
    first: Optional[datetime] = None
    last: Optional[datetime] = None
    in_range: bool = False


def to_moment(stamp: Any, options: Options) -> Optional[datetime]:
    """ISO timestamp to an aware datetime in the chosen zone; naive means UTC."""
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    if options.utc:
        return moment.astimezone(timezone.utc)
    if options.tz is not None:
        return moment.astimezone(options.tz)
    return moment.astimezone()


def minute_bucket(minutes: float) -> str:
    for edge, label in MINUTE_BUCKETS:
        if minutes <= edge:
            return label
    return LONGEST_BUCKET


def _blocks(content: Any) -> List[Dict[str, Any]]:
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _has_user_text(content: Any) -> bool:
    """True when a user event carries real text, not only tool results."""
    if isinstance(content, str):
        return bool(content.strip())
    return any(block.get("type") == "text" and str(block.get("text") or "").strip()
               for block in _blocks(content))


class Aggregator:
    """Folds transcripts one at a time into a single :class:`Metrics`."""

    def __init__(self, options: Optional[Options] = None) -> None:
        self.options = options or Options()
        self.metrics = Metrics(
            tokens=dict.fromkeys(TOKEN_KEYS, 0),
            heatmap=[[0] * 24 for _ in range(7)],
            tool_states=dict.fromkeys(("ok", "error", "pending", "orphan"), 0),
            warnings=dict.fromkeys(("idless", "duplicate_tool_use",
                                    "duplicate_tool_result", "malformed_lines"), 0))
        self._cutoff = self._start_of_window()

    def _start_of_window(self) -> Optional[date]:
        """First day included by ``--days N`` (N days back, including today)."""
        if not self.options.days or self.options.days <= 0:
            return None
        # to_moment already reads a naive "now" as UTC, like any other stamp.
        now = self.options.now or datetime.now(timezone.utc)
        local = to_moment(now.isoformat(), self.options) or now
        return local.date() - timedelta(days=self.options.days - 1)

    def _in_window(self, moment: datetime) -> bool:
        return self._cutoff is None or moment.date() >= self._cutoff

    def add(self, ref: TranscriptRef, events: Iterable[Any]) -> None:
        """Fold one transcript. Raised OSErrors are the caller's to handle."""
        state = _FileState()
        for event in events:
            if event is None:
                self.metrics.warnings["malformed_lines"] += 1
                continue
            self._event(event, state)
        self._finish_file(ref, state)

    def _event(self, event: Dict[str, Any], state: _FileState) -> None:
        state.cwd = state.cwd or str(event.get("cwd") or "")
        moment = to_moment(event.get("timestamp"), self.options)
        if moment is None:
            return
        state.first = moment if state.first is None else min(state.first, moment)
        state.last = moment if state.last is None else max(state.last, moment)
        kind = event.get("type")
        if not self._in_window(moment):
            if kind == "assistant":
                self._mark_out_of_range(event, state)
            return
        state.in_range = True
        day = moment.strftime("%Y-%m-%d")
        key = str(event.get("uuid") or "") or ("line:%d" % len(state.seen_events))
        if key not in state.seen_events:
            state.seen_events.add(key)
            self.metrics.heatmap[moment.weekday()][moment.hour] += 1
        if kind == "assistant":
            self._assistant(event, day, state)
        elif kind == "user":
            self._user(event, day, state)

    def _mark_out_of_range(self, event: Dict[str, Any], state: _FileState) -> None:
        """Remember tool ids outside the window so their results aren't orphans."""
        for block in _blocks((event.get("message") or {}).get("content")):
            if block.get("type") == "tool_use":
                state.out_of_range.add(str(block.get("id") or ""))

    def _assistant(self, event: Dict[str, Any], day: str, state: _FileState) -> None:
        message = event.get("message") or {}
        blocks = _blocks(message.get("content"))
        identifier = message.get("id")
        if not identifier:
            self.metrics.warnings["idless"] += 1
            identifier = event.get("uuid") or day
        state.messages.add(str(identifier))
        usage = message.get("usage")
        if isinstance(usage, dict):
            # Last snapshot per message wins: streamed events repeat the block.
            state.usage[str(identifier)] = (day, usage)
        for block in blocks:
            if block.get("type") == "tool_use":
                self._tool_use(block, day, state)
        if blocks and not event.get("isSidechain"):
            # One streamed message is one turn, so turns key on the message id.
            state.turn_messages[str(identifier)] = day
            state.turn_events += 1

    def _tool_use(self, block: Dict[str, Any], day: str, state: _FileState) -> None:
        identifier = str(block.get("id") or "")
        name = str(block.get("name") or "") or UNKNOWN_TOOL
        if not identifier:
            self.metrics.tools[name] = self.metrics.tools.get(name, 0) + 1
            return
        if identifier in state.uses:
            self.metrics.warnings["duplicate_tool_use"] += 1
            return
        state.uses[identifier] = (day, name)
        self.metrics.tools[name] = self.metrics.tools.get(name, 0) + 1

    def _user(self, event: Dict[str, Any], day: str, state: _FileState) -> None:
        content = (event.get("message") or {}).get("content")
        for block in _blocks(content):
            if block.get("type") != "tool_result":
                continue
            identifier = str(block.get("tool_use_id") or "")
            if not identifier or identifier in state.out_of_range:
                continue
            if identifier in state.results:
                self.metrics.warnings["duplicate_tool_result"] += 1
                continue
            state.results[identifier] = bool(block.get("is_error"))
        if event.get("isSidechain") or event.get("isMeta"):
            return
        if _has_user_text(content):
            state.user_turns[day] = state.user_turns.get(day, 0) + 1
            state.turn_events += 1

    def _finish_file(self, ref: TranscriptRef, state: _FileState) -> None:
        if not state.in_range:
            return
        metrics = self.metrics
        metrics.sessions += 1
        metrics.assistant_messages += len(state.messages)
        metrics.turn_events += state.turn_events
        metrics.user_turns += sum(state.user_turns.values())
        counted = list(state.user_turns.items())
        counted += [(day, 1) for day in state.turn_messages.values()]
        for day, count in counted:
            metrics.turns += count
            metrics.daily_turns[day] = metrics.daily_turns.get(day, 0) + count
        project = metrics.projects.setdefault(
            ref.project, dict(dict.fromkeys(TOKEN_KEYS, 0), sessions=0))
        if state.cwd:
            metrics.project_paths.setdefault(ref.project, state.cwd)
        project["sessions"] += 1
        for day, usage in state.usage.values():
            daily = metrics.daily_tokens.setdefault(day, dict.fromkeys(TOKEN_KEYS, 0))
            for raw, name in TOKEN_FIELDS:
                value = usage.get(raw)
                if isinstance(value, int):
                    metrics.tokens[name] += value
                    daily[name] += value
                    project[name] += value
        self._fold_tools(state)
        span = 0.0
        if state.first is not None and state.last is not None:
            span = (state.last - state.first).total_seconds() / 60.0
        label = minute_bucket(span)
        metrics.session_minutes[label] = metrics.session_minutes.get(label, 0) + 1

    def _fold_tools(self, state: _FileState) -> None:
        metrics = self.metrics
        for identifier, (day, _name) in state.uses.items():
            outcome = state.results.get(identifier)
            if outcome is None:
                metrics.tool_states["pending"] += 1
                continue
            key = "error" if outcome else "ok"
            metrics.tool_states[key] += 1
            daily = metrics.daily_errors.setdefault(day, {"ok": 0, "error": 0})
            daily[key] += 1
        for identifier in state.results:
            if identifier not in state.uses:
                metrics.tool_states["orphan"] += 1

    def finish(self) -> Metrics:
        """Close out derived values and return the metrics."""
        states = self.metrics.tool_states
        denominator = states["ok"] + states["error"]
        self.metrics.error_rate = (states["error"] / denominator) if denominator else 0.0
        return self.metrics


def aggregate(refs: Iterable[TranscriptRef], options: Optional[Options] = None,
              stats: Optional[ScanStats] = None) -> Metrics:
    """Fold every transcript, skipping and counting the ones that fail to read."""
    aggregator = Aggregator(options)
    aggregator.metrics.scan = stats if stats is not None else ScanStats()
    for ref in refs:
        try:
            aggregator.add(ref, read_events(ref))
        except OSError:
            aggregator.metrics.scan.skip("unreadable")
        except Exception:  # a malformed transcript must never abort the scan
            aggregator.metrics.scan.skip("parse-error")
        else:
            aggregator.metrics.scan.included += 1
    return aggregator.finish()
