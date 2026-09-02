"""Static page assets for the generated dashboard.

Markup and CSS only: the page contains no ``<script>`` element at all, and every
asset is inlined, so the dashboard makes no network request of any kind.

Series and ramp colours live in CSS custom properties, which lets a single set
of inline SVG charts serve both colour schemes. The sequential ramp is listed
light-to-dark for the light surface and reversed for the dark one, so that in
both schemes the near-zero end recedes into the page background.
"""

# 16x16 PNG. A PNG data URI avoids the xmlns URL an inline SVG icon would need.
FAVICON = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAA"
           "JUlEQVR42mMQEpEiCTEMAg2W7U8haIhpQFY0lDTgUjSAGmiV+AAWD5fcS+ZeXAAAAABJ"
           "RU5ErkJggg==")

CSS = """
:root {
  color-scheme: dark;
  --bg: #12141a; --panel: #191c24; --panel-2: #1f232d; --line: #2b303c;
  --fg: #e6e8ee; --fg-dim: #99a0b0; --grid: #2b303c;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70;
  --r0: #0d366b; --r1: #184f95; --r2: #256abf; --r3: #3987e5;
  --r4: #6da7ec; --r5: #9ec5f4; --r6: #cde2fb;
}
@media (prefers-color-scheme: light) {
  :root {
    color-scheme: light;
    --bg: #f6f7f9; --panel: #ffffff; --panel-2: #eef0f5; --line: #d3d8e2;
    --fg: #1b1f28; --fg-dim: #555f70; --grid: #e4e8ef;
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
    --r0: #cde2fb; --r1: #9ec5f4; --r2: #6da7ec; --r3: #3987e5;
    --r4: #256abf; --r5: #184f95; --r6: #0d366b;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
.topbar {
  position: sticky; top: 0; z-index: 5; background: var(--panel);
  border-bottom: 1px solid var(--line); padding: 12px 20px;
}
.topbar h1 { margin: 0 0 3px; font-size: 16px; font-weight: 600; }
.crumbs { color: var(--fg-dim); font-size: 12px; display: flex; flex-wrap: wrap; gap: 10px; }
.wrap { max-width: 1000px; margin: 0 auto; padding: 18px 20px 30px; }
.tiles {
  display: grid; gap: 10px; margin-bottom: 16px;
  grid-template-columns: repeat(auto-fit, minmax(min(150px, 100%), 1fr));
}
.tile {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 9px; padding: 10px 12px;
}
.tile b { display: block; font-size: 19px; font-variant-numeric: tabular-nums; }
.tile span {
  color: var(--fg-dim); font-size: 11px; text-transform: uppercase; letter-spacing: .05em;
}
.tile.warn { border-color: var(--s2); }
.tile.warn b { color: var(--s2); }
/* A date range is far longer than a count, so it gets two columns and
   smaller type instead of wrapping and stretching the whole tile row. */
.tile.span2 { grid-column: span 2; }
.tile.span2 b { font-size: 14px; }
.cards {
  display: grid; gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
}
.card {
  background: var(--panel); border: 1px solid var(--line); border-radius: 9px;
  padding: 12px 14px 10px; min-width: 0;
}
.card.wide { grid-column: 1 / -1; }
.card h2 { margin: 0 0 2px; font-size: 13px; font-weight: 600; }
.card p { margin: 0 0 8px; color: var(--fg-dim); font-size: 11.5px; }
.chart { width: 100%; height: auto; display: block; overflow: visible; }
.chart .ax { fill: var(--fg-dim); font-size: 11px; }
.chart .mid { font-size: 13px; }
.chart .val { fill: var(--fg); font-size: 11px; font-variant-numeric: tabular-nums; }
.chart .val.dim { fill: var(--fg-dim); }
.chart .grid { stroke: var(--grid); stroke-width: 1; shape-rendering: crispEdges; }
.chart .area { fill-opacity: .85; }
.chart .line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.chart .bar, .chart .cell, .chart .swatch { rx: 2; }
.chart .cell.r0 { fill: var(--r0); }
.chart .cell.r1 { fill: var(--r1); }
.chart .cell.r2 { fill: var(--r2); }
.chart .cell.r3 { fill: var(--r3); }
.chart .cell.r4 { fill: var(--r4); }
.chart .cell.r5 { fill: var(--r5); }
.chart .cell.r6 { fill: var(--r6); }
.chart .cell.zero { fill: var(--panel-2); }
.foot {
  max-width: 1000px; margin: 0 auto; padding: 12px 20px 30px;
  border-top: 1px solid var(--line); color: var(--fg-dim); font-size: 11.5px;
  display: flex; flex-wrap: wrap; gap: 10px;
}
@media (max-width: 560px) {
  .wrap, .foot { padding-left: 12px; padding-right: 12px; }
}
"""

TEMPLATE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="cc-stats %%VERSION%%">
<title>cc-stats &middot; %%TITLE%%</title>
<link rel="icon" href="%%FAVICON%%">
<style>%%CSS%%</style>
</head>
<body>
<header class="topbar">
  <h1>Claude Code statistics</h1>
  <div class="crumbs">%%CRUMBS%%</div>
</header>
<main class="wrap">
  <section class="tiles">%%TILES%%</section>
  <section class="cards">%%CARDS%%</section>
</main>
<footer class="foot">%%FOOTER%%</footer>
</body>
</html>
"""
