# Agentic Setup

This repository is a portable agentic development setup. Runtime paths and
machine-specific options are generated into `.env` by `./install.sh`; do not
hardcode local paths in instructions, hooks, plugins, or harness config.

## Runtime Configuration

- `ROOT_DIR` is the workspace root containing target repositories.
- `AGENT_ROOT` is the installed copy of this setup.
- `AGENT_HARNESSES` lists generated harnesses: `codex`, `claude`, `opencode`.
- `AGENT_PROVIDER` selects the model provider profile.
- `AGENT_PLUGINS` lists optional integrations such as `graphify`.

If `.env` is missing, run:

```bash
./install.sh --portable .
```

## Command Workflows

The setup exposes the same high-level workflows across supported harnesses:

- `/spec` -> `rhobar`
- `/refine` -> `milten`
- `/analyze` -> `lester`
- `/implement` -> `gorn`
- `/verify` -> `gomez`
- `/bookskeeper` -> `xardas`

`/refine` ends in `READY` or `NEEDS_INPUT`; `/analyze` ends in `READY` or
`BLOCKED`. `/implement` must delegate review to Lee and repeat remediation,
verification, and review until Lee returns `PASS` or an external blocker is
reported. Verification must include runnable startup/bootstrap evidence when
the change can affect application wiring, configuration, dependencies, or
runtime initialization.

Scout is the cheap, read-only repository evidence agent. Rhobar, Milten,
Lester, and Xardas may delegate bounded discovery to Scout while retaining
responsibility for conclusions. Harnesses differ in how they launch subagents,
but all six command bindings must exist in Codex, Claude Code, and OpenCode and
must preserve these contracts.

## Repository Rules

- Read `llms.txt` before changing installer behavior, generated harness files,
  roles, commands, providers, plugins, or documentation structure.
- Read a target repository's local `AGENTS.md` first when present.
- Treat `core/shared-instructions.md` as the source of truth for behavior shared
  by every role; render it instead of duplicating shared rules in generators.
- Keep generated task documents under `AGENT_ROOT/docs/<project-slug>/`.
- Keep repository-owned guidance in the target repository, such as
  `graphify-out/*` and repo-local `AGENTS.md`.
- Prefer focused file reads and targeted verification over broad dumps.
- Do not modify harness generated files by hand when a template/generator change
  is the correct fix.

## Optional Graph Workflows

Graphify support is optional for general discovery but required by
`/bookskeeper`. When enabled and `graphify-out/graph.json` exists, query it
before broad source exploration. Repository-changing workflows mark
`graphify-out/needs_update` when knowledge may be stale. `/bookskeeper` runs the
cheap `graphify update <repo>` freshness gate for every existing graph, uses the
marker to narrow documentation work, clears it only after a successful refresh,
and performs a deep build only when no graph exists.
