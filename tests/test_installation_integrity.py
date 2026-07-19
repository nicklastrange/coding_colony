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
    "design": "nadia",
    "implement": "gorn",
    "implement-spike": "riordian",
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

    def test_each_provider_generates_integral_all_harness_install(self) -> None:
        for provider_name, provider in self.providers.items():
            with self.subTest(provider=provider_name):
                agent_root = self.install(
                    "--harness",
                    ",".join(HARNESSES),
                    "--provider",
                    provider_name,
                )

                env = read_env(agent_root / ".env")
                self.assertEqual(env["AGENT_PROVIDER"], provider_name)
                self.assertEqual(env["AGENT_HARNESSES"], ",".join(HARNESSES))
                for tier, model in provider["tiers"].items():
                    self.assertEqual(env[f"AGENT_MODEL_{tier.upper()}"], model)
                self.assertEqual(env["AGENT_MODEL_DEFAULT"], provider["default_model"])

                models = json.loads((agent_root / ".config" / "models.json").read_text(encoding="utf-8"))
                self.assertEqual(models, {"provider": provider_name, "default": provider["default_model"], "tiers": provider["tiers"]})
                self.assertFalse((agent_root / ".agent-v2").exists())

                self.assertFalse((agent_root / "install.sh").exists())
                self.assertFalse((agent_root / "scripts").exists())
                self.assertFalse((agent_root / "config").exists())
                self.assertFalse((agent_root / "core").exists())

                self.assert_codex_install(agent_root, provider)
                hooks = json.loads((agent_root / ".codex" / "hooks.json").read_text(encoding="utf-8"))
                session_command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
                self.assertNotIn("git rev-parse", session_command)
                self.assertIn("$PWD/.codex/hooks/session_context.py", session_command)
                codex_config = (agent_root / ".codex" / "config.toml").read_text(encoding="utf-8")
                self.assertIn("multi_agent = true", codex_config)
                self.assert_claude_install(agent_root, provider)
                self.assert_opencode_install(agent_root, provider)

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
            "codex,opencode",
            "--plugin",
            "gradle-wrapper",
        )

        codex_env = read_env(agent_root / "codex.env")
        opencode_env = read_env(agent_root / "opencode.env")
        self.assertEqual(codex_env["AGENT_HARNESSES"], "codex")
        self.assertEqual(codex_env["AGENT_PROVIDER"], "codex-native")
        self.assertEqual(codex_env["AGENT_MODEL_DEFAULT"], self.providers["codex-native"]["default_model"])
        self.assertEqual(opencode_env["AGENT_HARNESSES"], "opencode")
        self.assertEqual(opencode_env["AGENT_PROVIDER"], "opencode-native")
        self.assertEqual(opencode_env["AGENT_MODEL_DEFAULT"], self.providers["opencode-native"]["default_model"])

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
        codex_xardas = (agent_root / ".codex" / "agents" / "xardas.toml").read_text(encoding="utf-8")
        self.assertIn('model = "openai/gpt-5.5"', codex_xardas)
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
        xardas = (agent_root / ".codex" / "agents" / "xardas.toml").read_text(encoding="utf-8")
        self.assertIn('model = "dynamic-deep-model"', xardas)

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
        for role_name, role in self.roles.items():
            content = (agent_root / ".codex" / "agents" / f"{role_name}.toml").read_text(encoding="utf-8")
            self.assertIn(f"name = \"{role_name}\"", content)
            self.assertIn(f'model = "{provider["tiers"][role["tier"]]}"', content)
            self.assertIn(f'model_reasoning_effort = "{role["effort"]}"', content)
            self.assertIn(f"Model tier: {role['tier']}", content)
            self.assertIn("Role workflow:", content)
        xardas = (agent_root / ".codex" / "agents" / "xardas.toml").read_text(encoding="utf-8")
        self.assertIn("graphify-out/CODE_CONVENTIONS.md", xardas)
        self.assertIn("repo-local `AGENTS.md` managed section", xardas)
        for command, role in COMMAND_TO_ROLE.items():
            content = (agent_root / ".agents" / "skills" / command / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(f"`{role}` custom agent", content)
            if role == "gorn":
                self.assertIn("spawn exactly one `gorn` agent", content)
                self.assertIn("`gorn` owns implementation, review coordination, remediation, and verification", content)
                self.assertIn("launch `lee` for review", content)
                self.assertIn("send_input` or `resume_agent", content)
            else:
                self.assertIn(f'agent_type="{role}"', content)
                self.assertIn(f"The spawned `{role}`", content)
                if role in {"milten", "lester"}:
                    self.assertIn("may spawn the `scout` agent", content)
                    self.assertIn("context-window tokens", content)
                    self.assertNotIn("leaf executor", content)
                else:
                    self.assertIn("agent is the leaf executor", content)
                self.assertIn("Call `spawn_agent` exactly once", content)
            self.assertNotIn("agent:", content)
        bookskeeper = (agent_root / ".agents" / "skills" / "bookskeeper" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("graphify <repo-path> --mode deep", bookskeeper)
        self.assertIn("graphify-out/BUSINESS_LOGIC.md", bookskeeper)

    def assert_claude_install(self, agent_root: Path, provider: dict) -> None:
        settings = json.loads((agent_root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["model"], provider["default_model"])
        for role_name, role in self.roles.items():
            path = agent_root / ".claude" / "agents" / f"{role_name}.md"
            metadata = frontmatter(path)
            self.assertEqual(metadata["name"], role_name)
            self.assertEqual(metadata["x-agent-tier"], role["tier"])
            content = path.read_text(encoding="utf-8")
            self.assertIn(f"Model tier: {role['tier']}", content)
            self.assertIn("Role workflow:", content)
            self.assert_no_provider_models_in_agent_definition(content, provider)

    def assert_opencode_install(self, agent_root: Path, provider: dict) -> None:
        config = json.loads((agent_root / ".opencode" / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(config["model"], provider["default_model"])
        self.assertNotIn("agent", config)
        self.assertNotIn("command", config)
        self.assertIn("./plugins/model-tier-resolver.js", config["plugin"])
        resolver = (agent_root / ".opencode" / "plugins" / "model-tier-resolver.js").read_text(encoding="utf-8")
        self.assertIn("AGENT_MODEL_DEEP", resolver)
        self.assertIn("config.agent", resolver)
        for role_name, role in self.roles.items():
            path = agent_root / ".opencode" / "agents" / f"{role_name}.md"
            metadata = frontmatter(path)
            self.assertEqual(metadata["model"], role["tier"])
            self.assertEqual(metadata["x-agent-tier"], role["tier"])
            self.assertEqual(metadata["mode"], "all")
            content = body_without_frontmatter(path)
            self.assertIn(f"Model tier: {role['tier']}", content)
            self.assertIn("Role workflow:", content)
            self.assert_no_provider_models_in_agent_definition(content, provider)
        xardas_content = body_without_frontmatter(agent_root / ".opencode" / "agents" / "xardas.md")
        self.assertIn("graphify-out/CODE_CONVENTIONS.md", xardas_content)
        self.assertIn("repo-local `AGENTS.md` managed section", xardas_content)
        self.assertNotIn("Keep generated task docs under AGENT_ROOT/docs", xardas_content)

        for command, role in COMMAND_TO_ROLE.items():
            metadata = frontmatter(agent_root / ".opencode" / "commands" / f"{command}.md")
            self.assertEqual(metadata["agent"], role)
            self.assertNotIn("model", metadata)

    def assert_no_provider_models_in_agent_definition(self, content: str, provider: dict) -> None:
        for model in provider["tiers"].values():
            self.assertNotIn(model, content)


if __name__ == "__main__":
    unittest.main()
