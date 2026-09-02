"""Pure functions turning aggregated metrics into inline SVG chart markup.

No JavaScript is involved: every chart is fully rendered here and the only
interactivity is the ``<title>`` tooltip browsers show natively. Colours are CSS
custom properties, so one SVG serves both colour schemes. Inline SVG carries no
``xmlns``: the HTML parser supplies it, which keeps all URLs out of the page.
"""

import html
from typing import Callable, Dict, List, Optional, Sequence, Tuple

FULL_WIDTH, HALF_WIDTH = 920, 448
BAR_GAP, RAMP_STEPS, TOP_TOOLS = 2, 7, 12
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
BUCKET_ORDER = ("0", "1-5", "6-15", "16-30", "31-60", "61-120", "120+")


def esc(value: object) -> str:
    """Escape for text and attribute use, dropping XML-illegal C0 controls."""
    text = "".join(char for char in str(value) if char >= " " and char != "\x7f")
    return html.escape(text, quote=True)


def _co(value: float) -> str:
    return ("%.1f" % float(value)).rstrip("0").rstrip(".")


def _num(value: float) -> str:
    return "{:,}".format(int(value))


def _compact(value: float) -> str:
    number = float(value)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(number) >= limit:
            return ("%.1f" % (number / limit)).replace(".0", "") + suffix
    return str(int(number))


def _text(x: float, y: float, value: object, cls: str = "ax",
          anchor: str = "start") -> str:
    return ('<text class="%s" x="%s" y="%s" text-anchor="%s">%s</text>'
            % (cls, _co(x), _co(y), anchor, esc(value)))


def _svg(width: int, height: float, body: str, label: str) -> str:
    return ('<svg class="chart" viewBox="0 0 %d %s" role="img" aria-label="%s">%s</svg>'
            % (width, _co(height), esc(label), body))


def _empty(width: int, label: str) -> str:
    return _svg(width, 120, _text(width / 2.0, 60, "No data yet", "ax mid", "middle"), label)


def _grid(left: float, top: float, plot_w: float, plot_h: float,
          peak: float, steps: int = 4) -> str:
    """Hairline horizontal gridlines with muted value labels."""
    out = []
    for index in range(steps + 1):
        ratio = index / float(steps)
        y = top + plot_h - plot_h * ratio
        out.append('<line class="grid" x1="%s" y1="%s" x2="%s" y2="%s"/>'
                   % (_co(left), _co(y), _co(left + plot_w), _co(y)))
        out.append(_text(left - 8, y + 4, _compact(peak * ratio), "ax", "end"))
    return "".join(out)


def stacked_area(days: Sequence[str], rows: Sequence[Dict[str, int]],
                 series: Sequence[Tuple[str, str, str]], width: int,
                 height: int, label: str) -> str:
    """Stacked area over days. ``series`` is (key, legend label, css var)."""
    if not days:
        return _empty(width, label)
    left, right, top, bottom = 58.0, 74.0, 18.0, 26.0
    plot_w, plot_h = width - left - right, height - top - bottom
    totals = [sum(row.get(key, 0) for key, _lb, _cv in series) for row in rows]
    peak = max(totals) or 1
    count = len(days)
    xs = [left + (plot_w / 2.0 if count == 1 else plot_w * i / (count - 1.0))
          for i in range(count)]
    if count == 1:
        xs = [left, left + plot_w]
        rows = [rows[0], rows[0]]
    body = [_grid(left, top, plot_w, plot_h, peak)]
    lower, labels = [0.0] * len(xs), []
    for key, legend, colour in series:
        upper = [lower[i] + rows[i].get(key, 0) for i in range(len(xs))]
        points = ["%s,%s" % (_co(xs[i]), _co(top + plot_h - plot_h * upper[i] / peak))
                  for i in range(len(xs))]
        points += ["%s,%s" % (_co(xs[i]), _co(top + plot_h - plot_h * lower[i] / peak))
                   for i in range(len(xs) - 1, -1, -1)]
        body.append('<polygon class="area" fill="%s" points="%s"><title>%s</title></polygon>'
                    % (colour, " ".join(points), esc(legend)))
        mid = top + plot_h - plot_h * (upper[-1] + lower[-1]) / (2.0 * peak)
        labels.append((mid, "%s %s" % (_compact(rows[-1].get(key, 0)), legend)))
        lower = upper
    body.extend(_spread(labels, left + plot_w + 6, top, top + plot_h))
    body.append(_text(left, height - 6, days[0], "ax"))
    if count > 1:
        body.append(_text(left + plot_w, height - 6, days[-1], "ax", "end"))
    if len(series) > 1:
        body.append(_legend(left, top - 6, series))
    return _svg(width, height, "".join(body), label)


def _spread(labels: List[Tuple[float, str]], x: float, low: float,
            high: float, gap: float = 13.0) -> List[str]:
    """Emit end-of-series labels, pushed apart so they can never overlap."""
    out, previous = [], None  # type: List[str], Optional[float]
    for y, text in sorted(labels):
        y = min(max(y, low + 4), high)
        if previous is not None and y - previous < gap:
            y = previous + gap
        previous = y
        out.append(_text(x, y + 4, text, "val"))
    return out


def _clip(text: str, room: float) -> str:
    """Trim a label to the space available, keeping the informative tail."""
    limit = max(int(room / 6.2), 8)
    return text if len(text) <= limit else "…" + text[-(limit - 1):]


def _legend(x: float, y: float, series: Sequence[Tuple[str, str, str]]) -> str:
    out, offset = [], 0.0
    for _key, legend, colour in series:
        out.append('<rect class="swatch" x="%s" y="%s" width="9" height="9" fill="%s"/>'
                   % (_co(x + offset), _co(y - 8), colour))
        out.append(_text(x + offset + 13, y, legend, "ax"))
        offset += 22 + 7.0 * len(legend)
    return "".join(out)


def horizontal_bars(items: Sequence[Tuple[str, float]], width: int, label: str,
                    extras: Optional[Dict[str, str]] = None,
                    name_width: float = 150.0) -> str:
    """Single-hue horizontal bars; values sit to the right of each bar."""
    if not items:
        return _empty(width, label)
    row_h, value_w = 22.0, 78.0
    extra_w = 96.0 if extras else 0.0
    plot_w = width - name_width - value_w - extra_w - 12
    peak = max(value for _name, value in items) or 1
    height = row_h * len(items) + 14
    body = []
    for index, (name, value) in enumerate(items):
        y = 8 + index * row_h
        bar = plot_w * (value / float(peak))
        body.append('<text class="ax" x="%s" y="%s" text-anchor="end">%s<title>%s</title>'
                    '</text>' % (_co(name_width - 8), _co(y + 14),
                                 esc(_clip(name, name_width - 12)), esc(name)))
        body.append('<rect class="bar" x="%s" y="%s" width="%s" height="%s" fill="var(--s1)">'
                    '<title>%s: %s</title></rect>'
                    % (_co(name_width), _co(y), _co(max(bar, 1.0)),
                       _co(row_h - BAR_GAP), esc(name), esc(_num(value))))
        body.append(_text(name_width + bar + 7, y + 14, _num(value), "val"))
        if extras:
            body.append(_text(width - 4, y + 14, extras.get(name, ""), "val dim", "end"))
    return _svg(width, height, "".join(body), label)


def vertical_bars(pairs: Sequence[Tuple[str, float]], width: int, height: int,
                  label: str) -> str:
    """Single-hue column chart with a value label above every column."""
    if not pairs or not any(value for _name, value in pairs):
        return _empty(width, label)
    left, top, bottom = 16.0, 22.0, 28.0
    plot_w, plot_h = width - left * 2, height - top - bottom
    peak = max(value for _name, value in pairs) or 1
    slot = plot_w / float(len(pairs))
    body = []
    for index, (name, value) in enumerate(pairs):
        bar_h = plot_h * (value / float(peak))
        x = left + index * slot
        body.append('<rect class="bar" x="%s" y="%s" width="%s" height="%s" fill="var(--s1)">'
                    '<title>%s: %s</title></rect>'
                    % (_co(x), _co(top + plot_h - bar_h), _co(slot - BAR_GAP * 2),
                       _co(max(bar_h, 1.0)), esc(name), esc(_num(value))))
        body.append(_text(x + slot / 2.0, top + plot_h - bar_h - 5, _num(value),
                          "val", "middle"))
        body.append(_text(x + slot / 2.0, height - 9, name, "ax", "middle"))
    return _svg(width, height, "".join(body), label)


def heatmap(grid: Sequence[Sequence[int]], width: int, label: str) -> str:
    """Weekday rows by hour columns, shaded with the sequential ramp."""
    peak = max((max(row) for row in grid), default=0)
    left, top, cell_h = 38.0, 18.0, 20.0
    cell_w = (width - left - 8) / 24.0
    height = top + cell_h * 7 + 16
    body = []
    for hour in range(0, 24, 3):
        body.append(_text(left + cell_w * hour + cell_w / 2.0, top - 6, hour, "ax", "middle"))
    for row_index, row in enumerate(grid):
        body.append(_text(left - 8, top + row_index * cell_h + 14,
                          WEEKDAYS[row_index], "ax", "end"))
        for hour, value in enumerate(row):
            # Exact zero is "no activity", not a low count: neutral surface.
            shade = "zero" if not value or not peak else "r%d" % min(
                RAMP_STEPS - 1,
                1 + int((RAMP_STEPS - 2) * (value - 1) / float(max(peak - 1, 1))))
            body.append('<rect class="cell %s" x="%s" y="%s" width="%s" height="%s">'
                        '<title>%s %02d:00 — %s events</title></rect>'
                        % (shade, _co(left + hour * cell_w),
                           _co(top + row_index * cell_h), _co(cell_w - BAR_GAP),
                           _co(cell_h - BAR_GAP), WEEKDAYS[row_index], hour, _num(value)))
    return _svg(width, height, "".join(body), label)


def line_chart(days: Sequence[str], values: Sequence[Optional[float]], width: int,
               height: int, label: str, suffix: str = "%") -> str:
    """Line over days; ``None`` values break the line instead of reading zero."""
    present = [value for value in values if value is not None]
    if not present:
        return _empty(width, label)
    left, right, top, bottom = 58.0, 22.0, 18.0, 26.0
    plot_w, plot_h = width - left - right, height - top - bottom
    peak = max(present) or 1.0
    count = len(days)
    body = [_grid(left, top, plot_w, plot_h, peak)]
    segment, best = [], max(range(len(values)), key=lambda i: values[i] or -1.0)
    for index, value in enumerate(values):
        x = left + (plot_w / 2.0 if count == 1 else plot_w * index / (count - 1.0))
        if value is None:
            if len(segment) > 1:
                body.append('<polyline class="line" stroke="var(--s2)" points="%s"/>'
                            % " ".join(segment))
            segment = []
            continue
        y = top + plot_h - plot_h * (value / peak)
        segment.append("%s,%s" % (_co(x), _co(y)))
        body.append('<circle class="dot" cx="%s" cy="%s" r="2.5" fill="var(--s2)">'
                    '<title>%s: %.1f%s</title></circle>'
                    % (_co(x), _co(y), esc(days[index]), value, esc(suffix)))
        if index == best:
            body.append(_text(x, y - 8, "%.1f%s" % (value, suffix), "val", "middle"))
    if len(segment) > 1:
        body.append('<polyline class="line" stroke="var(--s2)" points="%s"/>'
                    % " ".join(segment))
    body.append(_text(left, height - 6, days[0], "ax"))
    if count > 1:
        body.append(_text(left + plot_w, height - 6, days[-1], "ax", "end"))
    return _svg(width, height, "".join(body), label)


def tokens_chart(metrics: object) -> str:
    days = sorted(metrics.daily_tokens)
    rows = [metrics.daily_tokens[day] for day in days]
    series = [("input", "in", "var(--s1)"), ("output", "out", "var(--s2)")]
    return stacked_area(days, rows, series, FULL_WIDTH, 240, "Daily tokens in and out")


def cache_chart(metrics: object) -> str:
    days = sorted(metrics.daily_tokens)
    rows = [metrics.daily_tokens[day] for day in days]
    series = [("cache_read", "read", "var(--s1)"),
              ("cache_creation", "written", "var(--s3)")]
    return stacked_area(days, rows, series, HALF_WIDTH, 210, "Daily cache tokens")


def tools_chart(metrics: object) -> str:
    ranked = sorted(metrics.tools.items(), key=lambda kv: (-kv[1], kv[0]))
    items = [(name, count) for name, count in ranked[:TOP_TOOLS]]
    rest = sum(count for _name, count in ranked[TOP_TOOLS:])
    if rest:
        items.append(("Other", rest))
    return horizontal_bars(items, FULL_WIDTH, "Tool distribution")


def projects_chart(metrics: object, label_for: Optional[Callable] = None) -> str:
    """``label_for`` maps a raw directory name to its display label."""
    show = label_for or (lambda name: name)
    ranked = sorted(metrics.projects.items(),
                    key=lambda kv: (-kv[1].get("sessions", 0), kv[0]))[:TOP_TOOLS]
    items = [(show(name), data.get("sessions", 0)) for name, data in ranked]
    extras = dict((show(name), _compact(data.get("input", 0) + data.get("output", 0))
                   + " tok") for name, data in ranked)
    return horizontal_bars(items, FULL_WIDTH, "Sessions per project", extras=extras,
                           name_width=250.0)


def heatmap_chart(metrics: object) -> str:
    return heatmap(metrics.heatmap, FULL_WIDTH, "Activity by weekday and hour")


def sessions_chart(metrics: object) -> str:
    pairs = [(name, metrics.session_minutes.get(name, 0)) for name in BUCKET_ORDER]
    return vertical_bars(pairs, HALF_WIDTH, 210, "Session length in minutes")


def errors_chart(metrics: object) -> str:
    days = sorted(set(metrics.daily_tokens) | set(metrics.daily_errors))
    values = []  # type: List[Optional[float]]
    for day in days:
        counts = metrics.daily_errors.get(day)
        total = (counts["ok"] + counts["error"]) if counts else 0
        values.append(100.0 * counts["error"] / total if total else None)
    return line_chart(days, values, HALF_WIDTH, 210, "Daily tool error rate")
