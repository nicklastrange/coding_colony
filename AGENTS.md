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
- `/design` -> `nadia`
- `/implement` -> `gorn`
- `/implement-spike` -> `riordian`
- `/verify` -> `gomez`
- `/bookskeeper` -> `xardas`

Harnesses differ in how they launch subagents. Generated harness files should
use native delegation/configuration where available and fall back to clear
instructions where a harness has no direct equivalent.

## Repository Rules

- Read `llms.txt` before changing installer behavior, generated harness files,
  roles, commands, providers, plugins, or documentation structure.
- Read a target repository's local `AGENTS.md` first when present.
- Keep generated task documents under `AGENT_ROOT/docs/<project-slug>/`.
- Keep repository-owned guidance in the target repository, such as
  `graphify-out/*` and repo-local `AGENTS.md`.
- Prefer focused file reads and targeted verification over broad dumps.
- Do not modify harness generated files by hand when a template/generator change
  is the correct fix.

## Optional Graph Workflows

Graphify support is optional. When the `graphify` plugin is enabled and a target
repository has `graphify-out/graph.json`, use graph queries before broad source
exploration. If Graphify is not installed or no graph exists, fall back to normal
bounded repository inspection.
