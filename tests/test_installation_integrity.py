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
MODEL_TIERS = ("fast", "balanced", "deep")
DEVELOPMENT_SKILLS = {"flutter", "kotlin", "spring-boot"}
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
            value = value.strip()
            if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
                value = json.loads(value)
            data[key.strip()] = value
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
            {key: self.roles["gorn"][key] for key in ("tier", "effort")},
            {"tier": "fast", "effort": "medium"},
        )
        self.assertEqual(
            {key: self.roles["lester"][key] for key in ("tier", "effort")},
            {"tier": "deep", "effort": "max"},
        )
        self.assertEqual(
            {key: self.roles["xardas"][key] for key in ("tier", "effort")},
            {"tier": "balanced", "effort": "high"},
        )
        self.assertEqual(
            {key: self.roles["lee"][key] for key in ("tier", "effort", "sandbox")},
            {"tier": "deep", "effort": "high", "sandbox": "read-only"},
        )
        for provider_name, provider in self.providers.items():
            with self.subTest(provider=provider_name):
                self.assertEqual(set(provider["tiers"]), set(MODEL_TIERS))
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
        return agent_root.resolve()

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
                self.assertFalse(any(key.startswith("AGENT_MODEL_") for key in env))

                colony = json.loads((agent_root / "coding-colony.json").read_text(encoding="utf-8"))
                expected_models = {"default": provider["default_model"], **provider["tiers"]}
                self.assertEqual(colony["models"], {harness: expected_models for harness in harnesses})
                self.assertEqual(
                    colony["agents"],
                    {
                        role_name: {"model": role["tier"], "reasoning": role["effort"]}
                        for role_name, role in self.roles.items()
                    },
                )
                self.assertFalse((agent_root / ".config" / "models.json").exists())
                for harness in HARNESSES:
                    self.assertFalse((agent_root / f"{harness}.env").exists())
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
                    self.assertIn("$AGENT_ROOT/.codex/hooks/session_context.py", session_command)
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
                provider = self.providers[provider_name]
                config = json.loads((agent_root / "coding-colony.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    config["models"][harness],
                    {"default": provider["default_model"], **provider["tiers"]},
                )

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

    def test_central_config_and_path_cli_are_generated(self) -> None:
        agent_root = self.install(
            "--harness",
            ",".join(HARNESSES),
            "--plugin",
            "gradle-wrapper",
        )

        self.assertEqual((agent_root / ".env").stat().st_mode & 0o777, 0o600)
        colony = json.loads((agent_root / "coding-colony.json").read_text(encoding="utf-8"))
        for harness in HARNESSES:
            provider = self.providers[f"{harness}-native" if harness != "claude" else "anthropic-native"]
            self.assertEqual(
                colony["models"][harness],
                {"default": provider["default_model"], **provider["tiers"]},
            )
            self.assertFalse((agent_root / f"{harness}.env").exists())
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

    def test_cli_launches_each_harness_in_target_repo_without_mutating_shared_env(self) -> None:
        agent_root = self.install("--harness", ",".join(HARNESSES))
        target_repo = agent_root.parent / "Demo Project"
        target_repo.mkdir()
        docs_dir = agent_root / "docs" / "demo-project"
        env_path = agent_root / ".env"
        env_path.write_text(env_path.read_text(encoding="utf-8") + "CUSTOM_SHARED=kept\n", encoding="utf-8")
        shared_env = env_path.read_text(encoding="utf-8")
        colony_path = agent_root / "coding-colony.json"
        colony = json.loads(colony_path.read_text(encoding="utf-8"))
        for harness in HARNESSES:
            colony["models"][harness]["default"] = f"{harness}-default"
            colony["models"][harness]["deep"] = f"{harness}-deep"
        colony["agents"]["gorn"] = {"model": "deep", "reasoning": "max"}
        colony_path.write_text(json.dumps(colony, indent=2) + "\n", encoding="utf-8")
        central_config = colony_path.read_text(encoding="utf-8")
        user_home = agent_root.parent / "user-home"
        user_codex_home = user_home / ".codex"
        user_codex_home.mkdir(parents=True)
        user_config = (
            'model = "user-global-model"\n'
            '[features]\n'
            'web_search_request = true\n'
            '[mcp_servers.user_global]\n'
            'command = "user-global-mcp"\n'
        )
        (user_codex_home / "config.toml").write_text(user_config, encoding="utf-8")
        (user_codex_home / "auth.json").write_text('{"auth_mode":"apikey"}\n', encoding="utf-8")
        user_codex_snapshot = {
            path.name: path.read_text(encoding="utf-8") for path in user_codex_home.iterdir()
        }

        fake_bin = agent_root.parent / "bin"
        fake_bin.mkdir()
        fake_harness = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

Path(os.environ["CAPTURE"]).write_text(json.dumps({
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "provider": os.environ.get("AGENT_PROVIDER"),
    "shared": os.environ.get("CUSTOM_SHARED"),
    "codex_home": os.environ.get("CODEX_HOME"),
    "claude_config_dir": os.environ.get("CLAUDE_CONFIG_DIR"),
    "opencode_config_dir": os.environ.get("OPENCODE_CONFIG_DIR"),
    "opencode_config_content": os.environ.get("OPENCODE_CONFIG_CONTENT"),
    "project_slug": os.environ.get("AGENT_PROJECT_SLUG"),
    "project_docs": os.environ.get("AGENT_PROJECT_DOCS"),
}), encoding="utf-8")
"""
        for harness in HARNESSES:
            executable = fake_bin / harness
            executable.write_text(fake_harness, encoding="utf-8")
            executable.chmod(0o755)

        results: dict[str, dict] = {}
        for harness in HARNESSES:
            capture = agent_root.parent / f"{harness}.json"
            launch_env = {
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                "CAPTURE": str(capture),
                "HOME": str(user_home),
                "CODEX_HOME": str(user_codex_home),
                "OPENCODE_CONFIG_CONTENT": '{"theme":"dark","permission":{"bash":"ask","external_directory":{"/existing/**":"deny"}}}',
            }
            launch_env.pop("AGENT_PROVIDER", None)
            launch = [
                str(agent_root / ".config" / "bin" / "coding-colony"),
                harness,
                "--repo",
                str(target_repo),
            ]
            if harness == "codex":
                launch.append("--yolo")
            launch.extend(["--", "--flag", harness])
            subprocess.run(
                launch,
                cwd=REPO_ROOT,
                check=True,
                text=True,
                capture_output=True,
                env=launch_env,
            )
            results[harness] = json.loads(capture.read_text(encoding="utf-8"))

        self.assertEqual(env_path.read_text(encoding="utf-8"), shared_env)
        self.assertEqual(colony_path.read_text(encoding="utf-8"), central_config)
        self.assertEqual(
            {path.name: path.read_text(encoding="utf-8") for path in user_codex_home.iterdir()},
            user_codex_snapshot,
        )
        self.assertTrue(docs_dir.is_dir())
        for harness, result in results.items():
            self.assertEqual(result["provider"], "native")
            self.assertEqual(result["shared"], "kept")
            self.assertEqual(result["cwd"], str(target_repo))
            self.assertEqual(result["project_slug"], "demo-project")
            self.assertEqual(result["project_docs"], str(docs_dir))

        self.assertEqual(results["codex"]["codex_home"], str(user_codex_home))
        codex_argv = results["codex"]["argv"]
        self.assertNotIn("--model", codex_argv)
        self.assertEqual(codex_argv.count("--enable"), 2)
        self.assertIn("hooks", codex_argv)
        self.assertIn("multi_agent", codex_argv)
        codex_overrides = [codex_argv[index + 1] for index, value in enumerate(codex_argv) if value == "--config"]
        self.assertIn("agents.max_threads=3", codex_overrides)
        self.assertIn("agents.max_depth=2", codex_overrides)
        for role in self.roles:
            description = json.dumps(self.roles[role]["description"])
            self.assertIn(f"agents.{role}.description={description}", codex_overrides)
            role_path = agent_root / ".codex" / "agents" / f"{role}.toml"
            expected = f'agents.{role}.config_file="{role_path}"'
            self.assertIn(expected, codex_overrides)
        session_override = next(value for value in codex_overrides if value.startswith("hooks.SessionStart="))
        self.assertIn("$AGENT_ROOT/.codex/hooks/session_context.py", session_override)
        self.assertEqual(
            codex_argv[-7:],
            [
                "-C",
                str(target_repo),
                "--add-dir",
                str(docs_dir),
                "--dangerously-bypass-approvals-and-sandbox",
                "--flag",
                "codex",
            ],
        )
        skill_link = user_home / ".agents" / "skills" / "coding-colony"
        self.assertTrue(skill_link.is_symlink())
        self.assertEqual(skill_link.resolve(), (agent_root / ".codex" / "skills").resolve())
        self.assertEqual(results["claude"]["claude_config_dir"], str(agent_root / ".claude"))
        self.assertEqual(
            results["claude"]["argv"],
            ["--add-dir", str(docs_dir), "--mcp-config", str(agent_root / ".mcp.json"), "--flag", "claude"],
        )
        self.assertEqual(results["opencode"]["opencode_config_dir"], str(agent_root / ".opencode"))
        inline = json.loads(results["opencode"]["opencode_config_content"])
        self.assertEqual(inline["theme"], "dark")
        permission = inline["permission"]
        self.assertEqual(permission["bash"], "ask")
        self.assertEqual(permission["external_directory"]["/existing/**"], "deny")
        self.assertEqual(permission["external_directory"][f"{docs_dir}/**"], "allow")

        codex_config = (agent_root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('model = "codex-default"', codex_config)
        codex_gorn = (agent_root / ".codex" / "agents" / "gorn.toml").read_text(encoding="utf-8")
        self.assertIn('model = "codex-deep"', codex_gorn)
        self.assertIn('model_reasoning_effort = "max"', codex_gorn)
        claude_settings = json.loads((agent_root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(claude_settings["model"], "claude-default")
        claude_gorn = frontmatter(agent_root / ".claude" / "agents" / "gorn.md")
        self.assertEqual(claude_gorn["model"], "claude-deep")
        self.assertEqual(claude_gorn["effort"], "max")
        opencode_config = json.loads((agent_root / ".opencode" / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(opencode_config["model"], "opencode-default")
        opencode_gorn = frontmatter(agent_root / ".opencode" / "agents" / "gorn.md")
        self.assertEqual(opencode_gorn["model"], "opencode-deep")
        self.assertEqual(opencode_gorn["variant"], "max")

    def test_codex_launcher_defaults_to_agent_root_and_preserves_user_home(self) -> None:
        agent_root = self.install("--harness", "codex")
        target_repo = agent_root.parent / "repo"
        target_repo.mkdir()
        fake_bin = agent_root.parent / "bin"
        fake_bin.mkdir()
        executable = fake_bin / "codex"
        executable.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "Path(os.environ['CAPTURE']).write_text(json.dumps({"
            "'argv': sys.argv[1:], 'codex_home': os.environ['CODEX_HOME'], "
            "'cwd': os.getcwd(), 'target': os.environ['AGENT_TARGET_REPO']}))\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        user_home = agent_root.parent / "home"
        capture = agent_root.parent / "capture.json"
        launch_env = {
            **os.environ,
            "HOME": str(user_home),
            "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "CAPTURE": str(capture),
        }
        launch_env.pop("CODEX_HOME", None)
        launch = [
            str(agent_root / ".config" / "bin" / "coding-colony"),
            "codex",
        ]

        subprocess.run(launch, cwd=target_repo, check=True, text=True, capture_output=True, env=launch_env)
        subprocess.run(launch, cwd=target_repo, check=True, text=True, capture_output=True, env=launch_env)
        result = json.loads(capture.read_text(encoding="utf-8"))
        self.assertEqual(result["codex_home"], str(user_home / ".codex"))
        self.assertEqual(result["cwd"], str(agent_root))
        self.assertEqual(result["target"], str(agent_root))
        self.assertTrue((user_home / ".codex").is_dir())
        self.assertNotIn("--model", result["argv"])
        skill_link = user_home / ".agents" / "skills" / "coding-colony"
        self.assertTrue(skill_link.is_symlink())
        self.assertEqual(skill_link.resolve(), (agent_root / ".codex" / "skills").resolve())

        conflicting_home = agent_root.parent / "conflicting-home"
        conflict = conflicting_home / ".agents" / "skills" / "coding-colony"
        conflict.mkdir(parents=True)
        marker = conflict / "keep.txt"
        marker.write_text("user-owned\n", encoding="utf-8")
        conflicting_env = {**launch_env, "HOME": str(conflicting_home)}
        failed = subprocess.run(launch, cwd=target_repo, text=True, capture_output=True, env=conflicting_env)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("already exists", failed.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "user-owned\n")

    def test_launcher_separates_same_named_nested_repositories(self) -> None:
        agent_root = self.install("--harness", "opencode")
        legacy_docs = agent_root / "docs" / "service"
        legacy_docs.mkdir()
        legacy_spec = legacy_docs / "project-spec.md"
        legacy_spec.write_text("legacy project knowledge\n", encoding="utf-8")
        repositories = [
            agent_root.parent / "team-a" / "service",
            agent_root.parent / "team-b" / "service",
        ]
        repositories[0].mkdir(parents=True)
        (repositories[0] / ".git").mkdir()

        fake_bin = agent_root.parent / "bin"
        fake_bin.mkdir()
        executable = fake_bin / "opencode"
        executable.write_text(
            "#!/usr/bin/env python3\nimport os\nprint(os.environ['AGENT_PROJECT_DOCS'])\n",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        launch_env = {
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        }

        docs = []
        for index, repository in enumerate(repositories):
            if index == 1:
                repository.mkdir(parents=True)
                (repository / ".git").mkdir()
            result = subprocess.run(
                [
                    str(agent_root / ".config" / "bin" / "coding-colony"),
                    "opencode",
                    "--repo",
                    str(repository),
                ],
                check=True,
                text=True,
                capture_output=True,
                env=launch_env,
            )
            docs.append(Path(result.stdout.strip()))

        self.assertNotEqual(docs[0], docs[1])
        self.assertTrue(all(path.is_dir() for path in docs))
        self.assertEqual(docs[0], legacy_docs)
        self.assertEqual(legacy_spec.read_text(encoding="utf-8"), "legacy project knowledge\n")
        marker = json.loads((legacy_docs / ".coding-colony-project.json").read_text(encoding="utf-8"))
        self.assertEqual(marker, {"repository": str(repositories[0])})
        self.assertTrue(docs[1].name.startswith("team-b-service-"))

    def test_launcher_rejects_ambiguous_unmarked_legacy_docs(self) -> None:
        agent_root = self.install("--harness", "opencode")
        legacy_docs = agent_root / "docs" / "service"
        legacy_docs.mkdir()
        repositories = [
            agent_root.parent / "team-a" / "service",
            agent_root.parent / "team-b" / "service",
        ]
        for repository in repositories:
            repository.mkdir(parents=True)
            (repository / ".git").mkdir()

        result = subprocess.run(
            [
                str(agent_root / ".config" / "bin" / "coding-colony"),
                "opencode",
                "--repo",
                str(repositories[0]),
            ],
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ambiguous ownership", result.stderr)
        self.assertFalse((legacy_docs / ".coding-colony-project.json").exists())

    def test_parallel_launches_never_expose_partial_runtime_config(self) -> None:
        agent_root = self.install("--harness", "opencode")
        target_repo = agent_root.parent / "target"
        target_repo.mkdir()
        colony_path = agent_root / "coding-colony.json"
        colony = json.loads(colony_path.read_text(encoding="utf-8"))
        for name in ("default", *MODEL_TIERS):
            colony["models"]["opencode"][name] = f"parallel/{name}"
        for override in colony["agents"].values():
            override["reasoning"] = "parallel"
        colony_path.write_text(json.dumps(colony, indent=2) + "\n", encoding="utf-8")

        fake_bin = agent_root.parent / "bin"
        fake_bin.mkdir()
        executable = fake_bin / "opencode"
        executable.write_text(
            """#!/usr/bin/env python3
import json
import os
from pathlib import Path

root = Path(os.environ["OPENCODE_CONFIG_DIR"])
json.loads((root / "opencode.json").read_text(encoding="utf-8"))
for path in (root / "agents").glob("*.md"):
    content = path.read_text(encoding="utf-8")
    assert "\\nmodel: " in content and "\\nvariant: " in content
""",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        launch_env = {
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        }
        command = [
            str(agent_root / ".config" / "bin" / "coding-colony"),
            "opencode",
            "--repo",
            str(target_repo),
        ]
        processes = [
            subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=launch_env)
            for _ in range(64)
        ]
        failures = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            if process.returncode:
                failures.append((process.returncode, stdout, stderr))
        self.assertEqual(failures, [])

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
            self.assertEqual(content.count("# Added by Coding Colony"), 1)
            self.assertEqual(content.count("export PATH="), 1)

    def test_launcher_rejects_invalid_agent_config(self) -> None:
        agent_root = self.install("--harness", "codex")
        config_path = agent_root / "coding-colony.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["agents"]["gorn"]["model"] = "review"
        config_path.write_text(json.dumps(config), encoding="utf-8")

        result = subprocess.run(
            [
                str(agent_root / ".config" / "bin" / "coding-colony"),
                "codex",
                "--repo",
                str(agent_root.parent),
            ],
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agents.gorn.model must be fast, balanced, or deep", result.stderr)

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

    def test_reinstall_removes_only_retired_generated_artifacts(self) -> None:
        agent_root = self.install("--harness", ",".join(HARNESSES))
        colony_path = agent_root / "coding-colony.json"
        colony = json.loads(colony_path.read_text(encoding="utf-8"))
        colony["models"]["codex"]["deep"] = "custom-deep"
        colony["agents"]["gorn"]["reasoning"] = "max"
        colony_path.write_text(json.dumps(colony, indent=2) + "\n", encoding="utf-8")
        retired = (
            ".config/models.json",
            ".codex/agents/nadia.toml",
            ".codex/agents/riordian.toml",
            ".codex/skills/design/SKILL.md",
            ".codex/skills/implement-spike/SKILL.md",
            ".codex/skills/kotlin-spring-boot/SKILL.md",
            ".agents/skills/design/SKILL.md",
            ".agents/skills/implement-spike/SKILL.md",
            ".claude/agents/nadia.md",
            ".claude/agents/riordian.md",
            ".claude/skills/design/SKILL.md",
            ".claude/skills/implement-spike/SKILL.md",
            ".claude/skills/kotlin-spring-boot/SKILL.md",
            ".opencode/agents/nadia.md",
            ".opencode/agents/riordian.md",
            ".opencode/commands/design.md",
            ".opencode/commands/implement-spike.md",
            ".opencode/skills/kotlin-spring-boot/SKILL.md",
            ".opencode/plugins/model-tier-resolver.js",
        )
        disabled_graphify = (
            ".codex/skills/graphify/SKILL.md",
            ".claude/skills/graphify/SKILL.md",
            ".opencode/skills/graphify/SKILL.md",
            ".opencode/plugins/graphify.js",
        )
        user_files = (
            "codex.env",
            "claude.env",
            "opencode.env",
            ".codex/agents/custom.toml",
            ".codex/skills/custom/SKILL.md",
            ".codex/auth.json",
            ".codex/sessions/session.jsonl",
            ".claude/agents/custom.md",
            ".claude/skills/custom/SKILL.md",
            ".claude/history.jsonl",
            ".claude/projects/project/session.jsonl",
            ".opencode/agents/custom.md",
            ".opencode/commands/custom.md",
            ".opencode/session-state.json",
            ".agents/skills/custom/SKILL.md",
        )
        for relative_path in (*retired, *disabled_graphify, *user_files):
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
        for relative_path in disabled_graphify:
            self.assertFalse((agent_root / relative_path).exists(), relative_path)
        self.assertEqual(json.loads(colony_path.read_text(encoding="utf-8")), colony)
        for relative_path in user_files:
            self.assertEqual(
                (agent_root / relative_path).read_text(encoding="utf-8"),
                "preserve only when user-owned\n",
            )

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
        environments: list[dict[str, str]] = []
        working_directories: list[Path] = []

        def fake_which(command: str) -> str | None:
            return "/tmp/bin/graphify" if command == "graphify" else None

        def fake_run(command: list[str], check: bool, **kwargs: object) -> object:
            commands.append(command)
            environments.append(kwargs["env"])
            working_directories.append(kwargs["cwd"])
            return object()

        original_which = module.shutil.which
        original_run = module.subprocess.run
        try:
            module.shutil.which = fake_which
            module.subprocess.run = fake_run
            optional_deps = {"graphify": {"state": "enabled", "availability": "available"}}
            module.configure_selected_plugins(
                ["graphify"],
                {"graphify": {"post_install_command": ["graphify", "install", "--project", "--platform", "{platform}"]}},
                optional_deps,
                ["opencode", "codex"],
                Path("/tmp/coding-colony-test"),
                dry_run=False,
            )
        finally:
            module.shutil.which = original_which
            module.subprocess.run = original_run

        self.assertEqual(
            commands,
            [
                ["graphify", "install", "--project", "--platform", "opencode"],
                ["graphify", "install", "--project", "--platform", "codex"],
            ],
        )
        self.assertEqual(working_directories, [Path("/tmp/coding-colony-test")] * 2)
        self.assertEqual(optional_deps["graphify"]["configure_state"], "configured:opencode+codex")
        for environment in environments:
            self.assertEqual(environment["CODEX_HOME"], "/tmp/coding-colony-test/.codex")
            self.assertEqual(environment["CLAUDE_CONFIG_DIR"], "/tmp/coding-colony-test/.claude")
            self.assertEqual(environment["OPENCODE_CONFIG_DIR"], "/tmp/coding-colony-test/.opencode")

    def assert_codex_install(self, agent_root: Path, provider: dict) -> None:
        config = (agent_root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn(f'model = "{provider["default_model"]}"', config)
        self.assertIn("max_threads = 3", config)
        self.assertIn("max_depth = 2", config)
        self.assertEqual(
            json.loads((agent_root / ".codex" / "bridge.json").read_text(encoding="utf-8")),
            {
                "agents": {role_name: role["description"] for role_name, role in self.roles.items()},
                "mcp_servers": {},
            },
        )
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
            if provider.get("codex_provider"):
                provider_id = f'coding_colony_{provider["codex_provider"]["id"]}'
                self.assertIn(f'model_provider = "{provider_id}"', content)
                self.assertIn(f"[model_providers.{provider_id}]", content)
            else:
                self.assertIn('model_provider = "openai"', content)
            self.assertIn("Role workflow:", content)
            self.assertIn(self.shared_instructions, content)

        skill_root = agent_root / ".codex" / "skills"
        self.assertEqual(
            {path.name for path in skill_root.iterdir()},
            set(COMMAND_TO_ROLE) | DEVELOPMENT_SKILLS,
        )
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
        self.assert_development_skills(skill_root)
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
            self.assertIn("Role workflow:", content)
            self.assertIn(self.shared_instructions, content)
            self.assert_no_provider_models_in_agent_definition(body_without_frontmatter(path), provider)
            if role["sandbox"] == "read-only":
                self.assertEqual(metadata["permissionMode"], "plan")
                self.assertIn("Write", metadata["disallowedTools"])
                self.assertIn("Edit", metadata["disallowedTools"])

        skill_root = agent_root / ".claude" / "skills"
        self.assertEqual(
            {path.name for path in skill_root.iterdir()},
            set(COMMAND_TO_ROLE) | DEVELOPMENT_SKILLS,
        )
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
        self.assert_development_skills(skill_root)
        self.assert_role_workflow_contracts(role_contents)

    def assert_opencode_install(self, agent_root: Path, provider: dict) -> None:
        config = json.loads((agent_root / ".opencode" / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(config["model"], provider["default_model"])
        self.assertNotIn("agent", config)
        self.assertNotIn("command", config)
        self.assertNotIn("./plugins/model-tier-resolver.js", config["plugin"])
        self.assertFalse((agent_root / ".opencode" / "plugins" / "model-tier-resolver.js").exists())
        self.assertEqual(
            {path.stem for path in (agent_root / ".opencode" / "agents").glob("*.md")},
            set(self.roles),
        )
        role_contents: dict[str, str] = {}
        for role_name, role in self.roles.items():
            path = agent_root / ".opencode" / "agents" / f"{role_name}.md"
            metadata = frontmatter(path)
            self.assertEqual(metadata["model"], provider["tiers"][role["tier"]])
            self.assertEqual(metadata["variant"], role["effort"])
            self.assertEqual(metadata["x-agent-tier"], role["tier"])
            self.assertEqual(metadata["mode"], "subagent")
            raw_content = path.read_text(encoding="utf-8")
            content = body_without_frontmatter(path)
            role_contents[role_name] = content
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
        skill_root = agent_root / ".opencode" / "skills"
        self.assertEqual({path.name for path in skill_root.iterdir()}, DEVELOPMENT_SKILLS)
        self.assert_development_skills(skill_root)
        self.assert_role_workflow_contracts(role_contents)

    def assert_development_skills(self, skill_root: Path) -> None:
        for name in DEVELOPMENT_SKILLS:
            source_root = REPO_ROOT / "skills" / name
            installed_root = skill_root / name
            source_files = {
                path.relative_to(source_root)
                for path in source_root.rglob("*")
                if path.is_file()
            }
            installed_files = {
                path.relative_to(installed_root)
                for path in installed_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(installed_files, source_files)
            self.assertGreater(len(source_files), 1)
            self.assertEqual(frontmatter(source_root / "SKILL.md")["name"], name)
            for relative_path in source_files:
                self.assertEqual(
                    (installed_root / relative_path).read_text(encoding="utf-8"),
                    (source_root / relative_path).read_text(encoding="utf-8"),
                )

    def assert_role_workflow_contracts(self, role_contents: dict[str, str]) -> None:
        self.assertIn("READY", role_contents["milten"])
        self.assertIn("NEEDS_INPUT", role_contents["milten"])
        self.assertIn("READY", role_contents["lester"])
        self.assertIn("BLOCKED", role_contents["lester"])
        self.assertIn("traceability", role_contents["lester"].lower())
        self.assertIn("both `kotlin` and `spring-boot`", role_contents["lester"])
        self.assertIn("Java Spring Boot requires only `spring-boot`", role_contents["lester"])
        self.assertNotIn("kotlin-spring-boot", role_contents["lester"])
        self.assertIn("startup", role_contents["gorn"].lower())
        self.assertIn("bootstrap", role_contents["gorn"].lower())
        self.assertIn("reject a plan that omitted an applicable skill", role_contents["gorn"])
        self.assertIn("startup", role_contents["gomez"].lower())
        self.assertIn("Verdict: PASS", role_contents["gomez"])
        self.assertIn("PASS", role_contents["gorn"])
        self.assertIn("repeat", role_contents["gorn"].lower())
        self.assertIn("plan-required development skill", role_contents["lee"])
        self.assertIn("unlisted skill", role_contents["lee"])
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
