# Contributing

Keep the repository source-of-truth small and harness-neutral.

- Put role metadata in `config/roles.json`.
- Put provider tier mappings in `config/providers.json`.
- Put optional integration metadata in `config/plugins.json`.
- Put shared behavioral rules in `core/shared-instructions.md`.
- Update `scripts/agent_setup.py` when generation behavior changes.
- Do not commit generated harness directories or local `.env` files.
- Do not hardcode personal absolute paths.

Before proposing changes, run:

```bash
python3 -m py_compile scripts/agent_setup.py
./install.sh --portable /tmp/agent-v2-oss-smoke --harness codex --no-strict --dry-run
```

