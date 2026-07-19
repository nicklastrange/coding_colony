# Shared Agent Instructions

Use these rules in every generated harness unless a harness-specific mechanism is
more precise.

- Resolve the target repository explicitly and read its `AGENTS.md` first.
- Resolve `ROOT_DIR`, `AGENT_ROOT`, commands, and machine-specific values from
  generated runtime configuration. Never hardcode local absolute paths.
- Use launcher-provided `AGENT_PROJECT_SLUG` and `AGENT_PROJECT_DOCS` for central
  task artifacts. Derive a fallback only when those values are unavailable.
- Do not edit or remove the `.coding-colony-project.json` identity marker in a
  central project-doc directory.
- Before graph use, check both `graphify-out/graph.json` and
  `graphify-out/needs_update`. Query the graph only when the plugin is enabled
  and the graph exists; the marker means it is stale.
- A graph is navigation, not source of truth. Never broad-dump raw graph data.
  Verify changed and task-critical facts in live source with exact `path:line`
  evidence, especially when the freshness marker exists.
- Start discovery with harness-native file and search tools. When shell access
  is permitted, prefer focused `rg --files` filters and `rg -n` symbol, caller,
  test, or configuration searches. Read the smallest useful ranges and expand
  only when evidence requires it.
- Keep task artifacts under `AGENT_PROJECT_DOCS` (the matching
  `AGENT_ROOT/docs/<project-slug>/`). Keep
  repository-owned guidance in repo-local `AGENTS.md` and `graphify-out/`.
- Preserve user changes, keep edits surgical, and match existing patterns before
  adding new ones.
- Run the smallest meaningful repository-native check first, then every broader
  check triggered by the change's risk. Report exact commands and results.
