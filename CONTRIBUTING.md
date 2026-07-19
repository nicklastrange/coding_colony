# Contributing

Keep the repository source-of-truth small and harness-neutral.

- Put role metadata in `config/roles.json`.
- Put provider tier mappings in `config/providers.json`.
- Put optional integration metadata in `config/plugins.json`.
- Put shared behavioral rules in `core/shared-instructions.md`.
- Keep the six command bindings (`spec`, `refine`, `analyze`, `implement`,
  `verify`, and `bookskeeper`) available in Codex, Claude Code, and OpenCode.
- Update `scripts/agent_setup.py` when generation behavior changes.
- Do not commit generated harness directories or local `.env` files.
- Do not hardcode personal absolute paths.

Before proposing changes, run:

```bash
PYTHONPYCACHEPREFIX=/tmp/coding-colony-pycache python3 -m py_compile scripts/agent_setup.py tests/test_installation_integrity.py
python3 -m unittest discover -s tests -v
./install.sh --portable /tmp/coding-colony-smoke --harness codex --no-strict --dry-run
```
