#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


SUPPORTED_HARNESSES = ("codex", "claude", "opencode")
MODEL_TIERS = ("fast", "balanced", "deep")
DEFAULT_PLUGINS: tuple[str, ...] = ()
NATIVE_PROVIDER_BY_HARNESS = {
    "codex": "codex-native",
    "claude": "anthropic-native",
    "opencode": "opencode-native",
}
COMMAND_TO_ROLE = {
    "spec": "rhobar",
    "refine": "milten",
    "analyze": "lester",
    "implement": "gorn",
    "verify": "gomez",
    "bookskeeper": "xardas",
}
ROLE_ORDER = (
    "scout",
    "rhobar",
    "milten",
    "lester",
    "gorn",
    "lee",
    "gomez",
    "xardas",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_coding_colony_config(config: dict, roles: dict) -> None:
    if set(config) != {"models", "agents"}:
        raise SystemExit("coding-colony.json must contain only `models` and `agents`")
    if not isinstance(config["models"], dict) or not isinstance(config["agents"], dict):
        raise SystemExit("coding-colony.json `models` and `agents` must be objects")
    for harness, models in config["models"].items():
        if harness not in SUPPORTED_HARNESSES:
            raise SystemExit(f"coding-colony.json has unknown harness: {harness}")
        if not isinstance(models, dict) or set(models) != {"default", *MODEL_TIERS}:
            raise SystemExit(
                f"coding-colony.json models.{harness} must contain default, fast, balanced, and deep"
            )
        if any(not isinstance(value, str) or not value.strip() for value in models.values()):
            raise SystemExit(f"coding-colony.json models.{harness} values must be non-empty strings")
    for role_name, override in config["agents"].items():
        if role_name not in roles:
            raise SystemExit(f"coding-colony.json has unknown agent: {role_name}")
        if not isinstance(override, dict) or set(override) != {"model", "reasoning"}:
            raise SystemExit(
                f"coding-colony.json agents.{role_name} must contain only model and reasoning"
            )
        if override["model"] not in MODEL_TIERS:
            raise SystemExit(
                f"coding-colony.json agents.{role_name}.model must be fast, balanced, or deep"
            )
        if not isinstance(override["reasoning"], str) or not override["reasoning"].strip():
            raise SystemExit(
                f"coding-colony.json agents.{role_name}.reasoning must be a non-empty string"
            )


def legacy_harness_models(
    agent_root: Path,
    harness: str,
    provider: dict,
    shared_env: dict[str, str],
    single_harness: bool,
) -> dict[str, str]:
    models = {"default": default_model_for_provider(provider), **model_tiers_for_provider(provider)}
    legacy = dict(shared_env) if single_harness else {}
    legacy.update(parse_env(agent_root / f"{harness}.env"))
    for name in ("default", *MODEL_TIERS):
        value = legacy.get(f"AGENT_MODEL_{name.upper()}")
        if value:
            models[name] = value
    return models


def load_coding_colony_config(
    agent_root: Path,
    harnesses: list[str],
    explicit_provider: str | None,
    providers: dict,
    roles: dict,
    shared_env: dict[str, str],
    dry_run: bool,
) -> dict:
    path = agent_root / "coding-colony.json"
    if path.exists():
        try:
            config = read_json(path)
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(f"Invalid coding-colony.json: {error}") from error
        if not isinstance(config, dict):
            raise SystemExit("coding-colony.json must contain a JSON object")
    else:
        config = {}
    original = json.dumps(config, sort_keys=True)
    models = config.setdefault("models", {})
    agents = config.setdefault("agents", {})
    if not isinstance(models, dict) or not isinstance(agents, dict):
        raise SystemExit("coding-colony.json `models` and `agents` must be objects")
    for harness in harnesses:
        provider = providers[provider_for_harness(harness, explicit_provider)]
        defaults = legacy_harness_models(
            agent_root,
            harness,
            provider,
            shared_env,
            len(harnesses) == 1,
        )
        harness_models = models.setdefault(harness, {})
        if not isinstance(harness_models, dict):
            raise SystemExit(f"coding-colony.json models.{harness} must be an object")
        for name, value in defaults.items():
            harness_models.setdefault(name, value)
    for role_name, role in roles.items():
        override = agents.setdefault(role_name, {})
        if not isinstance(override, dict):
            raise SystemExit(f"coding-colony.json agents.{role_name} must be an object")
        override.setdefault("model", role["tier"])
        override.setdefault("reasoning", role["effort"])
    validate_coding_colony_config(config, roles)
    if not path.exists() or json.dumps(config, sort_keys=True) != original:
        write_file(path, json.dumps(config, indent=2) + "\n", dry_run)
    return config


def configured_roles(roles: dict, config: dict) -> dict:
    return {
        name: {
            **role,
            "tier": config["agents"][name]["model"],
            "effort": config["agents"][name]["reasoning"],
        }
        for name, role in roles.items()
    }


def split_csv(values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in value.split(",") if part.strip())
    return result


def toml_string(value: str) -> str:
    return json.dumps(value)


def toml_multiline(value: str) -> str:
    return '"""' + value.replace('"""', '\\"\\"\\"') + '"""'


def mkdir(path: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"mkdir -p {path}")
        return
    path.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, content: str, dry_run: bool, mode: int | None = None) -> None:
    if dry_run:
        print(f"write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def remove_path(path: Path, dry_run: bool) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if dry_run:
        print(f"remove {path}")
    elif path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except FileNotFoundError:
        return False


def copy_file(src: Path, dst: Path, dry_run: bool, mode: int | None = None) -> None:
    if same_path(src, dst):
        return
    if dry_run:
        print(f"copy {src} -> {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if mode is not None:
        dst.chmod(mode)


def copy_tree(src: Path, dst: Path, dry_run: bool) -> None:
    if same_path(src, dst):
        return
    if dry_run:
        print(f"copy {src} -> {dst}")
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def parse_env_content(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def parse_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return parse_env_content(path.read_text(encoding="utf-8"))


def env_content(
    agent_root: Path,
    root_dir: Path,
    harnesses: list[str],
    provider: str,
    plugins: list[str],
    optional_deps: dict[str, dict[str, str]],
    existing_env: dict[str, str],
) -> str:
    example = (repo_root() / ".env.example").read_text(encoding="utf-8")
    defaults = {
        "ROOT_DIR": str(root_dir),
        "AGENT_ROOT": str(agent_root),
        "AGENT_HARNESSES": ",".join(harnesses),
        "AGENT_PROVIDER": provider,
        "AGENT_PLUGINS": ",".join(plugins),
        "AGENT_OPTIONAL_DEPS": serialize_optional_deps(optional_deps),
        "AGENT_DETECTED_TOOLS": serialize_detected_tools(optional_deps),
        "AGENT_PLUGIN_INSTALLS": serialize_plugin_installs(optional_deps),
    }
    lines: list[str] = []
    seen: set[str] = set()
    for raw in example.splitlines():
        if "=" not in raw or raw.strip().startswith("#"):
            lines.append(raw)
            continue
        key, _ = raw.split("=", 1)
        if key in defaults:
            lines.append(f"{key}={defaults[key]}")
        elif key in existing_env:
            lines.append(f"{key}={existing_env[key]}")
        else:
            lines.append(raw)
        seen.add(key)
    for key, value in defaults.items():
        if key not in seen:
            lines.append(f"{key}={value}")
            seen.add(key)
    for key, value in existing_env.items():
        if key not in seen and not key.startswith("AGENT_MODEL_"):
            lines.append(f"{key}={value}")
    return "\n".join(lines).rstrip() + "\n"


def tier_model(provider: dict, role: dict) -> str:
    return provider["tiers"][role["tier"]]


def tier_env_name(tier: str) -> str:
    return f"AGENT_MODEL_{tier.upper()}"


def model_tiers_for_provider(provider: dict) -> dict[str, str]:
    return dict(provider["tiers"])


def default_model_for_provider(provider: dict) -> str:
    return provider.get("default_model", provider["tiers"]["balanced"])


def read_role_workflows() -> dict[str, str]:
    path = repo_root() / "core" / "role-workflows.md"
    text = path.read_text(encoding="utf-8")
    workflows: dict[str, str] = {}
    current_role: str | None = None
    current_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("<!-- role:") and line.endswith("-->"):
            if current_role:
                workflows[current_role] = "\n".join(current_lines).strip() + "\n"
            current_role = line.removeprefix("<!-- role:").removesuffix("-->").strip()
            current_lines = []
            continue
        if line == "<!-- /role -->":
            if current_role:
                workflows[current_role] = "\n".join(current_lines).strip() + "\n"
            current_role = None
            current_lines = []
            continue
        if current_role:
            current_lines.append(raw)
    if current_role:
        workflows[current_role] = "\n".join(current_lines).strip() + "\n"
    return workflows


def role_prompt(role_name: str, role: dict, plugins: list[str], workflows: dict[str, str]) -> str:
    workflow = workflows.get(role_name)
    if not workflow:
        raise SystemExit(f"Missing workflow for role: {role_name}")
    enabled_plugins = ", ".join(plugins) if plugins else "none"
    graph_line = (
        "Graphify is enabled: use it where the role workflow asks for graph-backed discovery or documentation."
        if "graphify" in plugins
        else "Graphify is optional and not enabled for this install; if a workflow requires graphify, report the missing optional dependency instead of fabricating graph-backed output."
    )
    allowed_children = {
        "rhobar": "scout",
        "milten": "scout",
        "lester": "scout",
        "gorn": "lee",
        "xardas": "scout",
    }.get(role_name, "none")
    delegation_boundary = f"""Delegation boundary:
This is a child-role invocation. Never spawn another {role_name} agent or invoke
the same role workflow recursively. Only spawn the explicitly allowed child role
{allowed_children} when the workflow requires it; otherwise do not spawn children."""
    shared_instructions = (repo_root() / "core" / "shared-instructions.md").read_text(encoding="utf-8").strip()
    return f"""You are {role_name}, {role['description']}

Primary responsibility: {role['summary']}

Install context:
- Enabled optional plugins: {enabled_plugins}
- {graph_line}

{shared_instructions}

{delegation_boundary}

Role workflow:
{workflow}
"""


def command_body(command: str, role: str) -> str:
    return f"""# /{command}

Run the `{role}` role workflow for this command.

Repository or task arguments: $ARGUMENTS
"""


def codex_skill_content(command: str, role: str) -> str:
    if role == "gorn":
        delegation_contract = """Delegate to exactly one `gorn` custom agent. Call `spawn_agent` exactly once with
`agent_type="gorn"` and pass the user's full request plus `$ARGUMENTS`. The
canonical `gorn` role workflow owns implementation, its mandatory `lee` review/remediation loop,
and verification.
The spawned gorn must not spawn another gorn or invoke /implement recursively.
Wait for `gorn` and report its result; do not inspect, edit, verify, or duplicate
its work. If native delegation is unavailable, report that and stop."""
    else:
        child_contract = (
            f"The spawned `{role}` agent may spawn at most one `scout` child for bounded, read-only discovery; no other children."
            if role in {"rhobar", "milten", "lester", "xardas"}
            else f"The spawned `{role}` agent is a leaf executor and must not spawn children."
        )
        delegation_contract = f"""Delegate to the `{role}` custom agent. Call `spawn_agent` exactly once with
`agent_type="{role}"` and pass the user's full request plus `$ARGUMENTS`. The
canonical `{role}` role workflow owns the task.
{child_contract} Wait for `{role}` and report its result; do not inspect, edit,
verify, or duplicate its work. If native delegation is unavailable, report that
and stop."""
    return f"""---
name: {command}
description: Run /{command} through the {role} role workflow.
---

{delegation_contract}
"""


def claude_skill_content(command: str, role: str) -> str:
    return f"""---
name: {command}
description: Run /{command} through the {role} role workflow.
context: fork
agent: {role}
disable-model-invocation: true
---

Run the canonical `{role}` workflow for this task:

$ARGUMENTS
"""


def opencode_command_content(command: str, role: str) -> str:
    return f"""---
description: Run /{command} through the {role} role workflow.
agent: {role}
subtask: true
---

{command_body(command, role)}
"""


def copy_development_skills(destination: Path, dry_run: bool) -> None:
    for source in sorted((repo_root() / "skills").iterdir()):
        if source.is_dir():
            copy_tree(source, destination / source.name, dry_run)


def detect_harness_binary(harness: str) -> bool:
    binary = {"codex": "codex", "claude": "claude", "opencode": "opencode"}[harness]
    return shutil.which(binary) is not None


def detect_plugin(plugin_name: str, plugin_def: dict) -> dict[str, str]:
    command_env = plugin_def.get("command_env")
    if not command_env:
        return {"availability": "builtin", "path": ""}
    command = plugin_def.get("default_command") or command_env_to_default(command_env)
    path = shutil.which(command) or ""
    return {"availability": "available" if path else "missing", "path": path, "command": command}


def command_env_to_default(command_env: str) -> str:
    return {
        "GRAPHIFY_COMMAND": "graphify",
        "CONTEXT_MODE_COMMAND": "context-mode",
        "PLAYWRIGHT_MCP_COMMAND": "playwright-mcp",
    }.get(command_env, command_env.lower())


def serialize_optional_deps(optional_deps: dict[str, dict[str, str]]) -> str:
    parts: list[str] = []
    for name in sorted(optional_deps):
        info = optional_deps[name]
        value = f"{name}={info['state']}:{info['availability']}"
        if info.get("path"):
            value += f":{info['path']}"
        parts.append(value)
    return ",".join(parts)


def serialize_detected_tools(optional_deps: dict[str, dict[str, str]]) -> str:
    parts: list[str] = []
    for name in sorted(optional_deps):
        path = optional_deps[name].get("path")
        if path:
            parts.append(f"{name}={path}")
    return ",".join(parts)


def serialize_plugin_installs(optional_deps: dict[str, dict[str, str]]) -> str:
    parts: list[str] = []
    for name in sorted(optional_deps):
        state = optional_deps[name].get("install_state")
        if state and state != "not-needed":
            parts.append(f"{name}={state}")
        configure_state = optional_deps[name].get("configure_state")
        if configure_state and configure_state != "not-needed":
            parts.append(f"{name}.configure={configure_state}")
    return ",".join(parts)


def prompt_yes_no(question: str, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = input(f"{question} {suffix} ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer yes or no.")


def shell_startup_file() -> Path:
    home = Path.home()
    shell = Path(os.environ.get("SHELL", "")).name
    if shell == "zsh":
        return Path(os.environ.get("ZDOTDIR", str(home))).expanduser() / ".zshrc"
    if shell == "bash":
        return home / (".bash_profile" if sys.platform == "darwin" else ".bashrc")
    return home / ".profile"


def add_coding_colony_to_path(agent_root: Path, startup_file: Path, dry_run: bool = False) -> None:
    bin_dir = (agent_root / ".config" / "bin").resolve()
    if str(bin_dir) in os.environ.get("PATH", "").split(os.pathsep):
        print(f"coding-colony is already on PATH: {bin_dir}")
        return

    marker = "# Added by Coding Colony"
    legacy_marker = "# Added by agent-v2: coding-colony"
    export_line = f"export PATH={shlex.quote(str(bin_dir))}:$PATH"
    existing = startup_file.read_text(encoding="utf-8") if startup_file.exists() else ""
    if marker in existing or legacy_marker in existing or export_line in existing:
        print(f"coding-colony PATH entry already exists in {startup_file}")
        return
    if dry_run:
        print(f"append to {startup_file}: {export_line}")
        return

    startup_file.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if not existing or existing.endswith("\n") else "\n"
    startup_file.write_text(
        f"{existing}{separator}{marker}\n{export_line}\n",
        encoding="utf-8",
    )
    print(f"Added coding-colony to PATH in {startup_file}")


def maybe_add_coding_colony_to_path(agent_root: Path) -> None:
    startup_file = shell_startup_file()
    bin_dir = (agent_root / ".config" / "bin").resolve()
    if str(bin_dir) in os.environ.get("PATH", "").split(os.pathsep):
        print(f"coding-colony is already on PATH: {bin_dir}")
        return
    if prompt_yes_no(f"Add coding-colony to PATH in {startup_file}?", True):
        add_coding_colony_to_path(agent_root, startup_file)
    else:
        print(f"Add it manually with: export PATH={shlex.quote(str(bin_dir))}:$PATH")


def install_command_text(plugin_def: dict) -> str:
    commands = plugin_def.get("install_commands")
    if commands:
        return " or ".join(shlex.join(command) for command in commands)
    command = plugin_def.get("install_command")
    if command:
        return shlex.join(command)
    return ""


def install_command_candidates(plugin_def: dict) -> list[list[str]]:
    commands = plugin_def.get("install_commands")
    if commands:
        return [list(command) for command in commands]
    command = plugin_def.get("install_command")
    if command:
        return [list(command)]
    return []


def choose_install_command(plugin_def: dict, dry_run: bool) -> tuple[list[str], str]:
    candidates = install_command_candidates(plugin_def)
    if not candidates:
        return [], "unsupported"
    for command in candidates:
        if dry_run or shutil.which(command[0]):
            return command, "available"
    return candidates[0], "installer-missing"


def install_plugin(plugin_name: str, plugin_def: dict, dry_run: bool) -> str:
    command, command_state = choose_install_command(plugin_def, dry_run)
    if not command:
        print(f"warning: plugin `{plugin_name}` has no install command", file=sys.stderr)
        return "unsupported"
    print(f"Installing optional plugin `{plugin_name}` with: {shlex.join(command)}")
    if dry_run:
        return "dry-run"
    if command_state == "installer-missing":
        installers = ", ".join(command[0] for command in install_command_candidates(plugin_def))
        print(f"warning: no installer command found for plugin `{plugin_name}`; tried: {installers}", file=sys.stderr)
        return "installer-missing"
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        print(f"warning: failed to install plugin `{plugin_name}` (exit {error.returncode})", file=sys.stderr)
        return "failed"
    return "installed"


def render_plugin_command(command: list[str], platform: str) -> list[str]:
    return [part.replace("{platform}", platform) for part in command]


def configure_plugin_for_harnesses(
    plugin_name: str,
    plugin_def: dict,
    harnesses: list[str],
    agent_root: Path,
    dry_run: bool,
) -> str:
    command_template = plugin_def.get("post_install_command")
    if not command_template:
        return "not-needed"

    configured: list[str] = []
    for harness in harnesses:
        command = render_plugin_command(list(command_template), harness)
        print(f"Configuring optional plugin `{plugin_name}` for {harness} with: {shlex.join(command)}")
        if dry_run:
            configured.append(harness)
            continue
        if not shutil.which(command[0]):
            print(f"warning: command `{command[0]}` not found while configuring plugin `{plugin_name}`", file=sys.stderr)
            return "command-missing"
        try:
            environment = dict(os.environ)
            environment.update({
                "CODEX_HOME": str(agent_root / ".codex"),
                "CLAUDE_CONFIG_DIR": str(agent_root / ".claude"),
                "OPENCODE_CONFIG_DIR": str(agent_root / ".opencode"),
            })
            subprocess.run(command, check=True, env=environment, cwd=agent_root)
        except subprocess.CalledProcessError as error:
            print(f"warning: failed to configure plugin `{plugin_name}` for {harness} (exit {error.returncode})", file=sys.stderr)
            return f"failed:{harness}"
        configured.append(harness)

    return "configured:" + "+".join(configured) if configured else "not-needed"


def configure_selected_plugins(
    plugins: list[str],
    plugin_defs: dict,
    optional_deps: dict[str, dict[str, str]],
    harnesses: list[str],
    agent_root: Path,
    dry_run: bool,
) -> None:
    for plugin_name in plugins:
        if optional_deps.get(plugin_name, {}).get("availability") == "missing":
            optional_deps.setdefault(plugin_name, {})["configure_state"] = "skipped:missing"
            continue
        plugin_def = plugin_defs[plugin_name]
        state = configure_plugin_for_harnesses(plugin_name, plugin_def, harnesses, agent_root, dry_run)
        optional_deps.setdefault(plugin_name, {})["configure_state"] = state
        if state.startswith("failed:") or state == "command-missing":
            raise SystemExit(f"Failed to configure optional plugin `{plugin_name}` ({state})")


def maybe_install_plugin(
    plugin_name: str,
    plugin_def: dict,
    detection: dict[str, str],
    *,
    install_missing_plugins: bool,
    prompt_for_install: bool,
    dry_run: bool,
) -> tuple[dict[str, str], str]:
    if detection["availability"] != "missing":
        return detection, "not-needed"

    command_text = install_command_text(plugin_def)
    if not command_text:
        return detection, "unsupported"

    should_install = install_missing_plugins
    if not should_install and prompt_for_install:
        description = plugin_def.get("install_description") or f"Run `{command_text}`."
        should_install = prompt_yes_no(
            f"Install missing optional dependency for `{plugin_name}`? {description} Command: `{command_text}`",
            False,
        )
    if not should_install:
        return detection, "skipped"

    install_state = install_plugin(plugin_name, plugin_def, dry_run)
    if install_state in {"installed", "dry-run"}:
        detection = detect_plugin(plugin_name, plugin_def)
    return detection, install_state


def select_plugins(
    requested_plugins: list[str],
    plugin_defs: dict,
    prompt_for_plugins: bool,
    install_missing_plugins: bool,
    prompt_for_install: bool,
    dry_run: bool,
) -> tuple[list[str], dict[str, dict[str, str]]]:
    unknown_plugins = [plugin for plugin in requested_plugins if plugin not in plugin_defs]
    if unknown_plugins:
        raise SystemExit(f"Unknown plugin(s): {', '.join(unknown_plugins)}")

    optional_deps: dict[str, dict[str, str]] = {}
    selected = set(requested_plugins)

    for plugin_name, plugin_def in plugin_defs.items():
        detection = detect_plugin(plugin_name, plugin_def)
        enabled = plugin_name in selected
        install_state = "not-needed"
        if not requested_plugins and prompt_for_plugins:
            availability = detection["availability"]
            if availability == "available":
                detail = f"detected at {detection['path']}"
                default = True
            elif availability == "builtin":
                detail = "built in"
                default = False
            else:
                install_text = install_command_text(plugin_def)
                install_hint = f"; can install with `{install_text}`" if install_text else "; no install command configured"
                detail = f"command `{detection.get('command', plugin_name)}` not found{install_hint}"
                default = False
            enabled = prompt_yes_no(f"Enable optional plugin `{plugin_name}` ({detail})?", default)
            if enabled:
                selected.add(plugin_name)

        if enabled and detection["availability"] == "missing":
            detection, install_state = maybe_install_plugin(
                plugin_name,
                plugin_def,
                detection,
                install_missing_plugins=install_missing_plugins,
                prompt_for_install=prompt_for_install,
                dry_run=dry_run,
            )
            if (
                not requested_plugins
                and prompt_for_plugins
                and detection["availability"] == "missing"
                and install_state in {"skipped", "failed", "installer-missing", "unsupported"}
            ):
                enabled = False
                selected.discard(plugin_name)
            if install_missing_plugins and detection["availability"] == "missing" and not dry_run:
                raise SystemExit(f"Failed to install optional plugin `{plugin_name}` ({install_state})")

        optional_deps[plugin_name] = {
            "state": "enabled" if enabled else "disabled",
            "availability": detection["availability"],
            "path": detection.get("path", ""),
            "install_state": install_state,
        }

    return [plugin for plugin in plugin_defs if plugin in selected], optional_deps


def validate_harnesses(harnesses: list[str], explicit: bool, no_strict: bool) -> list[str]:
    strict = explicit and not no_strict
    available: list[str] = []
    for harness in harnesses:
        if harness not in SUPPORTED_HARNESSES:
            raise SystemExit(f"Unsupported harness: {harness}")
        if detect_harness_binary(harness):
            available.append(harness)
            continue
        message = f"Harness binary not found for {harness}"
        if strict:
            raise SystemExit(message + " (strict mode is default when --harness is specified)")
        print("warning:", message, file=sys.stderr)
        if explicit:
            available.append(harness)
    if not explicit and not available:
        print("warning: no supported harness binaries found; generated base files only", file=sys.stderr)
    return available


def mcp_servers(plugins: list[str], env: dict[str, str]) -> dict:
    servers: dict[str, dict] = {}
    if "context-mode" in plugins:
        servers["context-mode"] = {
            "type": "stdio",
            "command": env.get("CONTEXT_MODE_COMMAND", "context-mode"),
        }
    if "playwright" in plugins:
        servers["playwright"] = {
            "type": "stdio",
            "command": env.get("PLAYWRIGHT_MCP_COMMAND", "playwright-mcp"),
        }
    return servers


def render_agents_md() -> str:
    return (repo_root() / "AGENTS.md").read_text(encoding="utf-8")


def provider_label(harnesses: list[str], explicit_provider: str | None) -> str:
    if explicit_provider:
        return explicit_provider
    native_profiles = {NATIVE_PROVIDER_BY_HARNESS[harness] for harness in harnesses}
    if len(native_profiles) == 1:
        return next(iter(native_profiles))
    return "native"


def provider_for_harness(harness: str, explicit_provider: str | None) -> str:
    return explicit_provider or NATIVE_PROVIDER_BY_HARNESS[harness]


def validate_provider_harnesses(provider_name: str | None, harnesses: list[str], providers: dict) -> None:
    if not provider_name:
        return
    if provider_name not in providers:
        raise SystemExit(f"Unknown provider profile: {provider_name}")
    supported = providers[provider_name]["supported_harnesses"]
    unsupported = [harness for harness in harnesses if harness not in supported]
    if unsupported:
        raise SystemExit(
            f"Provider profile `{provider_name}` does not support harness(es): {', '.join(unsupported)}. "
            f"Supported harnesses: {', '.join(supported)}"
        )


def generate_base(
    agent_root: Path,
    root_dir: Path,
    harnesses: list[str],
    provider: str,
    plugins: list[str],
    optional_deps: dict[str, dict[str, str]],
    existing_env: dict[str, str],
    dry_run: bool,
) -> None:
    write_file(
        agent_root / ".env",
        env_content(agent_root, root_dir, harnesses, provider, plugins, optional_deps, existing_env),
        dry_run,
        0o600,
    )
    write_file(agent_root / ".envrc", envrc_content(), dry_run)
    write_file(agent_root / "AGENTS.md", render_agents_md(), dry_run)
    mkdir(agent_root / "docs", dry_run)
    write_file(
        agent_root / ".config" / "install-manifest.json",
        json.dumps({
            "installer": "coding-colony",
            "source": str(repo_root()),
            "root_dir": str(root_dir),
            "agent_root": str(agent_root),
            "harnesses": harnesses,
            "provider": provider,
            "plugins": plugins,
            "optional_deps": optional_deps,
        }, indent=2) + "\n",
        dry_run,
    )
    if "gradle-wrapper" in plugins:
        copy_file(
            repo_root() / "scripts" / "run-gradle-summarized.sh",
            agent_root / ".config" / "bin" / "run-gradle-summarized.sh",
            dry_run,
            0o755,
        )
    write_file(
        agent_root / ".config" / "bin" / "coding-colony",
        CODING_COLONY_CLI.replace("__ROLE_NAMES_JSON__", json.dumps(list(ROLE_ORDER))),
        dry_run,
        0o755,
    )


def envrc_content() -> str:
    return """# Generated by Coding Colony.
# Run `direnv allow` once in this directory if you want harnesses that support
# environment substitution to read .env values automatically.
dotenv_if_exists .env
"""


def generate_codex(agent_root: Path, provider: dict, roles: dict, plugins: list[str], workflows: dict[str, str], env: dict[str, str], dry_run: bool) -> None:
    codex_dir = agent_root / ".codex"
    mkdir(codex_dir / "agents", dry_run)
    config_lines = [
        "# Generated by Coding Colony. Re-run install.sh instead of editing by hand.",
        f"model = {toml_string(env.get('AGENT_MODEL_DEFAULT', provider.get('default_model', provider['tiers']['balanced'])))}",
        'model_reasoning_effort = "medium"',
    ]
    codex_provider = provider.get("codex_provider")
    provider_bridge = None
    if codex_provider:
        provider_id = f"coding_colony_{codex_provider['id']}"
        base_url = (
            env.get(provider.get("base_url_env", ""), "")
            or provider.get("default_base_url", "")
            or "${" + provider.get("base_url_env", "PROVIDER_BASE_URL") + "}"
        )
        provider_bridge = {
            "id": provider_id,
            "name": codex_provider["name"],
            "base_url": base_url,
            "env_key": provider.get("api_key_env", "PROVIDER_API_KEY"),
            "wire_api": codex_provider.get("wire_api", "responses"),
        }
        config_lines.extend([
            f"model_provider = {toml_string(provider_id)}",
            "",
            f"[model_providers.{provider_id}]",
            f"name = {toml_string(codex_provider['name'])}",
            f"base_url = {toml_string(base_url)}",
            f"env_key = {toml_string(provider.get('api_key_env', 'PROVIDER_API_KEY'))}",
            f"wire_api = {toml_string(codex_provider.get('wire_api', 'responses'))}",
        ])
    config_lines.extend([
        "",
        "[features]",
        "hooks = true",
        "multi_agent = true",
        "",
        "[agents]",
        "max_threads = 3",
        "max_depth = 2",
    ])
    codex_mcp_servers = mcp_servers(plugins, env)
    for name, server in codex_mcp_servers.items():
        config_lines.extend(["", f"[mcp_servers.{name}]", f"command = {toml_string(server['command'])}"])
    write_file(codex_dir / "config.toml", "\n".join(config_lines) + "\n", dry_run)
    write_file(
        codex_dir / "bridge.json",
        json.dumps({
            "agents": {role_name: roles[role_name]["description"] for role_name in ROLE_ORDER},
            "mcp_servers": codex_mcp_servers,
        }, indent=2) + "\n",
        dry_run,
    )
    write_file(codex_dir / "AGENTS.md", render_agents_md(), dry_run)

    for role_name in ROLE_ORDER:
        role = roles[role_name]
        role_provider = (
            provider_bridge["id"]
            if provider_bridge
            else provider.get("harness_defaults", {}).get("codex", {}).get("provider_id")
        )
        role_lines = [
            f"name = {toml_string(role_name)}",
            f"description = {toml_string(role['description'])}",
            f"model = {toml_string(env.get(tier_env_name(role['tier']), provider['tiers'][role['tier']]))}",
            f"model_reasoning_effort = {toml_string(role['effort'])}",
            f"sandbox_mode = {toml_string(role['sandbox'])}",
        ]
        if role_provider:
            role_lines.append(f"model_provider = {toml_string(role_provider)}")
        role_lines.extend([
            "",
            f"developer_instructions = {toml_multiline(role_prompt(role_name, role, plugins, workflows))}",
        ])
        if provider_bridge:
            role_lines.extend([
                "",
                f"[model_providers.{provider_bridge['id']}]",
                f"name = {toml_string(provider_bridge['name'])}",
                f"base_url = {toml_string(provider_bridge['base_url'])}",
                f"env_key = {toml_string(provider_bridge['env_key'])}",
                f"wire_api = {toml_string(provider_bridge['wire_api'])}",
            ])
        content = "\n".join([*role_lines, ""])
        write_file(codex_dir / "agents" / f"{role_name}.toml", content, dry_run)

    hooks = {
        "hooks": {
            "SessionStart": [{
                "matcher": "startup|resume|clear|compact",
                "hooks": [{
                    "type": "command",
                    "command": "/usr/bin/python3 \"$AGENT_ROOT/.codex/hooks/session_context.py\"",
                    "statusMessage": "Loading generated agent context"
                }]
            }]
        }
    }
    if "gradle-wrapper" in plugins:
        hooks["hooks"]["PreToolUse"] = [{
            "matcher": "Bash",
            "hooks": [{
                "type": "command",
                "command": "/usr/bin/python3 \"$AGENT_ROOT/.codex/hooks/pre_tool_use_policy.py\"",
                "statusMessage": "Checking shell command"
            }]
        }]
    write_file(codex_dir / "hooks.json", json.dumps(hooks, indent=2) + "\n", dry_run)
    write_file(
        codex_dir / "hooks" / "session_context.py",
        SESSION_CONTEXT_PY,
        dry_run,
        0o755,
    )
    if "gradle-wrapper" in plugins:
        write_file(codex_dir / "hooks" / "pre_tool_use_policy.py", PRE_TOOL_USE_POLICY_PY, dry_run, 0o755)

    skills_dir = codex_dir / "skills"
    for command, role in COMMAND_TO_ROLE.items():
        write_file(skills_dir / command / "SKILL.md", codex_skill_content(command, role), dry_run)
    copy_development_skills(skills_dir, dry_run)


def generate_claude(agent_root: Path, provider: dict, roles: dict, plugins: list[str], workflows: dict[str, str], env: dict[str, str], dry_run: bool) -> None:
    claude_dir = agent_root / ".claude"
    mkdir(claude_dir / "agents", dry_run)
    for role_name in ROLE_ORDER:
        role = roles[role_name]
        frontmatter = [
            "---",
            f"name: {role_name}",
            f"description: {role['description']}",
            f"model: {json.dumps(env.get(tier_env_name(role['tier']), tier_model(provider, role)))}",
            f"effort: {json.dumps(role['effort'])}",
            f"x-agent-tier: {role['tier']}",
        ]
        if role["sandbox"] == "read-only":
            frontmatter.extend(["permissionMode: plan", "disallowedTools: Write, Edit"])
        content = "\n".join([
            *frontmatter,
            "---",
            "",
            role_prompt(role_name, role, plugins, workflows),
        ])
        write_file(claude_dir / "agents" / f"{role_name}.md", content, dry_run)
    for command, role in COMMAND_TO_ROLE.items():
        write_file(
            claude_dir / "skills" / command / "SKILL.md",
            claude_skill_content(command, role),
            dry_run,
        )
    copy_development_skills(claude_dir / "skills", dry_run)
    settings = {
        "model": env.get("AGENT_MODEL_DEFAULT", default_model_for_provider(provider)),
        "permissions": {
            "allow": ["Bash(rg:*)", "Bash(sed:*)", "Bash(find:*)", "Bash(git status:*)"],
            "deny": ["Bash(git reset --hard:*)", "Bash(git checkout --:*)"]
        }
    }
    write_file(claude_dir / "settings.json", json.dumps(settings, indent=2) + "\n", dry_run)
    write_file(claude_dir / "CLAUDE.md", "Read the target repository's AGENTS.md first.\n", dry_run)
    write_file(agent_root / ".mcp.json", json.dumps({"mcpServers": mcp_servers(plugins, env)}, indent=2) + "\n", dry_run)


def generate_opencode(agent_root: Path, provider: dict, roles: dict, plugins: list[str], workflows: dict[str, str], env: dict[str, str], dry_run: bool) -> None:
    opencode_dir = agent_root / ".opencode"
    mkdir(opencode_dir / "agents", dry_run)
    mkdir(opencode_dir / "commands", dry_run)
    for role_name in ROLE_ORDER:
        role = roles[role_name]
        child = "scout" if role_name in {"rhobar", "milten", "lester", "xardas"} else "lee" if role_name == "gorn" else None
        permissions = ["permission:"]
        if role["sandbox"] == "read-only":
            permissions.extend(["  edit: deny", "  bash: deny"])
        permissions.extend(["  task:", '    "*": deny'])
        if child:
            permissions.append(f"    {child}: allow")
        content = "\n".join([
            "---",
            f"description: {role['description']}",
            f"model: {json.dumps(env[tier_env_name(role['tier'])])}",
            f"variant: {json.dumps(role['effort'])}",
            f"x-agent-tier: {role['tier']}",
            "mode: subagent",
            *permissions,
            "---",
            "",
            role_prompt(role_name, role, plugins, workflows),
        ])
        write_file(opencode_dir / "agents" / f"{role_name}.md", content, dry_run)
    for command, role in COMMAND_TO_ROLE.items():
        write_file(
            opencode_dir / "commands" / f"{command}.md",
            opencode_command_content(command, role),
            dry_run,
        )
    copy_development_skills(opencode_dir / "skills", dry_run)
    config = {
        "$schema": "https://opencode.ai/config.json",
        "model": env.get("AGENT_MODEL_DEFAULT", provider.get("default_model", provider["tiers"]["balanced"])),
        "mcp": {
            name: {"type": "local", "command": [server["command"]]}
            for name, server in mcp_servers(plugins, env).items()
        },
        "plugin": [],
    }
    if "graphify" in plugins:
        config["plugin"].append("./plugins/graphify.js")
        write_file(opencode_dir / "plugins" / "graphify.js", OPENCODE_GRAPHIFY_JS, dry_run)
    if "gradle-wrapper" in plugins:
        config["plugin"].append("./plugins/gradle-wrapper-redirect.js")
        write_file(opencode_dir / "plugins" / "gradle-wrapper-redirect.js", OPENCODE_GRADLE_JS, dry_run)
    write_file(opencode_dir / "opencode.json", json.dumps(config, indent=2) + "\n", dry_run)


def generate(
    agent_root: Path,
    root_dir: Path,
    harnesses: list[str],
    explicit_provider: str | None,
    plugins: list[str],
    optional_deps: dict[str, dict[str, str]],
    dry_run: bool,
) -> None:
    providers = read_json(repo_root() / "config" / "providers.json")
    roles = read_json(repo_root() / "config" / "roles.json")
    workflows = read_role_workflows()
    validate_provider_harnesses(explicit_provider, harnesses, providers)
    selected_provider_label = provider_label(harnesses, explicit_provider)
    env = parse_env(agent_root / ".env")
    colony_config = load_coding_colony_config(
        agent_root,
        harnesses,
        explicit_provider,
        providers,
        roles,
        env,
        dry_run,
    )
    roles = configured_roles(roles, colony_config)
    env.update({
        "ROOT_DIR": str(root_dir),
        "AGENT_ROOT": str(agent_root),
        "AGENT_PROVIDER": selected_provider_label,
        "AGENT_HARNESSES": ",".join(harnesses),
        "AGENT_PLUGINS": ",".join(plugins),
        "AGENT_OPTIONAL_DEPS": serialize_optional_deps(optional_deps),
        "AGENT_DETECTED_TOOLS": serialize_detected_tools(optional_deps),
        "AGENT_PLUGIN_INSTALLS": serialize_plugin_installs(optional_deps),
    })

    for relative_path in (
        "CLAUDE.md",
        ".codex/agents/nadia.toml",
        ".codex/agents/riordian.toml",
        ".codex/skills/design",
        ".codex/skills/implement-spike",
        ".codex/skills/kotlin-spring-boot",
        ".agents/skills/design",
        ".agents/skills/implement-spike",
        ".claude/agents/nadia.md",
        ".claude/agents/riordian.md",
        ".claude/skills/design",
        ".claude/skills/implement-spike",
        ".claude/skills/kotlin-spring-boot",
        ".opencode/agents/nadia.md",
        ".opencode/agents/riordian.md",
        ".opencode/commands/design.md",
        ".opencode/commands/implement-spike.md",
        ".opencode/skills/kotlin-spring-boot",
        ".opencode/plugins/model-tier-resolver.js",
        ".config/models.json",
        *(f".agents/skills/{command}" for command in COMMAND_TO_ROLE),
    ):
        remove_path(agent_root / relative_path, dry_run)

    if "graphify" not in plugins:
        for relative_path in (
            ".codex/skills/graphify",
            ".claude/skills/graphify",
            ".opencode/skills/graphify",
            ".opencode/plugins/graphify.js",
        ):
            remove_path(agent_root / relative_path, dry_run)

    generate_base(
        agent_root,
        root_dir,
        harnesses,
        selected_provider_label,
        plugins,
        optional_deps,
        env,
        dry_run,
    )
    for harness in harnesses:
        provider_name = provider_for_harness(harness, explicit_provider)
        provider = providers[provider_name]
        harness_env = dict(env)
        harness_models = colony_config["models"][harness]
        harness_env["AGENT_MODEL_DEFAULT"] = harness_models["default"]
        for tier in MODEL_TIERS:
            harness_env[tier_env_name(tier)] = harness_models[tier]
        if harness == "codex":
            generate_codex(agent_root, provider, roles, plugins, workflows, harness_env, dry_run)
        elif harness == "claude":
            generate_claude(agent_root, provider, roles, plugins, workflows, harness_env, dry_run)
        elif harness == "opencode":
            generate_opencode(agent_root, provider, roles, plugins, workflows, harness_env, dry_run)


def resolve_install(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.global_install:
        preferred = Path.home() / ".coding-colony"
        legacy = Path.home() / ".agent-v2"
        agent_root = legacy if legacy.exists() and not preferred.exists() else preferred
        root_dir = Path(args.root_dir).expanduser().resolve() if args.root_dir else Path.home()
        return agent_root, root_dir
    if not args.portable:
        raise SystemExit("Choose --portable <path> or --global")
    agent_root = Path(args.portable).expanduser().resolve()
    root_dir = Path(args.root_dir).expanduser().resolve() if args.root_dir else agent_root.parent
    return agent_root, root_dir


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Install or update Coding Colony.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--portable", metavar="PATH", help="Install/generate a portable setup at PATH.")
    mode.add_argument("--global", dest="global_install", action="store_true", help="Install under ~/.coding-colony.")
    parser.add_argument("--root-dir", help="Workspace root containing target repositories. Defaults to parent of portable path.")
    parser.add_argument("--harness", action="append", help="Harness to generate: codex, claude, opencode. Repeat or comma-separate.")
    parser.add_argument("--provider", help="Compatible provider profile from config/providers.json. Defaults to each harness's native provider.")
    parser.add_argument("--plugin", action="append", help="Optional plugin to enable. Repeat or comma-separate.")
    parser.add_argument("--no-plugin-prompt", action="store_true", help="Do not ask about optional plugins when --plugin is omitted.")
    parser.add_argument("--install-missing-plugins", action="store_true", help="Install missing optional plugin dependencies that have configured install commands.")
    parser.add_argument("--no-path-prompt", action="store_true", help="Do not ask whether to add coding-colony to PATH.")
    parser.add_argument("--no-strict", action="store_true", help="Do not fail when an explicitly requested harness binary is missing.")
    parser.add_argument("--dry-run", action="store_true", help="Print intended writes without changing files.")
    args = parser.parse_args(argv)

    explicit_harness = bool(args.harness)
    requested_harnesses = split_csv(args.harness) or list(SUPPORTED_HARNESSES)
    harnesses = validate_harnesses(requested_harnesses, explicit_harness, args.no_strict)
    validate_provider_harnesses(
        args.provider,
        harnesses,
        read_json(repo_root() / "config" / "providers.json"),
    )
    agent_root, root_dir = resolve_install(args)
    if not args.dry_run:
        agent_root.mkdir(parents=True, exist_ok=True)
        for harness in harnesses:
            (agent_root / f".{harness}").mkdir(parents=True, exist_ok=True)
    plugin_defs = read_json(repo_root() / "config" / "plugins.json")
    requested_plugins = split_csv(args.plugin)
    prompt_for_plugins = not requested_plugins and not args.no_plugin_prompt and not args.dry_run and sys.stdin.isatty()
    prompt_for_install = not args.dry_run and sys.stdin.isatty()
    plugins, optional_deps = select_plugins(
        requested_plugins or list(DEFAULT_PLUGINS),
        plugin_defs,
        prompt_for_plugins,
        args.install_missing_plugins,
        prompt_for_install,
        args.dry_run,
    )
    if plugins:
        configure_selected_plugins(plugins, plugin_defs, optional_deps, harnesses, agent_root, args.dry_run)
    generate(agent_root, root_dir, harnesses, args.provider, plugins, optional_deps, args.dry_run)
    if not args.dry_run and not args.no_path_prompt and sys.stdin.isatty():
        maybe_add_coding_colony_to_path(agent_root)
    print("Generated harnesses:", ", ".join(harnesses))
    print("Agent root:", agent_root)
    print("Root dir:", root_dir)
    return 0


SESSION_CONTEXT_PY = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys


def read_env(root: Path) -> dict[str, str]:
    values = {}
    env_path = root / ".env"
    if not env_path.exists():
        return values
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    raw_event = payload.get("hook_event_name") or "SessionStart"
    event = {
        "session_start": "SessionStart",
        "subagent_start": "SubagentStart",
    }.get(str(raw_event).lower(), "SessionStart")
    agent_root = Path(os.environ.get("AGENT_ROOT", Path.cwd()))
    env = read_env(agent_root)
    env.update(os.environ)
    context = f"""Generated agent setup context:
- ROOT_DIR: `{env.get('ROOT_DIR', '<unset>')}`
- AGENT_ROOT: `{env.get('AGENT_ROOT', str(Path.cwd()))}`
- Harnesses: `{env.get('AGENT_HARNESSES', '')}`
- Provider: `{env.get('AGENT_PROVIDER', '')}`
- Plugins: `{env.get('AGENT_PLUGINS', '')}`
- Optional deps: `{env.get('AGENT_OPTIONAL_DEPS', '')}`
- Detected tools: `{env.get('AGENT_DETECTED_TOOLS', '')}`
- Plugin installs: `{env.get('AGENT_PLUGIN_INSTALLS', '')}`
- Read repo-local AGENTS.md before target-repository changes.
- Optional Graphify workflows apply only when enabled and graphify-out/graph.json exists.
"""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


PRE_TOOL_USE_POLICY_PY = r'''#!/usr/bin/env python3
import json
import os
import re
import shlex
from pathlib import Path
import sys


def read_env(root: Path) -> dict[str, str]:
    values = {}
    env_path = root / ".env"
    if not env_path.exists():
        return values
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def parse_gradle(command: str):
    match = re.search(r"(?:cd\s+(?P<repo>[^&;]+?)\s*&&\s*)?\./gradlew\s+(?P<args>.+)$", command, re.S)
    if not match:
        return None
    return {
        "repo_path": (match.group("repo") or "").strip().strip("'\""),
        "args": match.group("args").strip(),
    }


def candidate_repo(payload: dict, tool_input: dict, parsed: dict, env: dict[str, str]) -> str:
    if parsed.get("repo_path"):
        path = Path(parsed["repo_path"]).expanduser()
        if not path.is_absolute():
            base = next(
                (
                    value
                    for value in (
                        tool_input.get("cwd"),
                        tool_input.get("workdir"),
                        payload.get("cwd"),
                        payload.get("workdir"),
                        os.environ.get("AGENT_TARGET_REPO"),
                        env.get("AGENT_TARGET_REPO"),
                    )
                    if value
                ),
                str(Path.cwd()),
            )
            path = Path(base).expanduser() / path
        return str(path.resolve())
    candidates = [
        os.environ.get("AGENT_TARGET_REPO"),
        env.get("AGENT_TARGET_REPO"),
        tool_input.get("cwd"),
        tool_input.get("workdir"),
        payload.get("cwd"),
        payload.get("workdir"),
        str(Path.cwd()),
    ]
    for value in candidates:
        if not value:
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return str(path.resolve())
    return str(Path.cwd())


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or tool_input.get("cmd")
    if not isinstance(command, str):
        return 0
    parsed = parse_gradle(command)
    if not parsed or not re.search(r"(^|\s)(build|test|integrationTest|check)(\s|$)", parsed["args"]):
        return 0
    env = read_env(Path.cwd())
    wrapper = Path(os.environ.get("AGENT_ROOT") or env.get("AGENT_ROOT", str(Path.cwd()))) / ".config" / "bin" / "run-gradle-summarized.sh"
    if not wrapper.exists():
        return 0
    repo_path = candidate_repo(payload, tool_input, parsed, env)
    new_command = f"zsh {shlex.quote(str(wrapper))} {shlex.quote(repo_path)} {parsed['args']}"
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {"command": new_command},
            "additionalContext": "Redirected Gradle test/check command to the generated summarized wrapper."
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


OPENCODE_GRAPHIFY_JS = r'''// Generated optional graphify plugin.
import { existsSync } from "fs";
import { join } from "path";

const MARKER = "graphify-plugin-active";
const INSTRUCTIONS = `<graphify_context marker="${MARKER}">
When graphify-out/graph.json exists and repository discovery is broad, query the
graph before broad source reads. Skip this for direct edits to already-named files.
</graphify_context>`;

export const GraphifyPlugin = async ({ directory }) => ({
  "experimental.chat.system.transform": async (_input, output) => {
    if (!Array.isArray(output?.system)) return;
    if (output.system.some((entry) => typeof entry === "string" && entry.includes(MARKER))) return;
    if (!existsSync(join(directory, "graphify-out", "graph.json"))) return;
    output.system.splice(1, 0, INSTRUCTIONS);
  },
});
'''


CODING_COLONY_CLI = r'''#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time


HARNESSES = ("codex", "claude", "opencode")
MODEL_TIERS = ("fast", "balanced", "deep")
ROLE_NAMES = __ROLE_NAMES_JSON__


def fail(message, code=1):
    print(message, file=sys.stderr)
    raise SystemExit(code)


def usage(code=64):
    stream = sys.stdout if code == 0 else sys.stderr
    print("Usage: coding-colony <codex|claude|opencode> [--yolo] [--repo PATH] [-- harness args ...]", file=stream)
    raise SystemExit(code)


def parse_args(argv):
    if not argv:
        usage()
    if argv[0] in {"-h", "--help"}:
        usage(0)
    harness, remaining = argv[0], argv[1:]
    if harness not in HARNESSES:
        usage()
    repo = None
    yolo = False
    passthrough = []
    index = 0
    while index < len(remaining):
        argument = remaining[index]
        if argument == "--":
            passthrough.extend(remaining[index + 1 :])
            break
        if argument == "--yolo":
            yolo = True
            index += 1
            continue
        if argument == "--repo":
            if index + 1 >= len(remaining):
                usage()
            repo = Path(remaining[index + 1]).expanduser()
            index += 2
            continue
        passthrough.append(argument)
        index += 1
    if yolo and harness == "claude":
        fail("--yolo is supported only for codex and opencode", 64)
    return harness, repo, yolo, passthrough


def resolve_repo(repo, agent_root):
    if repo is None:
        repo = agent_root
    try:
        repo = repo.resolve(strict=True)
    except OSError as error:
        fail(f"Invalid repository path: {error}", 64)
    if not repo.is_dir():
        fail(f"Repository path is not a directory: {repo}", 64)
    return repo


def read_env(path):
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_codex_bridge(agent_root):
    path = agent_root / ".codex" / "bridge.json"
    try:
        bridge = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"Invalid generated Codex bridge {path}: {error}")
    if not isinstance(bridge, dict) or set(bridge) != {"agents", "mcp_servers"}:
        fail(f"Invalid generated Codex bridge contract: {path}")
    if not isinstance(bridge["agents"], dict) or set(bridge["agents"]) != set(ROLE_NAMES):
        fail(f"Invalid generated Codex agent bridge: {path}")
    if not isinstance(bridge["mcp_servers"], dict):
        fail(f"Invalid generated Codex MCP bridge: {path}")
    return bridge


def toml_inline(value):
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_inline(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(
            f"{json.dumps(str(key))} = {toml_inline(item)}" for key, item in value.items()
        ) + " }"
    fail(f"Cannot encode generated Codex bridge value of type {type(value).__name__}")


def rewrite_codex_hook_paths(value):
    if isinstance(value, str):
        return value.replace("${CODEX_HOME}", "${AGENT_ROOT}/.codex").replace(
            "$CODEX_HOME", "$AGENT_ROOT/.codex"
        )
    if isinstance(value, list):
        return [rewrite_codex_hook_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: rewrite_codex_hook_paths(item) for key, item in value.items()}
    return value


def user_codex_home(environment):
    configured = environment.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    user_home = Path(environment.get("HOME") or str(Path.home())).expanduser().resolve()
    return user_home / ".codex"


def link_codex_skills(agent_root, environment):
    source_root = agent_root / ".codex" / "skills"
    user_home = Path(environment.get("HOME") or str(Path.home())).expanduser().resolve()
    destination_root = user_home / ".agents" / "skills"
    destination = destination_root / "coding-colony"
    try:
        destination_root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        fail(f"Cannot create Codex skill directory {destination_root}: {error}")
    if destination.is_symlink():
        try:
            if destination.resolve(strict=True) == source_root.resolve(strict=True):
                return
        except OSError:
            pass
    if destination.exists() or destination.is_symlink():
        fail(
            f"Cannot register Coding Colony skills because {destination} already exists. "
            "Move that path or link it to the installed .codex/skills directory."
        )
    try:
        destination.symlink_to(source_root, target_is_directory=True)
    except FileExistsError:
        try:
            if (
                destination.is_symlink()
                and destination.resolve(strict=True) == source_root.resolve(strict=True)
            ):
                return
        except OSError:
            pass
        fail(f"Cannot register Coding Colony skills because {destination} was created concurrently")
    except OSError as error:
        fail(f"Cannot link Codex skills {source_root} into {destination}: {error}")


def append_codex_config(command, key, value):
    command.extend(["--config", f"{key}={toml_inline(value)}"])


def codex_command(agent_root, repo, docs, environment):
    codex_home = user_codex_home(environment)
    try:
        codex_home.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        fail(f"Cannot create Codex home {codex_home}: {error}")
    environment["CODEX_HOME"] = str(codex_home)
    link_codex_skills(agent_root, environment)
    bridge = load_codex_bridge(agent_root)
    command = ["codex"]

    command.extend(["--enable", "hooks", "--enable", "multi_agent"])
    append_codex_config(command, "agents.max_threads", 3)
    append_codex_config(command, "agents.max_depth", 2)
    for role in ROLE_NAMES:
        append_codex_config(command, f"agents.{role}.description", bridge["agents"][role])
        append_codex_config(
            command,
            f"agents.{role}.config_file",
            str(agent_root / ".codex" / "agents" / f"{role}.toml"),
        )

    hooks_path = agent_root / ".codex" / "hooks.json"
    try:
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        fail(f"Invalid generated Codex hooks {hooks_path}: {error}")
    if not isinstance(hooks, dict):
        fail(f"Invalid generated Codex hooks contract: {hooks_path}")
    for event, definitions in hooks.items():
        append_codex_config(command, f"hooks.{event}", rewrite_codex_hook_paths(definitions))

    for name, server in bridge["mcp_servers"].items():
        safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
        append_codex_config(command, f"mcp_servers.coding_colony_{safe_name}", server)

    command.extend(["-C", str(repo), "--add-dir", str(docs)])
    return command


def load_config(agent_root, harness):
    path = agent_root / "coding-colony.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"Invalid coding-colony.json: {error}")
    if not isinstance(config, dict) or set(config) != {"models", "agents"}:
        fail("coding-colony.json must contain only `models` and `agents`")
    models = config.get("models")
    agents = config.get("agents")
    if not isinstance(models, dict) or harness not in models:
        fail(f"Harness `{harness}` is not installed in coding-colony.json")
    harness_models = models[harness]
    if not isinstance(harness_models, dict) or set(harness_models) != {"default", *MODEL_TIERS}:
        fail(f"coding-colony.json models.{harness} must contain default, fast, balanced, and deep")
    if any(not isinstance(value, str) or not value.strip() for value in harness_models.values()):
        fail(f"coding-colony.json models.{harness} values must be non-empty strings")
    if not isinstance(agents, dict) or set(agents) != set(ROLE_NAMES):
        fail("coding-colony.json agents must contain exactly the installed Coding Colony agents")
    resolved = {}
    for role, override in agents.items():
        if not isinstance(override, dict) or set(override) != {"model", "reasoning"}:
            fail(f"coding-colony.json agents.{role} must contain only model and reasoning")
        tier = override["model"]
        reasoning = override["reasoning"]
        if tier not in MODEL_TIERS:
            fail(f"coding-colony.json agents.{role}.model must be fast, balanced, or deep")
        if not isinstance(reasoning, str) or not reasoning.strip():
            fail(f"coding-colony.json agents.{role}.reasoning must be a non-empty string")
        resolved[role] = (harness_models[tier], reasoning, tier)
    return harness_models, resolved


def atomic_write(path, content):
    try:
        if path.read_text(encoding="utf-8") == content:
            return
        mode = path.stat().st_mode & 0o777
    except OSError as error:
        fail(f"Cannot read generated runtime file {path}: {error}")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        temporary.chmod(mode)
        os.replace(temporary, path)
    except OSError as error:
        fail(f"Cannot update generated runtime file {path}: {error}")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def replace_line(path, key, separator, value):
    content = path.read_text(encoding="utf-8")
    pattern = rf"(?m)^{re.escape(key)}\s*{re.escape(separator)}\s*.*$"
    updated, count = re.subn(pattern, f"{key}{separator}{value}", content, count=1)
    if count != 1:
        fail(f"Generated runtime file is missing `{key}`: {path}")
    atomic_write(path, updated)


def update_json(path, key, value):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"Invalid generated runtime config {path}: {error}")
    data[key] = value
    atomic_write(path, json.dumps(data, indent=2) + "\n")


def slugify(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "project"


def project_docs_lock(path):
    return path.parent / f".{path.name}.coding-colony-project.lock"


def claim_project_docs(path, repo):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        fail(f"Cannot create project docs root {path.parent}: {error}")
    marker = path / ".coding-colony-project.json"
    payload = json.dumps({"repository": str(repo)}, indent=2) + "\n"
    if marker.exists():
        try:
            existing = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            fail(f"Invalid project docs identity marker {marker}: {error}")
        return existing == {"repository": str(repo)}
    lock = project_docs_lock(path)
    for _ in range(100):
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if marker.exists():
                return claim_project_docs(path, repo)
            time.sleep(0.01)
        except OSError as error:
            fail(f"Cannot claim project docs directory {path}: {error}")
    else:
        fail(f"Timed out waiting for project docs identity lock {lock}")
    temporary = None
    try:
        path.mkdir(parents=True, exist_ok=True)
        if marker.exists():
            return claim_project_docs(path, repo)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path, prefix=".coding-colony-project.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        temporary.chmod(0o600)
        os.replace(temporary, marker)
        return True
    except OSError as error:
        fail(f"Cannot write project docs identity marker {marker}: {error}")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
        try:
            lock.rmdir()
        except FileNotFoundError:
            pass


def legacy_docs_are_unambiguous(root_value, repo, slug):
    if not root_value or not (repo / ".git").exists():
        return False
    try:
        root = Path(root_value).expanduser().resolve(strict=True)
        repo.relative_to(root)
    except (OSError, ValueError):
        return False
    matches = []
    errors = []
    for current, directories, files in os.walk(root, onerror=errors.append):
        if ".git" in directories or ".git" in files:
            candidate = Path(current).resolve()
            if slugify(candidate.name) == slug:
                matches.append(candidate)
                if len(matches) > 1:
                    return False
        directories[:] = [name for name in directories if name != ".git"]
    return not errors and matches == [repo]


def project_docs(agent_root, repo, environment):
    base = slugify(repo.name)
    docs_root = agent_root / "docs"
    legacy = docs_root / base
    root_value = environment.get("ROOT_DIR")
    if root_value:
        try:
            relative = repo.relative_to(Path(root_value).expanduser().resolve(strict=True))
        except (OSError, ValueError):
            relative = None
    else:
        relative = None
    if legacy.exists():
        marker = legacy / ".coding-colony-project.json"
        if not marker.exists() and project_docs_lock(legacy).exists():
            if claim_project_docs(legacy, repo):
                return legacy
        if not marker.exists() and not legacy_docs_are_unambiguous(root_value, repo, base):
            expected = json.dumps({"repository": str(repo)})
            fail(
                f"Unmarked legacy project docs have ambiguous ownership: {legacy}. "
                f"Create {marker} with {expected} only if these docs belong to {repo}, then retry."
            )
        if claim_project_docs(legacy, repo):
            return legacy
    elif relative is not None and len(relative.parts) <= 1:
        if claim_project_docs(legacy, repo):
            return legacy
    identity = relative.as_posix() if relative is not None else str(repo)
    qualified = slugify(identity) if relative is not None else base
    digest = hashlib.sha256(str(repo).encode("utf-8")).hexdigest()[:12]
    destination = docs_root / f"{qualified}-{digest}"
    if not claim_project_docs(destination, repo):
        fail(f"Project docs identity collision at {destination}")
    return destination


def sync_runtime(agent_root, harness, models, agents):
    if harness == "codex":
        home = agent_root / ".codex"
        replace_line(home / "config.toml", "model", " = ", json.dumps(models["default"]))
        for role, (model, reasoning, _tier) in agents.items():
            path = home / "agents" / f"{role}.toml"
            replace_line(path, "model", " = ", json.dumps(model))
            replace_line(path, "model_reasoning_effort", " = ", json.dumps(reasoning))
    elif harness == "claude":
        home = agent_root / ".claude"
        update_json(home / "settings.json", "model", models["default"])
        for role, (model, reasoning, tier) in agents.items():
            path = home / "agents" / f"{role}.md"
            replace_line(path, "model", ": ", json.dumps(model))
            replace_line(path, "effort", ": ", json.dumps(reasoning))
            replace_line(path, "x-agent-tier", ": ", tier)
    else:
        home = agent_root / ".opencode"
        update_json(home / "opencode.json", "model", models["default"])
        for role, (model, reasoning, tier) in agents.items():
            path = home / "agents" / f"{role}.md"
            replace_line(path, "model", ": ", json.dumps(model))
            replace_line(path, "variant", ": ", json.dumps(reasoning))
            replace_line(path, "x-agent-tier", ": ", tier)


def allow_opencode_docs(environment, docs):
    raw = environment.get("OPENCODE_CONFIG_CONTENT", "")
    try:
        inline = json.loads(raw) if raw else {}
    except json.JSONDecodeError as error:
        fail(f"OPENCODE_CONFIG_CONTENT must be valid JSON: {error}")
    if not isinstance(inline, dict):
        fail("OPENCODE_CONFIG_CONTENT must be a JSON object")
    permission = inline.get("permission", {})
    if isinstance(permission, str):
        permission = {"*": permission}
    if not isinstance(permission, dict):
        fail("OPENCODE_CONFIG_CONTENT permission must be a string or object")
    pattern = f"{docs}/**"
    external = permission.get("external_directory", "ask")
    if isinstance(external, dict):
        external[pattern] = "allow"
    else:
        permission["external_directory"] = {"*": external, pattern: "allow"}
    inline["permission"] = permission
    environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(inline, separators=(",", ":"))


def main(argv):
    harness, repo, yolo, passthrough = parse_args(argv)
    agent_root = Path(__file__).resolve().parents[2]
    models, agents = load_config(agent_root, harness)
    sync_runtime(agent_root, harness, models, agents)

    environment = dict(os.environ)
    for key, value in read_env(agent_root / ".env").items():
        environment.setdefault(key, value)
    repo = resolve_repo(repo, agent_root)
    docs = project_docs(agent_root, repo, environment)
    slug = docs.name
    environment.update({
        "AGENT_ROOT": str(agent_root),
        "AGENT_TARGET_REPO": str(repo),
        "AGENT_PROJECT_SLUG": slug,
        "AGENT_PROJECT_DOCS": str(docs),
    })

    if harness == "codex":
        command = codex_command(agent_root, repo, docs, environment)
        if yolo:
            command.append("--dangerously-bypass-approvals-and-sandbox")
    elif harness == "claude":
        environment["CLAUDE_CONFIG_DIR"] = str(agent_root / ".claude")
        command = ["claude", "--add-dir", str(docs), "--mcp-config", str(agent_root / ".mcp.json")]
    else:
        environment["OPENCODE_CONFIG_DIR"] = str(agent_root / ".opencode")
        allow_opencode_docs(environment, docs)
        command = ["opencode"]
        if yolo:
            command.append("--auto")

    os.chdir(repo)
    try:
        os.execvpe(command[0], [*command, *passthrough], environment)
    except FileNotFoundError:
        fail(f"Harness executable not found: {command[0]}")


if __name__ == "__main__":
    main(sys.argv[1:])
'''


OPENCODE_GRADLE_JS = r'''// Generated optional Gradle wrapper redirect plugin.
const MARKER = "[gradle-wrapper-redirected]";

function shellQuote(value) {
  if (/^[A-Za-z0-9_./:-]+$/.test(value)) return value;
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

export const GradleWrapperRedirectPlugin = async ({ directory }) => ({
  "tool.execute.before": async (input, output) => {
    if (input.tool !== "bash") return;
    const command = output?.args?.command;
    if (typeof command !== "string") return;
    const match = command.match(/(?:cd\s+(?<repo>[^&;]+?)\s*&&\s*)?\.\/gradlew\s+(?<args>.+)$/s);
    if (!match?.groups?.args || !/(^|\s)(build|test|integrationTest|check)(\s|$)/.test(match.groups.args)) return;
    const repoPath = match.groups.repo?.trim().replace(/^['"]|['"]$/g, "") || process.env.AGENT_TARGET_REPO || output?.args?.cwd || directory;
    const wrapper = `${process.env.AGENT_ROOT || directory}/.config/bin/run-gradle-summarized.sh`;
    output.args.command = `zsh ${shellQuote(wrapper)} ${shellQuote(repoPath)} ${match.groups.args.trim()}`;
    output.args.description = `${MARKER} ${output.args.description || "Runs Gradle via summarized wrapper"}`;
  },
});
'''


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
