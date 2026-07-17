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
    "design": "nadia",
    "implement": "gorn",
    "implement-spike": "riordian",
    "verify": "gomez",
    "bookskeeper": "xardas",
}
ROLE_ORDER = (
    "scout",
    "rhobar",
    "milten",
    "lester",
    "nadia",
    "riordian",
    "gorn",
    "lee",
    "gomez",
    "xardas",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_content(
    agent_root: Path,
    root_dir: Path,
    harnesses: list[str],
    provider: str,
    default_model: str,
    model_tiers: dict[str, str],
    plugins: list[str],
    optional_deps: dict[str, dict[str, str]],
) -> str:
    example = (repo_root() / ".env.example").read_text(encoding="utf-8")
    defaults = {
        "ROOT_DIR": str(root_dir),
        "AGENT_ROOT": str(agent_root),
        "AGENT_HARNESSES": ",".join(harnesses),
        "AGENT_PROVIDER": provider,
        "AGENT_MODEL_DEFAULT": default_model,
        "AGENT_MODEL_FAST": model_tiers["fast"],
        "AGENT_MODEL_BALANCED": model_tiers["balanced"],
        "AGENT_MODEL_DEEP": model_tiers["deep"],
        "AGENT_MODEL_DESIGN": model_tiers["design"],
        "AGENT_MODEL_REVIEW": model_tiers["review"],
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
            seen.add(key)
        else:
            lines.append(raw)
    for key, value in defaults.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    return "\n".join(lines).rstrip() + "\n"


def profile_env_content(
    agent_root: Path,
    root_dir: Path,
    harness: str,
    provider_name: str,
    provider: dict,
    plugins: list[str],
    optional_deps: dict[str, dict[str, str]],
    existing_env: dict[str, str],
) -> str:
    model_tiers = model_tiers_for_provider(provider)
    default_model = default_model_for_provider(provider)
    for key in ("AGENT_MODEL_DEFAULT", *(f"AGENT_MODEL_{tier.upper()}" for tier in model_tiers)):
        if existing_env.get(key):
            if key == "AGENT_MODEL_DEFAULT":
                default_model = existing_env[key]
            else:
                model_tiers[key.removeprefix("AGENT_MODEL_").lower()] = existing_env[key]
    return env_content(
        agent_root,
        root_dir,
        [harness],
        provider_name,
        default_model,
        model_tiers,
        plugins,
        optional_deps,
    )


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


def apply_existing_model_overrides(
    model_tiers: dict[str, str], default_model: str, existing_env: dict[str, str]
) -> tuple[dict[str, str], str]:
    result = dict(model_tiers)
    for tier in result:
        value = existing_env.get(tier_env_name(tier))
        if value:
            result[tier] = value
    return result, existing_env.get("AGENT_MODEL_DEFAULT") or default_model


def merged_model_tiers(harnesses: list[str], explicit_provider: str | None, providers: dict) -> dict[str, str]:
    if explicit_provider:
        return model_tiers_for_provider(providers[explicit_provider])
    if len(harnesses) == 1:
        return model_tiers_for_provider(providers[NATIVE_PROVIDER_BY_HARNESS[harnesses[0]]])
    # Multi-harness native installs use each harness's own runtime config. The
    # shared .env gets Codex-native defaults only as a portable fallback.
    return model_tiers_for_provider(providers["codex-native"])


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
    return f"""You are {role_name}, {role['description']}

Primary responsibility: {role['summary']}

Model tier: {role['tier']}

Install context:
- Enabled optional plugins: {enabled_plugins}
- {graph_line}

Shared rules:
- Read repo-local AGENTS.md first when present.
- Keep changes narrow and tied to the user request.
- Prefer rg, rg --files, and bounded file reads.
- Use ROOT_DIR and AGENT_ROOT from the generated environment, not hardcoded paths.
- Keep project-scoped docs under AGENT_ROOT/docs/<project-slug>/; repository-owned guidance remains in the target repository.

Role workflow:
{workflow}
"""


def command_body(command: str, role: str) -> str:
    return f"""# /{command}

Run the `{role}` role workflow for this command.

Repository or task arguments: $ARGUMENTS
"""


def codex_skill_content(command: str, role: str, workflows: dict[str, str]) -> str:
    if role == "gorn":
        delegation_contract = f"""Codex delegation contract: invoking `/{command}` is explicit authorization to
delegate the complete task to the `gorn` custom agent. You are the launcher;
`gorn` owns implementation, review coordination, remediation, and verification.

When native multi-agent tools are available, spawn exactly one `gorn` agent with
the user's full request and these command arguments: `$ARGUMENTS`. Prefer
`send_input` or `resume_agent` when an existing `gorn` agent from this workflow
can continue the work. Do not spawn duplicate implementation agents.

Tell `gorn` to execute the workflow directly, then launch `lee` for review when
the plan or user requests review. `gorn` must wait for Lee, apply blocker/major
findings, and rerun the plan's verification. `gorn` may spawn `lee`, but must
not invoke `/{command}` again or spawn another `gorn`. Wait for the existing
`gorn` workflow to finish and report its result. Do not inspect, edit, or verify
the target repository yourself while `gorn` is working.

If native delegation is unavailable, report that `gorn` could not be spawned;
do not silently execute the workflow as the root agent."""
    else:
        delegation_contract = f"""Codex delegation contract: invoking `/{command}` is explicit authorization to
delegate the complete task to the `{role}` custom agent. You are the
orchestrator, not the workflow owner.

When native multi-agent tools are available, immediately call `spawn_agent` with
`agent_type=\"{role}\"` and pass the user's full request, including these command
arguments: `$ARGUMENTS`. Tell the spawned agent to execute the `{role}` workflow,
make the requested changes, and run its focused verification. The spawned `{role}`
agent is the leaf executor: it must not invoke `/{command}`, delegate again, or
spawn another agent. Call `spawn_agent` exactly once, wait for that agent, then
report its result. Do not inspect, edit, or verify the target repository
yourself before delegation, and do not duplicate the delegated work.

If native delegation is unavailable, report that `{role}` could not be spawned;
do not silently execute the workflow as the root agent."""
    return f"""---
description: Run /{command} through the {role} role workflow.
---

{delegation_contract}

{workflows[role]}
"""


def opencode_command_content(command: str, role: str) -> str:
    return f"""---
description: Run /{command} through the {role} role workflow.
agent: {role}
---

{command_body(command, role)}
"""


def opencode_model_tier_resolver_js(roles: dict) -> str:
    role_tiers = {role_name: roles[role_name]["tier"] for role_name in ROLE_ORDER}
    return OPENCODE_MODEL_TIER_RESOLVER_JS.replace(
        "__ROLE_TIER_JSON__",
        json.dumps(role_tiers, indent=2),
    )


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

    marker = "# Added by agent-v2: coding-colony"
    export_line = f"export PATH={shlex.quote(str(bin_dir))}:$PATH"
    existing = startup_file.read_text(encoding="utf-8") if startup_file.exists() else ""
    if marker in existing or export_line in existing:
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


def configure_plugin_for_harnesses(plugin_name: str, plugin_def: dict, harnesses: list[str], dry_run: bool) -> str:
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
            subprocess.run(command, check=True)
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
    dry_run: bool,
) -> None:
    for plugin_name in plugins:
        plugin_def = plugin_defs[plugin_name]
        state = configure_plugin_for_harnesses(plugin_name, plugin_def, harnesses, dry_run)
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


def generate_base(
    agent_root: Path,
    root_dir: Path,
    harnesses: list[str],
    provider: str,
    default_model: str,
    model_tiers: dict[str, str],
    plugins: list[str],
    optional_deps: dict[str, dict[str, str]],
    dry_run: bool,
) -> None:
    write_file(agent_root / ".env", env_content(agent_root, root_dir, harnesses, provider, default_model, model_tiers, plugins, optional_deps), dry_run)
    write_file(agent_root / ".envrc", envrc_content(), dry_run)
    write_file(agent_root / "AGENTS.md", render_agents_md(), dry_run)
    mkdir(agent_root / "docs", dry_run)
    write_file(
        agent_root / ".config" / "models.json",
        json.dumps({"provider": provider, "default": default_model, "tiers": model_tiers}, indent=2) + "\n",
        dry_run,
    )
    write_file(
        agent_root / ".config" / "install-manifest.json",
        json.dumps({
            "installer": "agent-v2-oss",
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
        CODING_COLONY_CLI,
        dry_run,
        0o755,
    )


def generate_profiles(
    agent_root: Path,
    root_dir: Path,
    harnesses: list[str],
    explicit_provider: str | None,
    providers: dict,
    plugins: list[str],
    optional_deps: dict[str, dict[str, str]],
    dry_run: bool,
) -> None:
    for harness in harnesses:
        provider_name = provider_for_harness(harness, explicit_provider)
        existing_profile = parse_env(agent_root / f"{harness}.env")
        write_file(
            agent_root / f"{harness}.env",
            profile_env_content(
                agent_root,
                root_dir,
                harness,
                provider_name,
                providers[provider_name],
                plugins,
                optional_deps,
                existing_profile,
            ),
            dry_run,
        )


def envrc_content() -> str:
    return """# Generated by agent-v2-oss.
# Run `direnv allow` once in this directory if you want harnesses that support
# environment substitution to read .env values automatically.
dotenv_if_exists .env
"""


def generate_codex(agent_root: Path, provider: dict, roles: dict, plugins: list[str], workflows: dict[str, str], env: dict[str, str], dry_run: bool) -> None:
    codex_dir = agent_root / ".codex"
    mkdir(codex_dir / "agents", dry_run)
    config_lines = [
        "# Generated by agent-v2-oss. Re-run install.sh instead of editing by hand.",
        f"model = {toml_string(env.get('AGENT_MODEL_DEFAULT', provider.get('default_model', provider['tiers']['balanced'])))}",
        'model_reasoning_effort = "medium"',
    ]
    codex_provider = provider.get("codex_provider")
    if codex_provider:
        provider_id = codex_provider["id"]
        base_url = (
            env.get(provider.get("base_url_env", ""), "")
            or provider.get("default_base_url", "")
            or "${" + provider.get("base_url_env", "PROVIDER_BASE_URL") + "}"
        )
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
    for name, server in mcp_servers(plugins, env).items():
        config_lines.extend(["", f"[mcp_servers.{name}]", f"command = {toml_string(server['command'])}"])
    write_file(codex_dir / "config.toml", "\n".join(config_lines) + "\n", dry_run)

    for role_name in ROLE_ORDER:
        role = roles[role_name]
        content = "\n".join([
            f"name = {toml_string(role_name)}",
            f"description = {toml_string(role['description'])}",
            f"model = {toml_string(env.get(tier_env_name(role['tier']), provider['tiers'][role['tier']]))}",
            f"model_reasoning_effort = {toml_string(role['effort'])}",
            f"sandbox_mode = {toml_string(role['sandbox'])}",
            "",
            f"developer_instructions = {toml_multiline(role_prompt(role_name, role, plugins, workflows))}",
            "",
        ])
        write_file(codex_dir / "agents" / f"{role_name}.toml", content, dry_run)

    hooks = {
        "hooks": {
            "SessionStart": [{
                "matcher": "startup|resume|clear|compact",
                "hooks": [{
                    "type": "command",
                    "command": "/usr/bin/python3 \"$PWD/.codex/hooks/session_context.py\"",
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
                "command": "/usr/bin/python3 \"$PWD/.codex/hooks/pre_tool_use_policy.py\"",
                "statusMessage": "Checking shell command"
            }]
        }]
    write_file(codex_dir / "hooks.json", json.dumps(hooks, indent=2) + "\n", dry_run)
    write_file(
        codex_dir / "hooks" / "session_context.py",
        SESSION_CONTEXT_PY.replace(
            "__ROLE_TIER_JSON__",
            json.dumps({name: roles[name]["tier"] for name in ROLE_ORDER}, sort_keys=True),
        ),
        dry_run,
        0o755,
    )
    if "gradle-wrapper" in plugins:
        write_file(codex_dir / "hooks" / "pre_tool_use_policy.py", PRE_TOOL_USE_POLICY_PY, dry_run, 0o755)

    skills_dir = agent_root / ".agents" / "skills"
    for command, role in COMMAND_TO_ROLE.items():
        write_file(skills_dir / command / "SKILL.md", codex_skill_content(command, role, workflows), dry_run)


def generate_claude(agent_root: Path, provider: dict, roles: dict, plugins: list[str], workflows: dict[str, str], env: dict[str, str], dry_run: bool) -> None:
    claude_dir = agent_root / ".claude"
    mkdir(claude_dir / "agents", dry_run)
    for role_name in ROLE_ORDER:
        role = roles[role_name]
        content = "\n".join([
            "---",
            f"name: {role_name}",
            f"description: {role['description']}",
            f"x-agent-tier: {role['tier']}",
            "---",
            "",
            role_prompt(role_name, role, plugins, workflows),
        ])
        write_file(claude_dir / "agents" / f"{role_name}.md", content, dry_run)
    settings = {
        "model": env.get("AGENT_MODEL_DEFAULT", provider.get("default_model", provider["tiers"]["balanced"])),
        "permissions": {
            "allow": ["Bash(rg:*)", "Bash(sed:*)", "Bash(find:*)", "Bash(git status:*)"],
            "deny": ["Bash(git reset --hard:*)", "Bash(git checkout --:*)"]
        }
    }
    write_file(claude_dir / "settings.json", json.dumps(settings, indent=2) + "\n", dry_run)
    write_file(agent_root / "CLAUDE.md", "Read AGENTS.md first. Role definitions live under .claude/agents/.\n", dry_run)
    write_file(agent_root / ".mcp.json", json.dumps({"mcpServers": mcp_servers(plugins, env)}, indent=2) + "\n", dry_run)


def generate_opencode(agent_root: Path, provider: dict, roles: dict, plugins: list[str], workflows: dict[str, str], env: dict[str, str], dry_run: bool) -> None:
    opencode_dir = agent_root / ".opencode"
    mkdir(opencode_dir / "agents", dry_run)
    mkdir(opencode_dir / "commands", dry_run)
    for role_name in ROLE_ORDER:
        role = roles[role_name]
        content = "\n".join([
            "---",
            f"description: {role['description']}",
            f"model: {role['tier']}",
            f"x-agent-tier: {role['tier']}",
            "mode: all",
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
    config = {
        "$schema": "https://opencode.ai/config.json",
        "model": env.get("AGENT_MODEL_DEFAULT", provider.get("default_model", provider["tiers"]["balanced"])),
        "mcp": {
            name: {"type": "local", "command": [server["command"]]}
            for name, server in mcp_servers(plugins, env).items()
        },
        "plugin": ["./plugins/model-tier-resolver.js"],
    }
    write_file(opencode_dir / "plugins" / "model-tier-resolver.js", opencode_model_tier_resolver_js(roles), dry_run)
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
    plugin_defs = read_json(repo_root() / "config" / "plugins.json")
    roles = read_json(repo_root() / "config" / "roles.json")
    workflows = read_role_workflows()
    if explicit_provider and explicit_provider not in providers:
        raise SystemExit(f"Unknown provider profile: {explicit_provider}")
    selected_provider_label = provider_label(harnesses, explicit_provider)
    env = parse_env(agent_root / ".env")
    default_provider_name = explicit_provider
    if not default_provider_name:
        default_provider_name = (
            NATIVE_PROVIDER_BY_HARNESS[harnesses[0]]
            if len(harnesses) == 1
            else "codex-native"
        )
    default_model = default_model_for_provider(providers[default_provider_name])
    model_tiers = merged_model_tiers(harnesses, explicit_provider, providers)
    if not explicit_provider:
        model_tiers, default_model = apply_existing_model_overrides(model_tiers, default_model, env)
    env.update({
        "ROOT_DIR": str(root_dir),
        "AGENT_ROOT": str(agent_root),
        "AGENT_PROVIDER": selected_provider_label,
        "AGENT_HARNESSES": ",".join(harnesses),
        "AGENT_MODEL_DEFAULT": default_model,
        "AGENT_PLUGINS": ",".join(plugins),
        "AGENT_OPTIONAL_DEPS": serialize_optional_deps(optional_deps),
        "AGENT_DETECTED_TOOLS": serialize_detected_tools(optional_deps),
        "AGENT_PLUGIN_INSTALLS": serialize_plugin_installs(optional_deps),
        "AGENT_MODEL_FAST": model_tiers["fast"],
        "AGENT_MODEL_BALANCED": model_tiers["balanced"],
        "AGENT_MODEL_DEEP": model_tiers["deep"],
        "AGENT_MODEL_DESIGN": model_tiers["design"],
        "AGENT_MODEL_REVIEW": model_tiers["review"],
    })

    generate_base(agent_root, root_dir, harnesses, selected_provider_label, default_model, model_tiers, plugins, optional_deps, dry_run)
    generate_profiles(agent_root, root_dir, harnesses, explicit_provider, providers, plugins, optional_deps, dry_run)
    for harness in harnesses:
        provider_name = provider_for_harness(harness, explicit_provider)
        provider = providers[provider_name]
        if harness == "codex":
            generate_codex(agent_root, provider, roles, plugins, workflows, env, dry_run)
        elif harness == "claude":
            generate_claude(agent_root, provider, roles, plugins, workflows, env, dry_run)
        elif harness == "opencode":
            generate_opencode(agent_root, provider, roles, plugins, workflows, env, dry_run)


def resolve_install(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.global_install:
        agent_root = Path.home() / ".agent-v2"
        root_dir = Path(args.root_dir).expanduser().resolve() if args.root_dir else Path.home()
        return agent_root, root_dir
    if not args.portable:
        raise SystemExit("Choose --portable <path> or --global")
    agent_root = Path(args.portable).expanduser().resolve()
    root_dir = Path(args.root_dir).expanduser().resolve() if args.root_dir else agent_root.parent
    return agent_root, root_dir


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Install or generate agent-v2-oss harness configuration.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--portable", metavar="PATH", help="Install/generate a portable setup at PATH.")
    mode.add_argument("--global", dest="global_install", action="store_true", help="Install/generate under ~/.agent-v2.")
    parser.add_argument("--root-dir", help="Workspace root containing target repositories. Defaults to parent of portable path.")
    parser.add_argument("--harness", action="append", help="Harness to generate: codex, claude, opencode. Repeat or comma-separate.")
    parser.add_argument("--provider", help="Provider profile from config/providers.json. Defaults to the native provider for each selected harness.")
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
    if plugins and (args.install_missing_plugins or prompt_for_plugins):
        configure_selected_plugins(plugins, plugin_defs, optional_deps, harnesses, args.dry_run)
    agent_root, root_dir = resolve_install(args)
    if not args.dry_run:
        agent_root.mkdir(parents=True, exist_ok=True)
    generate(agent_root, root_dir, harnesses, args.provider, plugins, optional_deps, args.dry_run)
    if not args.dry_run and not args.no_path_prompt and sys.stdin.isatty():
        maybe_add_coding_colony_to_path(agent_root)
    print("Generated harnesses:", ", ".join(harnesses))
    print("Agent root:", agent_root)
    print("Root dir:", root_dir)
    return 0


SESSION_CONTEXT_PY = r'''#!/usr/bin/env python3
import json
from pathlib import Path
import re
import sys

ROLE_TIER = __ROLE_TIER_JSON__


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


def sync_models(agent_root: Path, env: dict[str, str]) -> None:
    """Refresh Codex's concrete model fields from the editable .env file."""
    balanced = env.get("AGENT_MODEL_BALANCED")
    config_path = agent_root / ".codex" / "config.toml"
    if balanced and config_path.exists():
        config = config_path.read_text(encoding="utf-8")
        config = re.sub(r"^model\s*=\s*.*$", f"model = {json.dumps(env.get('AGENT_MODEL_DEFAULT', balanced))}", config, count=1, flags=re.MULTILINE)
        config_path.write_text(config, encoding="utf-8")

    agents_dir = agent_root / ".codex" / "agents"
    for role, tier in ROLE_TIER.items():
        model = env.get(f"AGENT_MODEL_{tier.upper()}")
        agent_path = agents_dir / f"{role}.toml"
        if not model or not agent_path.exists():
            continue
        content = agent_path.read_text(encoding="utf-8")
        content = re.sub(r"^model\s*=\s*.*$", f"model = {json.dumps(model)}", content, count=1, flags=re.MULTILINE)
        agent_path.write_text(content, encoding="utf-8")


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
    agent_root = Path.cwd()
    env = read_env(agent_root)
    configured_root = env.get("AGENT_ROOT")
    if configured_root:
        agent_root = Path(configured_root)
        env = read_env(agent_root)
    try:
        sync_models(agent_root, env)
        model_sync_status = "Model mappings refreshed from .env."
    except Exception as error:
        # A model refresh must never prevent Codex from starting.
        model_sync_status = f"Model refresh skipped: {type(error).__name__}."
    context = f"""Generated agent setup context:
- ROOT_DIR: `{env.get('ROOT_DIR', '<unset>')}`
- AGENT_ROOT: `{env.get('AGENT_ROOT', str(Path.cwd()))}`
- Harnesses: `{env.get('AGENT_HARNESSES', '')}`
- Provider: `{env.get('AGENT_PROVIDER', '')}`
- Plugins: `{env.get('AGENT_PLUGINS', '')}`
- Optional deps: `{env.get('AGENT_OPTIONAL_DEPS', '')}`
- Detected tools: `{env.get('AGENT_DETECTED_TOOLS', '')}`
- Plugin installs: `{env.get('AGENT_PLUGIN_INSTALLS', '')}`
- {model_sync_status}
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
    if not parsed or not re.search(r"(^|\s)(test|integrationTest|check)(\s|$)", parsed["args"]):
        return 0
    env = read_env(Path.cwd())
    wrapper = Path(env.get("AGENT_ROOT", str(Path.cwd()))) / ".config" / "bin" / "run-gradle-summarized.sh"
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


CODING_COLONY_CLI = r'''#!/usr/bin/env bash
set -euo pipefail

agent_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
usage() {
  printf 'Usage: coding-colony <codex|claude|opencode> [--yolo] [--repo PATH] [-- harness args ...]\n' >&2
}

if [[ $# -lt 1 ]]; then
  usage
  exit 64
fi

harness="$1"
shift
yolo=false
repo_path="$(pwd -P)"
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yolo)
      yolo=true
      shift
      ;;
    --repo)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      repo_path="$(CDPATH= cd -- "$2" && pwd -P)"
      shift 2
      ;;
    --)
      shift
      args+=("$@")
      break
      ;;
    *)
      args+=("$1")
      shift
      ;;
  esac
done

case "$harness" in
  codex|claude|opencode) ;;
  *) usage; exit 64 ;;
esac
if [[ "$yolo" == true && "$harness" == claude ]]; then
  printf '%s\n' '--yolo is supported only for codex and opencode' >&2
  exit 64
fi

profile="$agent_root/$harness.env"
[[ -f "$profile" ]] || { printf 'Missing profile: %s\n' "$profile" >&2; exit 1; }
cp "$profile" "$agent_root/.env"
export AGENT_TARGET_REPO="$repo_path"
cd "$agent_root"

case "$harness" in
  codex)
    [[ "$yolo" == true ]] && args+=(--yolo)
    exec codex "${args[@]}"
    ;;
  opencode)
    [[ "$yolo" == true ]] && args+=(--auto)
    exec opencode "${args[@]}"
    ;;
  claude)
    exec claude "${args[@]}"
    ;;
esac
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
    if (!match?.groups?.args || !/(^|\s)(test|integrationTest|check)(\s|$)/.test(match.groups.args)) return;
    const repoPath = match.groups.repo?.trim().replace(/^['"]|['"]$/g, "") || process.env.AGENT_TARGET_REPO || output?.args?.cwd || directory;
    const wrapper = `${directory}/.config/bin/run-gradle-summarized.sh`;
    output.args.command = `zsh ${shellQuote(wrapper)} ${shellQuote(repoPath)} ${match.groups.args.trim()}`;
    output.args.description = `${MARKER} ${output.args.description || "Runs Gradle via summarized wrapper"}`;
  },
});
'''


OPENCODE_MODEL_TIER_RESOLVER_JS = r'''// Generated OpenCode model tier resolver.
// Lets agent frontmatter use model tiers such as `model: deep` while resolving
// to concrete provider/model IDs from .env during OpenCode config loading.
import { readFileSync } from "fs";
import { join } from "path";

const ROLE_TIER = __ROLE_TIER_JSON__;

const TIER_ENV = {
  fast: "AGENT_MODEL_FAST",
  balanced: "AGENT_MODEL_BALANCED",
  deep: "AGENT_MODEL_DEEP",
  design: "AGENT_MODEL_DESIGN",
  review: "AGENT_MODEL_REVIEW",
};

function readEnv(directory) {
  const values = {};
  try {
    const text = readFileSync(join(directory, ".env"), "utf8");
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith("#") || !line.includes("=")) continue;
      const index = line.indexOf("=");
      values[line.slice(0, index)] = line.slice(index + 1).replace(/^['"]|['"]$/g, "");
    }
  } catch {
    // Missing .env should not break OpenCode startup.
  }
  return values;
}

export const ModelTierResolverPlugin = async ({ directory }) => {
  const env = readEnv(directory);
  return {
    config: async (config) => {
      if (env.AGENT_MODEL_DEFAULT) config.model = env.AGENT_MODEL_DEFAULT;
      config.agent = config.agent || {};
      for (const [role, tier] of Object.entries(ROLE_TIER)) {
        const model = env[TIER_ENV[tier]];
        if (!model) continue;
        config.agent[role] = {
          ...(config.agent[role] || {}),
          model,
        };
      }
    },
  };
};
'''

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
