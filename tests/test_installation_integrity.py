from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "agent_setup.py"
HARNESSES = ("codex", "claude", "opencode")
COMMAND_TO_ROLE = {
    "spec": "rhobar",
    "refine": "milten",
    "analyze": "lester",
    "implement": "gorn",
    "verify": "gomez",
    "bookskeeper": "xardas",
}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def body_without_frontmatter(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return "\n".join(lines)
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            return "\n".join(lines[index + 1 :])
    return "\n".join(lines)


class InstallationIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.providers = json.loads((REPO_ROOT / "config" / "providers.json").read_text(encoding="utf-8"))
        cls.roles = json.loads((REPO_ROOT / "config" / "roles.json").read_text(encoding="utf-8"))
        cls.shared_instructions = (REPO_ROOT / "core" / "shared-instructions.md").read_text(encoding="utf-8").strip()

    def test_role_and_provider_contracts(self) -> None:
        self.assertEqual(
            set(self.roles),
            {"scout", "rhobar", "milten", "lester", "gorn", "lee", "gomez", "xardas"},
        )
        self.assertEqual(
            {key: self.roles["scout"][key] for key in ("tier", "effort", "sandbox")},
            {"tier": "fast", "effort": "low", "sandbox": "read-only"},
        )
        self.assertEqual(
            {key: self.roles["milten"][key] for key in ("tier", "effort")},
            {"tier": "balanced", "effort": "high"},
        )
        self.assertEqual(
            {key: self.roles["xardas"][key] for key in ("tier", "effort")},
            {"tier": "balanced", "effort": "high"},
        )
        self.assertEqual(
            {key: self.roles["lee"][key] for key in ("tier", "effort", "sandbox")},
            {"tier": "review", "effort": "high", "sandbox": "read-only"},
        )
        for provider_name, provider in self.providers.items():
            with self.subTest(provider=provider_name):
                self.assertEqual(set(provider["tiers"]), {"fast", "balanced", "deep", "review"})
                self.assertEqual(provider["tiers"]["review"], provider["tiers"]["deep"])
                self.assertTrue(provider["supported_harnesses"])
                self.assertLessEqual(set(provider["supported_harnesses"]), set(HARNESSES))

    def install(self, *args: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        agent_root = root / "agent"
        command = [
            sys.executable,
            str(INSTALLER),
            "--portable",
            str(agent_root),
            "--root-dir",
            str(root),
            "--no-plugin-prompt",
            "--no-strict",
            *args,
        ]
        subprocess.run(command, cwd=REPO_ROOT, check=True, text=True, capture_output=True)
        return agent_root

    def test_each_provider_generates_integral_supported_harness_install(self) -> None:
        for provider_name, provider in self.providers.items():
            with self.subTest(provider=provider_name):
                harnesses = provider["supported_harnesses"]
                agent_root = self.install(
                    "--harness",
                    ",".join(harnesses),
                    "--provider",
                    provider_name,
                )

                env = read_env(agent_root / ".env")
                self.assertEqual(env["AGENT_PROVIDER"], provider_name)
                self.assertEqual(env["AGENT_HARNESSES"], ",".join(harnesses))
                for tier, model in provider["tiers"].items():
                    self.assertEqual(env[f"AGENT_MODEL_{tier.upper()}"], model)
                self.assertEqual(env["AGENT_MODEL_DEFAULT"], provider["default_model"])
                self.assertNotIn("AGENT_MODEL_DESIGN", env)

                models = json.loads((agent_root / ".config" / "models.json").read_text(encoding="utf-8"))
                self.assertEqual(models, {"provider": provider_name, "default": provider["default_model"], "tiers": provider["tiers"]})
                self.assertFalse((agent_root / ".agent-v2").exists())

                self.assertFalse((agent_root / "install.sh").exists())
                self.assertFalse((agent_root / "scripts").exists())
                self.assertFalse((agent_root / "config").exists())
                self.assertFalse((agent_root / "core").exists())

                if "codex" in harnesses:
                    self.assert_codex_install(agent_root, provider)
                    hooks = json.loads((agent_root / ".codex" / "hooks.json").read_text(encoding="utf-8"))
                    session_command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
                    self.assertNotIn("git rev-parse", session_command)
                    self.assertIn("$PWD/.codex/hooks/session_context.py", session_command)
                    codex_config = (agent_root / ".codex" / "config.toml").read_text(encoding="utf-8")
                    self.assertIn("multi_agent = true", codex_config)
                if "claude" in harnesses:
                    self.assert_claude_install(agent_root, provider)
                if "opencode" in harnesses:
                    self.assert_opencode_install(agent_root, provider)

    def test_explicit_provider_rejects_unsupported_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            agent_root = root / "agent"
            result = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--portable",
                    str(agent_root),
                    "--root-dir",
                    str(root),
                    "--no-plugin-prompt",
                    "--no-strict",
                    "--harness",
                    "opencode",
                    "--provider",
                    "codex-native",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not support harness(es): opencode", result.stderr)
            self.assertFalse(agent_root.exists())

    def test_single_harness_defaults_to_native_provider(self) -> None:
        expected = {
            "codex": "codex-native",
            "claude": "anthropic-native",
            "opencode": "opencode-native",
        }
        for harness, provider_name in expected.items():
            with self.subTest(harness=harness):
                agent_root = self.install("--harness", harness)
                env = read_env(agent_root / ".env")
                self.assertEqual(env["AGENT_PROVIDER"], provider_name)
                self.assertEqual(env["AGENT_HARNESSES"], harness)
                for tier, model in self.providers[provider_name]["tiers"].items():
                    self.assertEqual(env[f"AGENT_MODEL_{tier.upper()}"], model)

    def test_optional_plugins_are_logged_and_rendered_when_explicit(self) -> None:
        agent_root = self.install(
            "--harness",
            "opencode",
            "--plugin",
            "graphify",
            "--plugin",
            "context-mode",
            "--plugin",
            "playwright",
            "--plugin",
            "gradle-wrapper",
        )
        env = read_env(agent_root / ".env")
        self.assertEqual(env["AGENT_PLUGINS"], "graphify,context-mode,playwright,gradle-wrapper")
        self.assertIn("graphify=enabled:", env["AGENT_OPTIONAL_DEPS"])
        self.assertIn("context-mode=enabled:", env["AGENT_OPTIONAL_DEPS"])
        self.assertTrue((agent_root / ".opencode" / "plugins" / "graphify.js").exists())
        self.assertTrue((agent_root / ".opencode" / "plugins" / "gradle-wrapper-redirect.js").exists())
        self.assertIn("build|test|integrationTest|check", (agent_root / ".opencode" / "plugins" / "gradle-wrapper-redirect.js").read_text(encoding="utf-8"))
        config = json.loads((agent_root / ".opencode" / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(config["mcp"]["context-mode"]["command"], ["context-mode"])
        self.assertEqual(config["mcp"]["playwright"]["command"], ["playwright-mcp"])

    def test_profiles_and_path_cli_are_generated(self) -> None:
        agent_root = self.install(
            "--harness",
            ",".join(HARNESSES),
            "--plugin",
            "gradle-wrapper",
        )

        codex_env = read_env(agent_root / "codex.env")
        claude_env = read_env(agent_root / "claude.env")
        opencode_env = read_env(agent_root / "opencode.env")
        self.assertEqual(codex_env["AGENT_HARNESSES"], "codex")
        self.assertEqual(codex_env["AGENT_PROVIDER"], "codex-native")
        self.assertEqual(codex_env["AGENT_MODEL_DEFAULT"], self.providers["codex-native"]["default_model"])
        self.assertEqual(claude_env["AGENT_HARNESSES"], "claude")
        self.assertEqual(claude_env["AGENT_PROVIDER"], "anthropic-native")
        self.assertEqual(claude_env["AGENT_MODEL_DEFAULT"], self.providers["anthropic-native"]["default_model"])
        self.assertEqual(opencode_env["AGENT_HARNESSES"], "opencode")
        self.assertEqual(opencode_env["AGENT_PROVIDER"], "opencode-native")
        self.assertEqual(opencode_env["AGENT_MODEL_DEFAULT"], self.providers["opencode-native"]["default_model"])
        codex_config = (agent_root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn(
            f'model = "{self.providers["codex-native"]["default_model"]}"',
            codex_config,
        )
        claude_settings = json.loads((agent_root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(claude_settings["model"], self.providers["anthropic-native"]["default_model"])
        opencode_config = json.loads((agent_root / ".opencode" / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(opencode_config["model"], self.providers["opencode-native"]["default_model"])

        cli = agent_root / ".config" / "bin" / "coding-colony"
        self.assertTrue(cli.is_file())
        self.assertTrue(cli.stat().st_mode & 0o111)
        self.assertIn("AGENT_TARGET_REPO", cli.read_text(encoding="utf-8"))

    def test_path_entry_is_added_once(self) -> None:
        spec = importlib.util.spec_from_file_location("agent_setup_for_test", INSTALLER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            startup_file = root / ".zshrc"
            agent_root = root / "agent"
            module.add_coding_colony_to_path(agent_root, startup_file)
            module.add_coding_colony_to_path(agent_root, startup_file)

            content = startup_file.read_text(encoding="utf-8")
            self.assertEqual(content.count("# Added by agent-v2: coding-colony"), 1)
            self.assertEqual(content.count("export PATH="), 1)

    def test_gradle_hook_uses_target_cwd_from_tool_event(self) -> None:
        agent_root = self.install(
            "--harness",
            "codex",
            "--plugin",
            "gradle-wrapper",
        )
        target_repo = agent_root.parent / "target-repo"
        target_repo.mkdir()
        hook = agent_root / ".codex" / "hooks" / "pre_tool_use_policy.py"

        result = subprocess.run(
            [sys.executable, str(hook)],
            cwd=agent_root,
            input=json.dumps({
                "cwd": str(agent_root),
                "tool_input": {"command": "./gradlew test"},
            }),
            check=True,
            text=True,
            capture_output=True,
            env={**os.environ, "AGENT_TARGET_REPO": str(target_repo)},
        )

        output = json.loads(result.stdout)
        updated = output["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertTrue(updated.endswith(f"{target_repo} test"))
        self.assertNotIn(f" {agent_root} test", updated)

        build_result = subprocess.run(
            [sys.executable, str(hook)],
            cwd=agent_root,
            input=json.dumps({"tool_input": {"command": "./gradlew build"}}),
            check=True,
            text=True,
            capture_output=True,
            env={**os.environ, "AGENT_TARGET_REPO": str(target_repo)},
        )
        build_updated = json.loads(build_result.stdout)["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertTrue(build_updated.endswith(f"{target_repo} build"))

    def test_gradle_summary_falls_back_to_shell_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            gradlew = repo / "gradlew"
            gradlew.write_text("#!/bin/sh\nprintf '%s\\n' 'BUILD SUCCESSFUL'\n", encoding="utf-8")
            gradlew.chmod(0o755)
            result = subprocess.run(
                [str(REPO_ROOT / "scripts" / "run-gradle-summarized.sh"), "/Users/mikolaj.cekut", "build"],
                cwd=repo,
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertIn("RESULT=SUCCESS", result.stdout)
            self.assertIn(f"{repo}/gradlew", result.stdout)

    def test_reinstall_preserves_existing_model_env_overrides_without_explicit_provider(self) -> None:
        agent_root = self.install("--harness", "codex")
        env_path = agent_root / ".env"
        env_text = env_path.read_text(encoding="utf-8")
        env_text = env_text.replace(
            "AGENT_MODEL_DEEP=gpt-5.5",
            "AGENT_MODEL_DEEP=openai/gpt-5.5",
        )
        env_path.write_text(env_text, encoding="utf-8")

        subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--portable",
                str(agent_root),
                "--root-dir",
                str(agent_root.parent),
                "--no-plugin-prompt",
                "--no-strict",
                "--harness",
                "codex",
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        env = read_env(env_path)
        self.assertEqual(env["AGENT_MODEL_DEEP"], "openai/gpt-5.5")
        self.assertEqual(read_env(agent_root / "codex.env")["AGENT_MODEL_DEEP"], "openai/gpt-5.5")
        codex_lester = (agent_root / ".codex" / "agents" / "lester.toml").read_text(encoding="utf-8")
        self.assertIn('model = "openai/gpt-5.5"', codex_lester)
        codex_scout = (agent_root / ".codex" / "agents" / "scout.toml").read_text(encoding="utf-8")
        self.assertIn('model = "gpt-5.4-mini"', codex_scout)

    def test_reinstall_preserves_existing_default_model_override_without_explicit_provider(self) -> None:
        agent_root = self.install("--harness", "codex")
        env_path = agent_root / ".env"
        env_path.write_text(
            env_path.read_text(encoding="utf-8").replace(
                "AGENT_MODEL_DEFAULT=gpt-5.4",
                "AGENT_MODEL_DEFAULT=custom-default-model",
            ),
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--portable",
                str(agent_root),
                "--root-dir",
                str(agent_root.parent),
                "--no-plugin-prompt",
                "--no-strict",
                "--harness",
                "codex",
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        config = (agent_root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('model = "custom-default-model"', config)

    def test_reinstall_renders_single_harness_profile_model_override(self) -> None:
        agent_root = self.install("--harness", "claude")
        profile_path = agent_root / "claude.env"
        profile_path.write_text(
            profile_path.read_text(encoding="utf-8").replace(
                "AGENT_MODEL_DEEP=opus",
                "AGENT_MODEL_DEEP=custom-opus",
            ),
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--portable",
                str(agent_root),
                "--root-dir",
                str(agent_root.parent),
                "--no-plugin-prompt",
                "--no-strict",
                "--harness",
                "claude",
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        self.assertEqual(read_env(profile_path)["AGENT_MODEL_DEEP"], "custom-opus")
        lester = frontmatter(agent_root / ".claude" / "agents" / "lester.md")
        self.assertEqual(lester["model"], "custom-opus")

    def test_reinstall_removes_only_retired_generated_artifacts(self) -> None:
        agent_root = self.install("--harness", ",".join(HARNESSES))
        retired = (
            ".codex/agents/nadia.toml",
            ".codex/agents/riordian.toml",
            ".agents/skills/design/SKILL.md",
            ".agents/skills/implement-spike/SKILL.md",
            ".claude/agents/nadia.md",
            ".claude/agents/riordian.md",
            ".claude/skills/design/SKILL.md",
            ".claude/skills/implement-spike/SKILL.md",
            ".opencode/agents/nadia.md",
            ".opencode/agents/riordian.md",
            ".opencode/commands/design.md",
            ".opencode/commands/implement-spike.md",
        )
        user_files = (
            ".codex/agents/custom.toml",
            ".agents/skills/custom/SKILL.md",
            ".claude/agents/custom.md",
            ".claude/skills/custom/SKILL.md",
            ".opencode/agents/custom.md",
            ".opencode/commands/custom.md",
        )
        for relative_path in (*retired, *user_files):
            path = agent_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("preserve only when user-owned\n", encoding="utf-8")

        subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--portable",
                str(agent_root),
                "--root-dir",
                str(agent_root.parent),
                "--no-plugin-prompt",
                "--no-strict",
                "--harness",
                ",".join(HARNESSES),
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        for relative_path in retired:
            self.assertFalse((agent_root / relative_path).exists(), relative_path)
        for relative_path in user_files:
            self.assertEqual(
                (agent_root / relative_path).read_text(encoding="utf-8"),
                "preserve only when user-owned\n",
            )

    def test_codex_session_hook_refreshes_models_from_env(self) -> None:
        agent_root = self.install("--harness", "codex")
        env_path = agent_root / ".env"
        env_text = env_path.read_text(encoding="utf-8").replace(
            "AGENT_MODEL_DEEP=gpt-5.5",
            "AGENT_MODEL_DEEP=dynamic-deep-model",
        ).replace(
            "AGENT_MODEL_DEFAULT=gpt-5.4",
            "AGENT_MODEL_DEFAULT=dynamic-default-model",
        )
        env_path.write_text(env_text, encoding="utf-8")

        hook = agent_root / ".codex" / "hooks" / "session_context.py"
        subprocess.run(
            [sys.executable, str(hook)],
            cwd=agent_root,
            input=json.dumps({"hook_event_name": "session_start"}),
            check=True,
            text=True,
            capture_output=True,
        )

        config = (agent_root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('model = "dynamic-default-model"', config)
        lester = (agent_root / ".codex" / "agents" / "lester.toml").read_text(encoding="utf-8")
        self.assertIn('model = "dynamic-deep-model"', lester)

    def test_install_missing_plugin_runs_configured_installer_and_redetects(self) -> None:
        spec = importlib.util.spec_from_file_location("agent_setup_for_test", INSTALLER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        plugin_defs = {
            "graphify": {
                "command_env": "GRAPHIFY_COMMAND",
                "install_command": ["pipx", "install", "graphifyy"],
            }
        }
        installed = {"value": False}
        commands: list[list[str]] = []

        def fake_which(command: str) -> str | None:
            if command == "pipx":
                return "/usr/bin/pipx"
            if command == "graphify" and installed["value"]:
                return "/tmp/bin/graphify"
            return None

        def fake_run(command: list[str], check: bool) -> object:
            commands.append(command)
            installed["value"] = True
            return object()

        original_which = module.shutil.which
        original_run = module.subprocess.run
        try:
            module.shutil.which = fake_which
            module.subprocess.run = fake_run
            plugins, optional_deps = module.select_plugins(
                ["graphify"],
                plugin_defs,
                prompt_for_plugins=False,
                install_missing_plugins=True,
                prompt_for_install=False,
                dry_run=False,
            )
        finally:
            module.shutil.which = original_which
            module.subprocess.run = original_run

        self.assertEqual(plugins, ["graphify"])
        self.assertEqual(commands, [["pipx", "install", "graphifyy"]])
        self.assertEqual(optional_deps["graphify"]["availability"], "available")
        self.assertEqual(optional_deps["graphify"]["path"], "/tmp/bin/graphify")
        self.assertEqual(optional_deps["graphify"]["install_state"], "installed")

    def test_graphify_post_install_registers_each_selected_platform(self) -> None:
        spec = importlib.util.spec_from_file_location("agent_setup_for_test", INSTALLER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        commands: list[list[str]] = []

        def fake_which(command: str) -> str | None:
            return "/tmp/bin/graphify" if command == "graphify" else None

        def fake_run(command: list[str], check: bool) -> object:
            commands.append(command)
            return object()

        original_which = module.shutil.which
        original_run = module.subprocess.run
        try:
            module.shutil.which = fake_which
            module.subprocess.run = fake_run
            optional_deps = {"graphify": {"state": "enabled", "availability": "available"}}
            module.configure_selected_plugins(
                ["graphify"],
                {"graphify": {"post_install_command": ["graphify", "install", "--platform", "{platform}"]}},
                optional_deps,
                ["opencode", "codex"],
                dry_run=False,
            )
        finally:
            module.shutil.which = original_which
            module.subprocess.run = original_run

        self.assertEqual(
            commands,
            [
                ["graphify", "install", "--platform", "opencode"],
                ["graphify", "install", "--platform", "codex"],
            ],
        )
        self.assertEqual(optional_deps["graphify"]["configure_state"], "configured:opencode+codex")

    def assert_codex_install(self, agent_root: Path, provider: dict) -> None:
        config = (agent_root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn(f'model = "{provider["default_model"]}"', config)
        self.assertIn("max_threads = 3", config)
        self.assertIn("max_depth = 2", config)
        self.assertEqual(
            {path.stem for path in (agent_root / ".codex" / "agents").glob("*.toml")},
            set(self.roles),
        )
        role_contents: dict[str, str] = {}
        for role_name, role in self.roles.items():
            content = (agent_root / ".codex" / "agents" / f"{role_name}.toml").read_text(encoding="utf-8")
            role_contents[role_name] = content
            self.assertIn(f"name = \"{role_name}\"", content)
            self.assertIn(f'model = "{provider["tiers"][role["tier"]]}"', content)
            self.assertIn(f'model_reasoning_effort = "{role["effort"]}"', content)
            self.assertIn(f'sandbox_mode = "{role["sandbox"]}"', content)
            self.assertIn(f"Model tier: {role['tier']}", content)
            self.assertIn("Role workflow:", content)
            self.assertIn(self.shared_instructions, content)

        skill_root = agent_root / ".agents" / "skills"
        self.assertEqual({path.name for path in skill_root.iterdir()}, set(COMMAND_TO_ROLE))
        for command, role in COMMAND_TO_ROLE.items():
            path = skill_root / command / "SKILL.md"
            metadata = frontmatter(path)
            content = path.read_text(encoding="utf-8")
            self.assertEqual(metadata["name"], command)
            self.assertEqual(metadata["description"], f"Run /{command} through the {role} role workflow.")
            self.assertNotIn("Role workflow:", content)
            if role == "gorn":
                self.assertIn("Call `spawn_agent` exactly once", content)
                self.assertIn("one `gorn` custom agent", content)
                self.assertIn('agent_type="gorn"', content)
                self.assertIn("mandatory lee review/remediation loop", content.replace("`", "").lower())
                self.assertIn("verification", content)
            else:
                self.assertIn(f'agent_type="{role}"', content)
                if role in {"rhobar", "milten", "lester", "xardas"}:
                    self.assertIn("at most one `scout`", content)
                    self.assertNotIn("is a leaf", content)
                else:
                    self.assertIn("is a leaf", content)
                self.assertIn("Call `spawn_agent` exactly once", content)
            self.assertNotIn("agent:", content)
        self.assert_role_workflow_contracts(role_contents)

    def assert_claude_install(self, agent_root: Path, provider: dict) -> None:
        settings = json.loads((agent_root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["model"], provider["default_model"])
        self.assertEqual(
            {path.stem for path in (agent_root / ".claude" / "agents").glob("*.md")},
            set(self.roles),
        )
        role_contents: dict[str, str] = {}
        for role_name, role in self.roles.items():
            path = agent_root / ".claude" / "agents" / f"{role_name}.md"
            metadata = frontmatter(path)
            self.assertEqual(metadata["name"], role_name)
            self.assertEqual(metadata["model"], provider["tiers"][role["tier"]])
            self.assertEqual(metadata["effort"], role["effort"])
            content = path.read_text(encoding="utf-8")
            role_contents[role_name] = content
            self.assertIn(f"Model tier: {role['tier']}", content)
            self.assertIn("Role workflow:", content)
            self.assertIn(self.shared_instructions, content)
            self.assert_no_provider_models_in_agent_definition(body_without_frontmatter(path), provider)
            if role["sandbox"] == "read-only":
                self.assertEqual(metadata["permissionMode"], "plan")
                self.assertIn("Write", metadata["disallowedTools"])
                self.assertIn("Edit", metadata["disallowedTools"])

        skill_root = agent_root / ".claude" / "skills"
        self.assertEqual({path.name for path in skill_root.iterdir()}, set(COMMAND_TO_ROLE))
        for command, role in COMMAND_TO_ROLE.items():
            path = skill_root / command / "SKILL.md"
            metadata = frontmatter(path)
            self.assertEqual(metadata["name"], command)
            self.assertEqual(metadata["description"], f"Run /{command} through the {role} role workflow.")
            self.assertEqual(metadata["context"], "fork")
            self.assertEqual(metadata["agent"], role)
            self.assertEqual(metadata["disable-model-invocation"], "true")
            body = body_without_frontmatter(path)
            self.assertIn("$ARGUMENTS", body)
            self.assertNotIn("Role workflow:", body)
        self.assert_role_workflow_contracts(role_contents)

    def assert_opencode_install(self, agent_root: Path, provider: dict) -> None:
        config = json.loads((agent_root / ".opencode" / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(config["model"], provider["default_model"])
        self.assertNotIn("agent", config)
        self.assertNotIn("command", config)
        self.assertIn("./plugins/model-tier-resolver.js", config["plugin"])
        resolver = (agent_root / ".opencode" / "plugins" / "model-tier-resolver.js").read_text(encoding="utf-8")
        self.assertIn("AGENT_MODEL_DEEP", resolver)
        self.assertIn("config.agent", resolver)
        self.assertEqual(
            {path.stem for path in (agent_root / ".opencode" / "agents").glob("*.md")},
            set(self.roles),
        )
        role_contents: dict[str, str] = {}
        for role_name, role in self.roles.items():
            path = agent_root / ".opencode" / "agents" / f"{role_name}.md"
            metadata = frontmatter(path)
            self.assertEqual(metadata["model"], role["tier"])
            self.assertEqual(metadata["x-agent-tier"], role["tier"])
            self.assertEqual(metadata["mode"], "subagent")
            raw_content = path.read_text(encoding="utf-8")
            content = body_without_frontmatter(path)
            role_contents[role_name] = content
            self.assertIn(f"Model tier: {role['tier']}", content)
            self.assertIn("Role workflow:", content)
            self.assertIn(self.shared_instructions, content)
            self.assert_no_provider_models_in_agent_definition(content, provider)
            self.assertIn("permission:", raw_content)
            self.assertIn('"*": deny', raw_content)
            if role["sandbox"] == "read-only":
                self.assertIn("edit: deny", raw_content)
                self.assertIn("bash: deny", raw_content)
            if role_name in {"rhobar", "milten", "lester", "xardas"}:
                self.assertIn("scout: allow", raw_content)
            elif role_name == "gorn":
                self.assertIn("lee: allow", raw_content)
            else:
                self.assertNotIn("scout: allow", raw_content)
                self.assertNotIn("lee: allow", raw_content)

        command_root = agent_root / ".opencode" / "commands"
        self.assertEqual({path.stem for path in command_root.glob("*.md")}, set(COMMAND_TO_ROLE))
        for command, role in COMMAND_TO_ROLE.items():
            metadata = frontmatter(command_root / f"{command}.md")
            self.assertEqual(metadata["agent"], role)
            self.assertEqual(metadata["subtask"], "true")
            self.assertNotIn("model", metadata)
        self.assert_role_workflow_contracts(role_contents)

    def assert_role_workflow_contracts(self, role_contents: dict[str, str]) -> None:
        self.assertIn("READY", role_contents["milten"])
        self.assertIn("NEEDS_INPUT", role_contents["milten"])
        self.assertIn("READY", role_contents["lester"])
        self.assertIn("BLOCKED", role_contents["lester"])
        self.assertIn("traceability", role_contents["lester"].lower())
        self.assertIn("startup", role_contents["gorn"].lower())
        self.assertIn("bootstrap", role_contents["gorn"].lower())
        self.assertIn("startup", role_contents["gomez"].lower())
        self.assertIn("Verdict: PASS", role_contents["gomez"])
        self.assertIn("PASS", role_contents["gorn"])
        self.assertIn("repeat", role_contents["gorn"].lower())
        self.assertIn("graphify-out/needs_update", role_contents["gorn"])
        self.assertIn("graphify-out/needs_update", role_contents["xardas"])
        self.assertIn("<graphify-command> update <repo-path>", role_contents["xardas"])
        self.assertIn("even when no marker exists", role_contents["xardas"])
        self.assertIn("graphify-out/CODE_CONVENTIONS.md", role_contents["xardas"])
        self.assertIn("repo-local `AGENTS.md` managed section", role_contents["xardas"])

    def assert_no_provider_models_in_agent_definition(self, content: str, provider: dict) -> None:
        for model in provider["tiers"].values():
            self.assertNotIn(model, content)


if __name__ == "__main__":
    unittest.main()
