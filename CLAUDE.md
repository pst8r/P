# CLAUDE.md

## Repository Overview

**pst8r/P** is a project management repository for strategic planning and workflow visualization. It contains no source code — only documentation and diagram assets.

## Repository Contents

```
P/
├── README.md                    # Minimal project description
└── 2024 w4 Strategy.drawio      # Draw.io BPMN process-flow diagram
```

### Files

- **`README.md`** — One-line description ("Project Mgmt").
- **`2024 w4 Strategy.drawio`** — A Draw.io diagram (XML format) depicting a multi-lane BPMN-style process flow. The flow covers a user journey from identifying a problem (e.g. via Quora) through decision gateways that route to a "PLR.ME Digital Product" resolution path.

## Working with Draw.io Files

`.drawio` files are XML-based diagrams editable with:
- [draw.io desktop app](https://github.com/jgraph/drawio-desktop/releases) (offline)
- [draw.io web app](https://app.diagrams.net/) (browser)
- VS Code extension: **Draw.io Integration** (`hediet.vscode-drawio`)

When editing `.drawio` files, open them in one of the above tools rather than editing the raw XML directly. Commit the saved `.drawio` file after changes.

## Git Conventions

- **Main branch**: `main`
- **Feature branches**: use descriptive names (e.g. `claude/claude-md-docs-5w5CW`)
- Commit messages should describe *what changed* in the diagram or documentation (e.g. `"Add Q2 strategy lane to 2024 w4 diagram"`)
- No build, lint, or test steps exist — commits can go directly to a PR

## Adding New Assets

- Place new diagrams in the repository root or a `/diagrams` subdirectory if the collection grows.
- Use the naming convention `<year> w<week> <Topic>.drawio` for weekly strategy files.
- For documentation files, prefer Markdown (`.md`).

## No Build / Test / CI

This repository has no build system, package manager, test suite, or CI pipeline. There is nothing to install or run.
