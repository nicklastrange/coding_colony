# Coding Colony

Coding Colony is one centralized set of AI development workflows for teams and
solo developers who use Codex, Claude Code, or OpenCode.

It gives each harness the same high-level commands for product specification,
task refinement, implementation planning, implementation, verification, and
repository documentation while still using each harness in its native format.

## What You Get

- One workflow pack for Codex, Claude Code, and OpenCode.
- Slash-command workflows for `/spec`, `/refine`, `/analyze`, `/implement`,
  `/verify`, and `/bookskeeper`.
- Role-based agents with clear responsibilities, such as planner, implementer,
  reviewer, verifier, Scout, and bookskeeper.
- One installation shared by every selected harness and target repository.
- Model tiers `fast`, `balanced`, and `deep`, with per-agent tier and reasoning
  configuration in `coding-colony.json`.
- Separate conditional Kotlin, Spring Boot, and Flutter expert skills.
- Optional integrations for tools like Graphify, context-mode, Playwright MCP,
  and Gradle test summarization.
- Install output that contains only runtime files, not the installer source.

## Why Use It

Coding Colony is meant for projects where AI agents should follow repeatable
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

Install all harnesses you use into the same central location, then switch tools
between sessions without installing another copy.

## Quick Start

Install all supported harnesses into the default central location:

```bash
./install.sh --global --root-dir "$HOME/Code"
```

Install only OpenCode:

```bash
./install.sh --global --harness opencode
```

Install only Codex:

```bash
./install.sh --global --harness codex
```

Preview what would be generated without writing files:

```bash
./install.sh --global --dry-run
```

After installation, review `coding-colony.json` for models and per-agent
reasoning. `.env` contains generated paths, secrets, plugins, command overrides,
and optional tool status.

The installer writes a `coding-colony` launcher. Interactive installs ask
whether to add its directory to your shell startup file. Use `--no-path-prompt`
to skip that question. You can also add it manually to `PATH`:

```bash
export PATH="/path/to/agent-setup/.config/bin:$PATH"
cd /path/to/target-repository
coding-colony codex --yolo
```

Open a new shell or source the updated startup file after accepting the PATH
prompt.

By default, the launcher starts the harness in the Coding Colony installation
directory (`AGENT_ROOT`), regardless of the terminal's current directory. Use
`--repo PATH` to open a specific repository instead. The launcher reads
`coding-colony.json`,
synchronizes the selected harness's native files, and starts it with that path
as its real workspace. Claude Code and
OpenCode use the central `CLAUDE_CONFIG_DIR` or `OPENCODE_CONFIG_DIR`. Codex
keeps the user's active `CODEX_HOME`, so existing config, authentication,
sessions, state, user hooks, and MCP servers remain available. Coding Colony
adds its agents, hooks, limits, and namespaced MCP servers for that invocation
and links its central skill directory at `~/.agents/skills/coding-colony`.
Neither the user's Codex config nor auth file is rewritten.
Codex still applies its normal trust review to the added hooks.

The launcher also grants access to that project's central
`docs/<project-slug>/` directory.
Immediate children of `ROOT_DIR` keep a readable basename slug; nested or
external repositories receive a path-derived suffix so same-named projects
cannot share documents. On upgrade, an existing unmarked basename directory is
claimed automatically only when exactly one matching Git repository exists
under `ROOT_DIR`. Ambiguous ownership stops with an explicit marker-migration
instruction instead of exposing one project's docs to another.

If you use `direnv`, run this once from the installed directory:

```bash
direnv allow
```

## Installation Modes

### Portable Install

Portable installs choose a relocatable central location:

```bash
./install.sh --portable /path/to/agent-setup --root-dir /path/to/workspace
```

The installed folder can live anywhere and serve every repository it operates
on. Runtime paths are written to `.env`.

### Global Install

Global installs place the setup under `~/.coding-colony`:

```bash
./install.sh --global --root-dir /path/to/workspace
```

This is the default choice for one shared setup across many local repositories.

## Harness Selection

When `--harness` is omitted, Coding Colony generates config for all supported
harnesses in best-effort mode.

When `--harness` is provided, installation is strict by default. If the selected
harness binary is missing, the installer fails so you know the generated setup
may not be usable.

Use `--no-strict` for best-effort generation:

```bash
./install.sh --portable . --harness opencode --no-strict
```

## Providers And Models

Coding Colony uses model tiers instead of hardcoding concrete models inside agent
workflows:

- `fast`
- `balanced`
- `deep`

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

Change concrete tier mappings under `models.<harness>` and each agent's `model`
and `reasoning` under `agents` in `coding-colony.json`. Reasoning values are
passed through because harness and model vocabularies differ. The next
`coding-colony <harness>` launch validates the config and synchronizes that
harness; no reinstall is required. Running sessions are not hot-swapped.

For Codex, `models.codex.fast`, `balanced`, and `deep` select the named Colony
agents' models. The active Codex configuration keeps control of the root
session model and provider; `models.codex.default` remains in the shared schema
and generated central artifact but is not passed as a launcher override. Use
normal Codex config or append `--model` after the launcher's `--` separator to
choose the root model. Colony role files pin their own provider so a global
gateway choice cannot accidentally reinterpret a role's model ID.

For example, the generated agent entries can be changed to:

```json
{
  "gorn": { "model": "fast", "reasoning": "medium" },
  "lester": { "model": "deep", "reasoning": "max" }
}
```

## Conditional Development Skills

The central install provides separate `kotlin`, `spring-boot`, and `flutter`
skills in every selected harness. They are practical technology playbooks, with
focused references for Kotlin language and coroutine semantics, Spring runtime
and transaction behavior, and Flutter lifecycle and platform behavior.

During `/analyze`, Lester detects stacks from the affected modules and records
their evidence and exact skill names in the implementation plan. Skills compose:
a Kotlin Spring Boot service loads both `kotlin` and `spring-boot`, while a Java
Spring Boot service loads only `spring-boot`. During `/implement`, Gorn rechecks
the affected modules, rejects an omitted match, and loads every applicable skill
before editing. Lee loads the same skills and checks for omissions during review.

On first Codex launch, Coding Colony creates one symlink from
`~/.agents/skills/coding-colony` to the central skill directory. Later launches
reuse it, so reinstalling or updating the central setup updates every target
repository without copying skills. The launcher stops without overwriting if a
different file or directory already owns that exact registration path.

## Optional Integrations

When run interactively, the installer can ask about optional tools one by one.
You can also enable them directly:

```bash
./install.sh --global --plugin graphify --plugin context-mode
```

If an enabled optional tool is missing, the installer can install it when you
approve the prompt. For non-interactive installs, opt in explicitly:

```bash
./install.sh --global --plugin graphify --install-missing-plugins
```

For Graphify, this installs the `graphifyy` package with `pipx` and then runs
`graphify install --project --platform <harness>` from the central install for
each selected harness so the tool cannot mutate unrelated user-global or source
configuration.

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

## Central Install Layout

The important generated entries are `coding-colony.json`, `.env`, `docs/`, the
`.config/bin/coding-colony` launcher, and one native runtime directory per
selected harness: `.codex/`, `.claude/`, or `.opencode/`. These harness folders
are views inside the same install, not separate Coding Colony copies. Target
repositories keep their own source, `AGENTS.md`, and `graphify-out/` guidance.

## Development

Run the integrity tests before changing installer behavior, providers,
harnesses, commands, roles, or optional integrations:

```bash
python3 -m unittest discover -s tests -v
```

For LLM-oriented maintenance instructions, see `llms.txt`.
