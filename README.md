# Coding Colony

Coding Colony is a portable set of AI development workflows for teams and solo
developers who use Codex, Claude Code, or OpenCode.

It gives each harness the same high-level commands for product specification,
task refinement, implementation planning, implementation, verification, and
repository documentation while still using each harness in its native format.

## What You Get

- One workflow pack for Codex, Claude Code, and OpenCode.
- Slash-command workflows for `/spec`, `/refine`, `/analyze`, `/implement`,
  `/verify`, and `/bookskeeper`.
- Role-based agents with clear responsibilities, such as planner, implementer,
  reviewer, verifier, Scout, and bookskeeper.
- Portable project installs that keep machine-specific paths and secrets in
  `.env`.
- Model tiers `fast`, `balanced`, `deep`, and `review` so agent definitions stay
  provider-neutral.
- Optional integrations for tools like Graphify, context-mode, Playwright MCP,
  and Gradle test summarization.
- Install output that contains only runtime files, not the installer source.

## Why Use It

Agent V2 is meant for projects where AI agents should follow repeatable
engineering workflows instead of improvising every task from scratch.

Typical use cases:

- Turn vague requests into refined implementation briefs.
- Analyze a repository and create implementation plans grounded in real code.
- Implement plans with focused code changes, verification, and mandatory review
  until the result passes or an external blocker is reached.
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

The installer also writes one profile per selected harness (`codex.env`,
`claude.env`, or `opencode.env`) and a `coding-colony` launcher. Interactive
installs ask whether to add the launcher directory to your shell's
startup file. Use `--no-path-prompt` to skip that question. You can also add it
manually to `PATH` to start a harness from a target repository:

```bash
export PATH="/path/to/agent-setup/.config/bin:$PATH"
cd /path/to/target-repository
coding-colony codex --yolo
```

Open a new shell or source the updated startup file after accepting the PATH
prompt.

Use `--repo PATH` when launching from another directory. The launcher activates
the selected profile and passes the target repository to generated Gradle
redirects. When using the launcher, edit the corresponding `codex.env`,
`claude.env`, or `opencode.env`; it copies the selected profile to `.env`, so
direct edits to `.env` are not durable across launches.

`AGENT_MODEL_DEFAULT` controls the main/default harness agent independently from
the role tiers. `AGENT_MODEL_FAST`, `AGENT_MODEL_BALANCED`, `AGENT_MODEL_DEEP`,
and `AGENT_MODEL_REVIEW` control the specialized agents.

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
- `review`

By default, each harness uses its native provider profile. You only need
`--provider` when you intentionally want a compatible gateway. Profiles declare
their supported harnesses, and the installer rejects combinations whose model
IDs or transport cannot work there. The bundled LiteLLM and OpenRouter gateway
profiles currently target Codex.

Example with LiteLLM:

```bash
./install.sh --portable . --harness codex --provider litellm --no-strict
```

Then set your LiteLLM values in `.env`:

```bash
LITELLM_BASE_URL=http://localhost:4000
LITELLM_API_KEY=...
```

You can change concrete model IDs later through the `AGENT_MODEL_*` values. Edit
the harness-specific profile when using `coding-colony`, or `.env` when starting
a harness directly from the installed setup. OpenCode resolves the active
profile when its configuration reloads. Codex refreshes its root config and
custom-agent files from the active `.env` at SessionStart, so restart Codex after
changing them. Claude Code agent frontmatter requires concrete models; rerun the
installer after changing its profile. Generated workflow instructions remain
provider-neutral and continue to identify agents by tier.

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

Scout remains available without Graphify as a fast, read-only agent for bounded
file, symbol, caller, test, and configuration discovery. Graphify is optional
for the other workflows but is a prerequisite for `/bookskeeper`.

## Commands

The same command names are available across supported harnesses:

- `/spec`: create or refresh the product-level project specification.
- `/refine`: turn a raw request into a business-focused task that ends in
  `READY` or `NEEDS_INPUT`.
- `/analyze`: produce an evidence-backed, traceable implementation and review
  plan that ends in `READY` or `BLOCKED`.
- `/implement`: implement a ready plan, verify it, and repeat the Lee review and
  remediation loop until `PASS` or an external blocker. Changes that can affect
  application wiring, configuration, dependencies, or runtime initialization
  require startup/bootstrap evidence.
- `/verify`: independently check an implementation against requirements, the
  plan, repository evidence, and tests.
- `/bookskeeper`: initialize or incrementally refresh Graphify-backed repository
  guidance. Repository-changing workflows use `graphify-out/needs_update` to
  signal stale knowledge; Bookskeeper runs the cheap `graphify update <repo>`
  freshness gate for every existing graph, uses the marker to narrow document
  work, and clears it only after success.

Rhobar, Milten, Lester, and Xardas may use Scout for cheap bounded discovery;
the parent agent still owns and validates the conclusion. The same six command
bindings are generated for Codex, Claude Code, and OpenCode.

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
- `.config/**`
- `codex.env`, `claude.env`, `opencode.env`
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
