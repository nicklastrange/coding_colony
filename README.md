# Agent V2

Agent V2 is a portable set of AI development workflows for teams and solo
developers who use Codex, Claude Code, or OpenCode.

It gives each harness the same high-level commands for planning, design,
implementation, review, verification, and repository documentation while still
using each harness in its native format.

## What You Get

- One workflow pack for Codex, Claude Code, and OpenCode.
- Slash-command workflows for `/spec`, `/refine`, `/analyze`, `/design`,
  `/implement`, `/implement-spike`, `/verify`, and `/bookskeeper`.
- Role-based agents with clear responsibilities, such as planner, implementer,
  reviewer, verifier, designer, and bookskeeper.
- Portable project installs that keep machine-specific paths and secrets in
  `.env`.
- Model tiers such as `fast`, `balanced`, `deep`, `design`, and `review` so
  agent definitions stay provider-neutral.
- Optional integrations for tools like Graphify, context-mode, Playwright MCP,
  and Gradle test summarization.
- Install output that contains only runtime files, not the installer source.

## Why Use It

Agent V2 is meant for projects where AI agents should follow repeatable
engineering workflows instead of improvising every task from scratch.

Typical use cases:

- Turn vague requests into refined implementation briefs.
- Analyze a repository and create implementation plans grounded in real code.
- Generate UI design systems and HTML mockups before implementation.
- Implement plans with focused code changes and verification.
- Review changes for bugs, regressions, missing tests, and project-rule
  violations.
- Build or refresh repository guidance from a Graphify knowledge graph.

## Supported Harnesses

- Codex
- Claude Code
- OpenCode

Install one harness when you only use one tool, or install all of them when you
move between tools.

## Quick Start

Install all supported harnesses into the current directory:

```bash
./install.sh --portable .
```

Install only OpenCode:

```bash
./install.sh --portable . --harness opencode
```

Install only Codex:

```bash
./install.sh --portable . --harness codex
```

Preview what would be generated without writing files:

```bash
./install.sh --portable . --dry-run
```

After installation, review the generated `.env`. It contains the workspace root,
enabled harnesses, provider profile, model tier mappings, and optional tool
status.

If you use `direnv`, run this once from the installed directory:

```bash
direnv allow
```

## Installation Modes

### Portable Install

Portable installs are best for a project-specific agent setup:

```bash
./install.sh --portable /path/to/agent-setup --root-dir /path/to/workspace
```

The installed folder can live beside the repositories it operates on. Runtime
paths are written to `.env`.

### Global Install

Global installs place the setup under your home directory:

```bash
./install.sh --global --root-dir /path/to/workspace
```

Use this when you want one shared setup across many local repositories.

## Harness Selection

When `--harness` is omitted, Agent V2 generates config for all supported
harnesses in best-effort mode.

When `--harness` is provided, installation is strict by default. If the selected
harness binary is missing, the installer fails so you know the generated setup
may not be usable.

Use `--no-strict` for best-effort generation:

```bash
./install.sh --portable . --harness opencode --no-strict
```

## Providers And Models

Agent V2 uses model tiers instead of hardcoding concrete models inside agent
workflows:

- `fast`
- `balanced`
- `deep`
- `design`
- `review`

By default, each harness uses its native provider profile. You only need
`--provider` when you intentionally want a different provider or gateway.

Example with LiteLLM:

```bash
./install.sh --portable . --harness codex --provider litellm --no-strict
```

Then set your LiteLLM values in `.env`:

```bash
LITELLM_BASE_URL=http://localhost:4000
LITELLM_API_KEY=...
```

You can change concrete model IDs later by editing the `AGENT_MODEL_*` values in
`.env`. Generated agent files should keep tier names, not provider-specific
model names.

## Optional Integrations

When run interactively, the installer can ask about optional tools one by one.
You can also enable them directly:

```bash
./install.sh --portable . --plugin graphify --plugin context-mode
```

If an enabled optional tool is missing, the installer can install it when you
approve the prompt. For non-interactive installs, opt in explicitly:

```bash
./install.sh --portable . --plugin graphify --install-missing-plugins
```

For Graphify, this installs the `graphifyy` package with `pipx` and then runs
`graphify install --platform <harness>` for each selected harness so the tool is
registered where the harness expects it.

Available integrations:

- `graphify`: graph-backed repository analysis and bookskeeping.
- `context-mode`: extra context MCP server.
- `playwright`: browser automation MCP server.
- `gradle-wrapper`: summarized Gradle test/check output for agent runs.

Optional tools are recorded in `.env`, so agents know whether a workflow can use
them. If a required optional tool is missing, agents should report that clearly
instead of pretending the tool ran.

## Commands

The same command names are available across supported harnesses:

- `/spec`: create or refresh a project specification.
- `/refine`: turn a raw request into a refined task.
- `/analyze`: inspect the repository and produce an implementation plan.
- `/design`: create a visual design system and HTML mockups.
- `/implement`: implement a plan and verify the result.
- `/implement-spike`: run a bounded technical spike.
- `/verify`: check an implementation against the plan and tests.
- `/bookskeeper`: generate repository guidance from Graphify output.

## Generated Files

Installed setups may contain:

- `.codex/**`
- `.claude/**`
- `.opencode/**`
- `.agents/**`
- `.mcp.json`
- `CLAUDE.md`
- `.env`
- `.envrc`
- `.agent-v2/**`
- `docs/**`

Installed setups should not receive source files such as `install.sh`,
`scripts/agent_setup.py`, `config/**`, or `core/**`.

## Development

Run the integrity tests before changing installer behavior, providers,
harnesses, commands, roles, or optional integrations:

```bash
python3 -m unittest discover -s tests -v
```

For LLM-oriented maintenance instructions, see `llms.txt`.
