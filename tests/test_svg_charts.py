"""Chart tests: structural assertions on generated SVG, no browser involved."""

import unittest
import xml.etree.ElementTree as ET

from cc_stats.aggregator import Metrics
from cc_stats.scanner import ScanStats
from cc_stats.svg_charts import (BUCKET_ORDER, cache_chart, errors_chart, esc,
                                 heatmap_chart, horizontal_bars, line_chart,
                                 projects_chart, sessions_chart, tokens_chart,
                                 tools_chart)

TOKEN_ZERO = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}


def tokens(inp=0, out=0, read=0, write=0):
    return {"input": inp, "output": out, "cache_read": read, "cache_creation": write}


def demo_metrics(**over):
    grid = [[0] * 24 for _ in range(7)]
    grid[0][9] = 12          # busiest cell
    grid[2][14] = 4
    values = dict(
        tokens=tokens(100, 200, 300, 40),
        daily_tokens={"2026-01-01": tokens(10, 20, 30, 4),
                      "2026-01-02": tokens(40, 50, 60, 7)},
        tools={"Bash": 5, "Read": 3, "Edit": 1},
        tool_states={"ok": 8, "error": 2, "pending": 1, "orphan": 0},
        daily_errors={"2026-01-01": {"ok": 4, "error": 1},
                      "2026-01-02": {"ok": 3, "error": 1}},
        error_rate=0.2,
        projects={"-w-alpha": dict(tokens(10, 20, 30, 4), sessions=2),
                  "-w-beta": dict(tokens(1, 2, 3, 4), sessions=1)},
        heatmap=grid,
        session_minutes={"1-5": 3, "16-30": 1},
        turns=7, sessions=3, assistant_messages=5,
        warnings={"idless": 0, "duplicate_tool_use": 0,
                  "duplicate_tool_result": 0, "malformed_lines": 0},
        scan=ScanStats(found=4, included=3, skipped=1),
    )
    values.update(over)
    return Metrics(**values)


ALL_CHARTS = (tokens_chart, cache_chart, tools_chart, projects_chart,
              heatmap_chart, sessions_chart, errors_chart)


class ChartStructureTestCase(unittest.TestCase):
    def test_every_chart_is_wellformed_svg(self):
        for chart in ALL_CHARTS:
            root = ET.fromstring(chart(demo_metrics()))
            self.assertEqual(root.tag, "svg", chart.__name__)
            self.assertTrue(root.get("viewBox"), chart.__name__)
            self.assertTrue(root.get("aria-label"), chart.__name__)

    def test_charts_carry_no_urls_or_scripts(self):
        for chart in ALL_CHARTS:
            markup = chart(demo_metrics())
            for banned in ("http://", "https://", "<script", "xmlns", "url("):
                self.assertNotIn(banned, markup, chart.__name__)

    def test_empty_metrics_still_produce_valid_charts(self):
        blank = Metrics(heatmap=[[0] * 24 for _ in range(7)])
        for chart in ALL_CHARTS:
            markup = chart(blank)
            self.assertEqual(ET.fromstring(markup).tag, "svg", chart.__name__)
        self.assertIn("No data yet", tokens_chart(blank))

    def test_single_axis_only(self):
        # One gridline set per chart: five lines, all spanning the same x range.
        for chart in (tokens_chart, cache_chart, errors_chart):
            root = ET.fromstring(chart(demo_metrics()))
            lines = [node for node in root.iter("line")
                     if node.get("class") == "grid"]
            self.assertEqual(len(lines), 5, chart.__name__)
            self.assertEqual(len({node.get("x1") for node in lines}), 1)
            self.assertEqual(len({node.get("x2") for node in lines}), 1)


class SeriesTestCase(unittest.TestCase):
    def test_tokens_chart_stacks_input_below_output(self):
        root = ET.fromstring(tokens_chart(demo_metrics()))
        areas = [node.get("fill") for node in root.iter("polygon")]
        self.assertEqual(areas, ["var(--s1)", "var(--s2)"])

    def test_cache_chart_uses_slots_one_and_three(self):
        root = ET.fromstring(cache_chart(demo_metrics()))
        self.assertEqual([node.get("fill") for node in root.iter("polygon")],
                         ["var(--s1)", "var(--s3)"])

    def test_legend_only_on_multi_series_charts(self):
        for chart in (tokens_chart, cache_chart):
            root = ET.fromstring(chart(demo_metrics()))
            swatches = [n for n in root.iter("rect") if n.get("class") == "swatch"]
            self.assertEqual(len(swatches), 2, chart.__name__)
        for chart in (tools_chart, projects_chart, sessions_chart, errors_chart):
            root = ET.fromstring(chart(demo_metrics()))
            self.assertEqual([n for n in root.iter("rect")
                              if n.get("class") == "swatch"], [], chart.__name__)

    def test_end_labels_never_overlap(self):
        # Both series end on nearly the same value, so the labels must separate.
        metrics = demo_metrics(daily_tokens={"2026-01-01": tokens(10, 10, 1, 1),
                                             "2026-01-02": tokens(1, 1000, 1, 1)})
        root = ET.fromstring(tokens_chart(metrics))
        ys = sorted(float(node.get("y")) for node in root.iter("text")
                    if node.get("class") == "val")
        for first, second in zip(ys, ys[1:]):
            self.assertGreaterEqual(second - first, 12.9)


class BarTestCase(unittest.TestCase):
    def test_tools_chart_bar_count_and_single_hue(self):
        root = ET.fromstring(tools_chart(demo_metrics()))
        bars = [node for node in root.iter("rect") if node.get("class") == "bar"]
        self.assertEqual(len(bars), 3)
        self.assertEqual({node.get("fill") for node in bars}, {"var(--s1)"})

    def test_tools_chart_groups_the_tail_into_other(self):
        many = dict(("tool%02d" % index, 30 - index) for index in range(20))
        root = ET.fromstring(tools_chart(demo_metrics(tools=many)))
        bars = [node for node in root.iter("rect") if node.get("class") == "bar"]
        self.assertEqual(len(bars), 13)  # top 12 plus one "Other"
        titles = [node.text for node in root.iter("title")]
        self.assertTrue(titles[-1].startswith("Other: "))
        # Other holds the 8 remaining tools: counts 18 down to 11.
        self.assertEqual(titles[-1], "Other: %s" % "{:,}".format(sum(range(11, 19))))

    def test_session_histogram_keeps_bucket_order(self):
        root = ET.fromstring(sessions_chart(demo_metrics()))
        labels = [node.text for node in root.iter("text")
                  if node.get("class") == "ax"]
        self.assertEqual(labels, list(BUCKET_ORDER))

    def test_project_rows_carry_sessions_and_a_token_column(self):
        root = ET.fromstring(projects_chart(demo_metrics()))
        bars = [node for node in root.iter("rect") if node.get("class") == "bar"]
        self.assertEqual(len(bars), 2)
        self.assertEqual({node.get("fill") for node in bars}, {"var(--s1)"})
        dim = [node.text for node in root.iter("text")
               if node.get("class") == "val dim"]
        self.assertEqual(dim, ["30 tok", "3 tok"])

    def test_long_names_are_clipped_but_kept_in_the_tooltip(self):
        name = "-Users-someone-" + "x" * 90
        root = ET.fromstring(horizontal_bars([(name, 1)], 920, "wide"))
        shown = [node for node in root.iter("text") if node.get("class") == "ax"]
        self.assertLess(len(shown[0].text), len(name))
        self.assertTrue(shown[0].text.startswith("…"))
        self.assertEqual(shown[0].find("title").text, name)


class HeatmapAndLineTestCase(unittest.TestCase):
    def test_heatmap_cell_count_and_zero_shading(self):
        root = ET.fromstring(heatmap_chart(demo_metrics()))
        cells = [node for node in root.iter("rect") if "cell" in (node.get("class") or "")]
        self.assertEqual(len(cells), 7 * 24)
        zeros = [node for node in cells if node.get("class") == "cell zero"]
        self.assertEqual(len(zeros), 7 * 24 - 2)
        hottest = [node for node in cells if node.get("class") == "cell r6"]
        self.assertEqual(len(hottest), 1)
        self.assertEqual(hottest[0].find("title").text, "Mon 09:00 — 12 events")

    def test_error_line_breaks_at_a_zero_denominator_day(self):
        days = ["2026-01-0%d" % index for index in range(1, 6)]
        metrics = demo_metrics(
            daily_tokens=dict((day, tokens(1, 1, 1, 1)) for day in days),
            daily_errors={days[0]: {"ok": 4, "error": 1}, days[1]: {"ok": 3, "error": 1},
                          days[3]: {"ok": 2, "error": 0}, days[4]: {"ok": 1, "error": 1}})
        root = ET.fromstring(errors_chart(metrics))
        polylines = list(root.iter("polyline"))
        self.assertEqual(len(polylines), 2)  # the middle day is a gap, not a zero
        self.assertEqual(len(list(root.iter("circle"))), 4)
        for node in polylines:
            self.assertEqual(node.get("stroke"), "var(--s2)")

    def test_all_none_line_renders_the_empty_state(self):
        markup = line_chart(["2026-01-01"], [None], 448, 210, "empty")
        self.assertIn("No data yet", markup)
        self.assertEqual(ET.fromstring(markup).tag, "svg")


class HostileInputTestCase(unittest.TestCase):
    def test_markup_in_names_stays_inert(self):
        nasty = '<script>alert("x")</script>'
        root = ET.fromstring(tools_chart(demo_metrics(tools={nasty: 3})))
        self.assertEqual([node.tag for node in root.iter("script")], [])
        titles = [node.text for node in root.iter("title")]
        self.assertIn(nasty, titles)            # full name tooltip on the label
        self.assertIn(nasty + ": 3", titles)    # value tooltip on the bar

    def test_quotes_and_controls_survive_as_text(self):
        nasty = 'a"b\'c<>&\x01\x7fd'
        markup = projects_chart(demo_metrics(
            projects={nasty: dict(tokens(1, 2, 3, 4), sessions=1)}))
        root = ET.fromstring(markup)  # would raise on a stray control character
        self.assertEqual(root.find(".//title").text, 'a"b\'c<>&d')
        self.assertNotIn("\x01", markup)

    def test_esc_escapes_both_contexts(self):
        self.assertEqual(esc('<a href="x">&'), "&lt;a href=&quot;x&quot;&gt;&amp;")
        self.assertEqual(esc("keep\x00me"), "keepme")


if __name__ == "__main__":
    unittest.main()
