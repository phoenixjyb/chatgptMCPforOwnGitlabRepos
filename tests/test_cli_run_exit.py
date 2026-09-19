from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from gitlab_agent import cli


class RunExitTests(unittest.TestCase):
    def invoke(self, result=None, error=None, prog="gitlab-agent"):
        output = io.StringIO()
        with (
            patch.object(cli.AgentSettings, "load"),
            patch.object(cli, "WorkspaceManager"),
            patch.object(cli, "GitLabAPI"),
            patch.object(cli, "CommandRunner") as runner,
            contextlib.redirect_stdout(output),
        ):
            runner.return_value.run.return_value = result
            runner.return_value.run.side_effect = error
            code = cli.main(["run", "abc123def456", "--", "python", "-c", "pass"], prog=prog)
            runner.return_value.run.assert_called_once_with(
                "abc123def456", ["python", "-c", "pass"], timeout_seconds=None,
            )
        return code, json.loads(output.getvalue())

    def test_success_is_zero(self):
        result = {"returncode": 0, "timed_out": False, "stdout": "ok"}
        code, payload = self.invoke(result)
        self.assertEqual(code, 0)
        self.assertEqual(payload, result)

    def test_child_failure_is_propagated_by_every_cli_name(self):
        for prog in ("gitlab-agent", "actual-coder", "codingagent"):
            with self.subTest(prog=prog):
                code, payload = self.invoke({"returncode": 7, "timed_out": False}, prog=prog)
                self.assertEqual(code, 7)
                self.assertEqual(payload["returncode"], 7)

    def test_timeout_is_nonzero_even_without_child_returncode(self):
        code, payload = self.invoke({"returncode": None, "timed_out": True})
        self.assertEqual(code, 124)
        self.assertIsNone(payload["returncode"])

    def test_timeout_takes_precedence_over_returncode(self):
        code, _ = self.invoke({"returncode": 0, "timed_out": True})
        self.assertEqual(code, 124)

    def test_signal_returncode_is_normalized(self):
        code, payload = self.invoke({"returncode": -9, "timed_out": False})
        self.assertEqual(code, 137)
        self.assertEqual(payload["returncode"], -9)

    def test_large_exit_codes_cannot_wrap_to_success(self):
        for value in (256, 512, 3221225477, -256):
            with self.subTest(value=value):
                code, payload = self.invoke({"returncode": value, "timed_out": False})
                self.assertEqual(code, 1)
                self.assertEqual(payload["returncode"], value)

    def test_absent_or_malformed_returncode_is_failure(self):
        for value in (None, "0", False, True):
            with self.subTest(value=value):
                code, _ = self.invoke({"returncode": value, "timed_out": False})
                self.assertEqual(code, 1)
        self.assertEqual(self.invoke({})[0], 1)

    def test_launcher_failure_keeps_structured_diagnostic(self):
        code, payload = self.invoke(error=FileNotFoundError("test executable unavailable"))
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["type"], "FileNotFoundError")

    def test_policy_rejection_remains_nonzero(self):
        code, payload = self.invoke(error=RuntimeError("Executable is not allowed"))
        self.assertEqual(code, 1)
        self.assertIn("not allowed", payload["error"])


class RunExitIntegrationTests(unittest.TestCase):
    """Run the actual module in a subprocess against a real managed workspace."""

    def setUp(self):
        import test_workspace as fixtures
        self.fixture = fixtures.WorkspaceManagerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        created = self.fixture.manager.create_workspace("team/project", task_slug="exit-status")
        self.workspace_id = str(created["workspace_id"])
        # Never inherit developer credentials/configuration into this integration test.
        self.env = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith("GITLAB_")
        }
        self.env.update({
            "GITLAB_AGENT_ENV_FILE": str(self.fixture.settings.config_file),
            "GITLAB_BASE_URL": "https://gitlab.example.invalid",
            "GITLAB_WORKSPACE_ROOT": str(self.fixture.settings.workspace_root),
            "GITLAB_ALLOWED_PROJECTS": "team/project",
            "GITLAB_ALLOWED_EXECUTABLES": "python",
        })

    def invoke(self, script, timeout=None):
        args = [sys.executable, "-m", "gitlab_agent.cli", "run"]
        if timeout is not None:
            args += ["--timeout", str(timeout)]
        args += [self.workspace_id, "--", "python", "-c", script]
        return subprocess.run(args, env=self.env, capture_output=True, text=True, timeout=20)

    def test_real_success(self):
        result = self.invoke("print('success')")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["returncode"], 0)

    def test_real_child_failure_reaches_shell(self):
        result = self.invoke("import sys; print('failed'); sys.exit(7)")
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(json.loads(result.stdout)["returncode"], 7)

    def test_real_timeout_reaches_shell(self):
        result = self.invoke("import time; time.sleep(5)", timeout=1)
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertTrue(json.loads(result.stdout)["timed_out"])


if __name__ == "__main__":
    unittest.main()
