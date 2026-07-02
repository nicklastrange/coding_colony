# Shared Agent Instructions

Use these rules in every generated harness unless a harness-specific mechanism is
more precise.

- Read the target repository's `AGENTS.md` first when it exists.
- Prefer bounded file reads and `rg`/`rg --files` over broad dumps.
- Use optional graph tooling only when the `graphify` plugin is enabled and the
  target repository has `graphify-out/graph.json`.
- Keep changes surgical. Do not refactor unrelated code.
- Match existing style before introducing new patterns.
- Run the smallest meaningful verification first, then broader checks when risk
  requires it.
- Keep generated task docs under `AGENT_ROOT/docs/<project-slug>/`.
- Never hardcode local absolute paths; read paths from `.env` or generated
  harness configuration.

