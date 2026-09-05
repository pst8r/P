# CLAUDE.md

Guidance for AI assistants (Claude Code and others) working in this repository.

## What this repository is

**P** ("Project Mgmt") is a **project-management / strategy repository**, not a
software codebase. It holds planning artifacts — primarily
[draw.io](https://app.diagrams.net) diagrams — that capture business and product
strategy, plus one small tool: the **stock-movement monitor** in `monitor/`
(see below). There is **no build system, test suite, or dependency manifest**
here. Do not scaffold tooling unless the user explicitly asks.

Set expectations accordingly: tasks here are about **editing content and
diagrams**, and occasionally extending the monitor script.

## Repository layout

```
.
├── README.md                 # Repository overview
├── 2024 w4 Strategy.drawio    # draw.io strategy diagram (Week 4, 2024)
└── monitor/                  # Stock-movement monitor (Python + generated HTML dashboard)
    ├── README.md             # Usage, parameters and setup rules (Spanish)
    ├── config.json           # Watchlist, indicator/signal thresholds, risk parameters
    ├── stock_monitor.py      # Stdlib-only script; yfinance optional for live data
    └── output/               # Sample monitor.json / monitor.html generated with --demo
```

- **`*.drawio` files** are diagrams.net documents: XML (`<mxfile>` /
  `<mxGraphModel>`) describing shapes, swimlanes, and connectors. They are
  plain UTF-8 text and diff/merge as text, but they are meant to be **viewed and
  edited visually** at <https://app.diagrams.net> or the diagrams.net desktop /
  VS Code extension.
- File names encode the time period and topic (e.g. `2024 w4 Strategy` =
  Week 4, 2024). Follow that convention when adding new diagrams.

### About the current diagram

`2024 w4 Strategy.drawio` is a **swimlane (BPMN-style) process flowchart**: a
`Pool` with `Lane 1`–`Lane 3`, decision nodes (`Yes` / `No` branches), and steps
covering a digital-product strategy (identifying problems on Quora, evaluating a
"PLR.ME" digital product). When asked about "the strategy" or "the process,"
this is the file to read.

## Working with `.drawio` files

- **Reading content:** the human-readable labels live in `value="..."`
  attributes of `<mxCell>` elements. To scan a diagram's text without opening it
  visually, extract those values. Note that labels may contain HTML entities
  (`&amp;nbsp;`, `&lt;br&gt;`) and inline HTML — decode them when summarizing.
- **Editing:** prefer editing in diagrams.net so geometry, IDs, and styling stay
  consistent. If you must edit the XML directly, change only `value` text and
  keep every `id`, `parent`, `source`, `target`, and `<mxGeometry>` intact —
  breaking an `id` or edge reference corrupts the diagram. Never renumber or
  reuse cell IDs.
- **Do not reformat** the XML wholesale (line wrapping, attribute reordering).
  diagrams.net writes long single-line elements on purpose; reformatting
  produces huge, unreviewable diffs.

### About the stock-movement monitor

`monitor/stock_monitor.py` downloads daily + intraday prices for the watchlist
in `monitor/config.json`, computes indicators (SMA/EMA, RSI, MACD, Bollinger,
ATR, ADX, RVOL, VWAP, opening range), classifies each instrument's trend,
detects day-trading setups (breakout, gap-and-go, pullback, mean reversion,
volatility squeeze, ORB) with entry/stop/target/position size, and writes
`monitor/output/monitor.json` + a self-contained `monitor.html` dashboard.

- Pure standard library; `yfinance` is optional (`--source auto|yfinance|stooq|demo`).
- `python3 monitor/stock_monitor.py --demo` regenerates the sample output
  offline with deterministic synthetic data — run it after changing the
  script or the HTML template, and commit the regenerated `output/` files.
- The HTML template lives inside the script (`HTML_TEMPLATE`) and must stay
  self-contained: no CDN scripts, no external fonts, hand-rolled SVG charts.
- Client-facing text in the dashboard is Spanish. It is an analysis tool, not
  investment advice; keep the disclaimer.

## Development workflow

There is nothing to build, lint, or test for the diagrams. For the monitor,
"tested" means `--demo` runs without errors and the dashboard opens with no
console errors. "Done" means the change is made and committed.

### Git & branching

- **Never commit directly to `main`.** Do all work on a feature branch, then
  push that branch. Only open a pull request if the user explicitly asks.
- When this session is assigned a specific working branch, develop and push
  there; create it from the latest `main` if it does not exist.
- **Commit messages** in this repo have historically just named the artifact
  touched (e.g. `2024 w4 Strategy.drawio`). Prefer a slightly more descriptive
  message that says *what changed* (e.g.
  `Update Week 4 strategy: add PLR.ME evaluation branch`), while still naming
  the affected file/topic.
- Keep the working tree clean; commit the actual `.drawio` file, not exported
  images, unless the user asks for an export.

## Conventions & guardrails

- **Honesty over invention.** If asked to "analyze the codebase" or "run the
  tests," state plainly that this is a documents/diagram repository with no code
  — then help with the diagrams. Do not fabricate an architecture.
- **Preserve diagram integrity** (IDs, references, geometry) as described above.
- **Match existing naming** for new files (`YYYY wN <Topic>.drawio` or a clear
  equivalent) and update `README.md` if the repository's purpose broadens.
- **Ask before restructuring.** With so few files, reorganizing into folders or
  changing formats is a meaningful decision — confirm with the user first.
