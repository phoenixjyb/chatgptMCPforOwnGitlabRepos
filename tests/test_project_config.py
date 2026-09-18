from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gitlab_agent.config import AgentSettings
from gitlab_agent.project_config import parse_project_config


class ProjectConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = AgentSettings(
            config_file=root / ".env",
            gitlab_base_url="https://gitlab.example.test",
            api_token="token",
            api_verify_ssl=True,
            api_trust_env=False,
            git_token="token",
            git_username="oauth2",
            git_trust_env=False,
            allowed_projects={"team/project"},
            require_write_allowlist=True,
            workspace_root=root / "workspace",
            branch_prefix="chatgpt/",
            default_base_ref="main",
            allowed_executables={"python", "uv", "pytest", "cmake"},
            command_timeout_seconds=300,
            max_output_bytes=120000,
            max_file_bytes=1000000,
            git_author_name=None,
            git_author_email=None,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_contract_produces_effective_config(self) -> None:
        text = """
version: 1
project:
  base_branch: develop
agents:
  preferred:
    - copilot
    - codex
validation:
  commands:
    - name: unit-tests
      argv: [uv, run, pytest, -q]
      required: true
      timeout_seconds: 180
protected_paths:
  - deploy/
  - .gitlab-ci.yml
instructions:
  - Keep ROS 2 package boundaries intact.
executables:
  required:
    - uv
    - cmake
mr:
  target_branch: develop
  title_prefix: "[ActualCoder] "
"""
        result = parse_project_config(
            text,
            settings=self.settings,
            source_ref="main",
        )

        self.assertTrue(result.found)
        self.assertTrue(result.valid)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.effective["base_branch"], "develop")
        self.assertEqual(
            result.effective["preferred_agents"],
            ["copilot", "codex"],
        )
        commands = result.effective["validation_commands"]
        self.assertEqual(commands[0]["argv"], ["uv", "run", "pytest", "-q"])
        self.assertEqual(result.effective["mr"]["target_branch"], "develop")

    def test_repository_cannot_self_authorize_executable(self) -> None:
        text = """
version: 1
validation:
  commands:
    - name: unsafe
      argv: [bash, -c, echo hello]
executables:
  required:
    - curl
"""
        result = parse_project_config(
            text,
            settings=self.settings,
            source_ref="main",
        )

        self.assertFalse(result.valid)
        joined = "\n".join(result.errors)
        self.assertIn("bash", joined)
        self.assertIn("curl", joined)
        self.assertIn("GITLAB_ALLOWED_EXECUTABLES", joined)

    def test_timeout_is_capped_by_user_policy(self) -> None:
        text = """
version: 1
validation:
  commands:
    - name: tests
      argv: [pytest, -q]
      timeout_seconds: 999
"""
        result = parse_project_config(
            text,
            settings=self.settings,
            source_ref="main",
        )

        self.assertTrue(result.valid)
        commands = result.effective["validation_commands"]
        self.assertEqual(commands[0]["timeout_seconds"], 300)
        self.assertTrue(any("will be capped" in item for item in result.warnings))

    def test_unknown_keys_and_unsafe_paths_fail(self) -> None:
        text = """
version: 1
mystery: true
protected_paths:
  - ../outside
"""
        result = parse_project_config(
            text,
            settings=self.settings,
            source_ref="main",
        )

        self.assertFalse(result.valid)
        self.assertTrue(any("Unknown key" in item for item in result.errors))
        self.assertTrue(any("safe repository-relative path" in item for item in result.errors))

    def test_missing_contract_is_valid_and_uses_user_defaults(self) -> None:
        result = parse_project_config(
            None,
            settings=self.settings,
            source_ref="main",
        )

        self.assertFalse(result.found)
        self.assertTrue(result.valid)
        self.assertEqual(result.effective["base_branch"], "main")
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
