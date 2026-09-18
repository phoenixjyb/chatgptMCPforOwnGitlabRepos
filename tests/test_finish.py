from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from gitlab_agent.config import AgentSettings
from gitlab_agent.finish import build_finish_plan, execute_finish


class FakeRunner:
    def __init__(self, *, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def run(
        self,
        workspace_id: str,
        argv: list[str],
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, object]:
        self.calls.append(argv)
        return {
            "workspace_id": workspace_id,
            "argv": argv,
            "timed_out": False,
            "timeout_seconds": timeout_seconds,
            "returncode": self.returncode,
            "stdout": "",
            "stderr": "",
        }


class FakeManager:
    def __init__(
        self,
        *,
        root: Path,
        dirty: bool = True,
        ahead: int = 0,
        pushed: bool = False,
        mr_url: str | None = None,
        changed_paths: list[str] | None = None,
        security_diff: str = "",
        contract: str | None = None,
    ) -> None:
        self.root = root
        self._dirty = dirty
        self._ahead = ahead
        self._changed_paths = changed_paths or ["src/example.py"]
        self._security_diff = security_diff
        self._contract = contract
        self.state = SimpleNamespace(
            workspace_id="abc123def456",
            project="team/project",
            base_ref="main",
            base_sha="base123",
            branch="chatgpt/test-abc123de",
            pushed=pushed,
            merge_request_url=mr_url,
        )
        self.commits: list[str] = []
        self.pushes: list[str] = []

    def get_state(self, workspace_id: str) -> SimpleNamespace:
        return self.state

    def status(self, workspace_id: str) -> dict[str, object]:
        return {
            "workspace_id": workspace_id,
            "project": self.state.project,
            "base_ref": self.state.base_ref,
            "base_sha": self.state.base_sha,
            "branch": self.state.branch,
            "worktree_path": str(self.root / "worktree"),
            "dirty": self._dirty,
            "commits_ahead_of_base": self._ahead,
            "pushed": self.state.pushed,
            "merge_request_url": self.state.merge_request_url,
        }

    def read_remote_text_file(
        self,
        project: str,
        relative_path: str,
        *,
        ref: str | None = None,
    ) -> dict[str, object]:
        return {
            "project": project,
            "ref": ref or "main",
            "commit_sha": self.state.base_sha,
            "path": relative_path,
            "exists": self._contract is not None,
            "content": self._contract,
        }

    def changed_paths(self, workspace_id: str) -> list[str]:
        return list(self._changed_paths)

    def diff(self, workspace_id: str) -> dict[str, object]:
        return {
            "workspace_id": workspace_id,
            "base_sha": self.state.base_sha,
            "truncated": False,
            "original_bytes": len(self._security_diff.encode()),
            "diff": self._security_diff,
        }

    def security_diff(self, workspace_id: str) -> str:
        return self._security_diff

    def latest_commit_subject(self, workspace_id: str) -> str:
        return "existing commit subject"

    def commit(self, workspace_id: str, message: str) -> dict[str, object]:
        self.commits.append(message)
        self._dirty = False
        self._ahead += 1
        return self.status(workspace_id)

    def push_and_create_mr(
        self,
        workspace_id: str,
        *,
        target_branch: str,
        title: str,
        description: str = "",
    ) -> dict[str, object]:
        self.pushes.append("push-mr")
        self.state.pushed = True
        self.state.merge_request_url = (
            "https://gitlab.example.test/team/project/-/merge_requests/1"
        )
        return {
            "workspace": self.status(workspace_id),
            "merge_request_url": self.state.merge_request_url,
            "target_branch": target_branch,
            "title": title,
            "description": description,
        }

    def push(self, workspace_id: str) -> dict[str, object]:
        self.pushes.append("push-update")
        return {
            "workspace": self.status(workspace_id),
            "updated_existing_branch": True,
            "merge_request_url": self.state.merge_request_url,
        }


class FinishTests(unittest.TestCase):
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
            workspace_root=root / "workspace-root",
            branch_prefix="chatgpt/",
            default_base_ref="main",
            allowed_executables={"python", "pytest", "uv"},
            command_timeout_seconds=300,
            max_output_bytes=120000,
            max_file_bytes=1000000,
            git_author_name=None,
            git_author_email=None,
        )
        self.root = root

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_dirty_workspace_builds_first_push_mr_plan(self) -> None:
        manager = FakeManager(root=self.root, dirty=True)
        runner = FakeRunner()

        plan = build_finish_plan(
            settings=self.settings,
            manager=manager,  # type: ignore[arg-type]
            runner=runner,  # type: ignore[arg-type]
            workspace_id="abc123def456",
            commit_message="fix: example",
        )

        self.assertTrue(plan["ok"])
        self.assertEqual(plan["plan"]["commit_required"], True)
        self.assertEqual(plan["plan"]["push_action"], "push-mr")
        self.assertEqual(plan["plan"]["mr_title"], "fix: example")
        self.assertEqual(plan["validations"], [])
        self.assertTrue(
            any("No project validation commands" in item for item in plan["warnings"])
        )

    def test_protected_path_blocks_without_explicit_override(self) -> None:
        manager = FakeManager(
            root=self.root,
            dirty=True,
            changed_paths=[".actualcoder.yaml"],
        )
        plan = build_finish_plan(
            settings=self.settings,
            manager=manager,  # type: ignore[arg-type]
            runner=FakeRunner(),  # type: ignore[arg-type]
            workspace_id="abc123def456",
            commit_message="change policy",
        )

        self.assertFalse(plan["ok"])
        self.assertEqual(plan["protected_path_changes"], [".actualcoder.yaml"])
        self.assertTrue(any("Protected paths changed" in item for item in plan["blockers"]))

    def test_secret_finding_blocks_finish(self) -> None:
        diff = """diff --git a/leak.txt b/leak.txt
--- /dev/null
+++ b/leak.txt
@@ -0,0 +1 @@
+token=glpat-abcdefghijklmnop
"""
        manager = FakeManager(
            root=self.root,
            dirty=True,
            changed_paths=["leak.txt"],
            security_diff=diff,
        )
        plan = build_finish_plan(
            settings=self.settings,
            manager=manager,  # type: ignore[arg-type]
            runner=FakeRunner(),  # type: ignore[arg-type]
            workspace_id="abc123def456",
            commit_message="add leak",
        )

        self.assertFalse(plan["ok"])
        self.assertFalse(plan["secret_scan"]["ok"])
        self.assertEqual(
            plan["secret_scan"]["findings"][0]["kind"],
            "GitLab PAT",
        )

    def test_required_validation_failure_blocks_finish(self) -> None:
        contract = """
version: 1
validation:
  commands:
    - name: unit
      argv: [pytest, -q]
      required: true
"""
        manager = FakeManager(root=self.root, dirty=True, contract=contract)
        runner = FakeRunner(returncode=1)

        plan = build_finish_plan(
            settings=self.settings,
            manager=manager,  # type: ignore[arg-type]
            runner=runner,  # type: ignore[arg-type]
            workspace_id="abc123def456",
            commit_message="fix: tests",
        )

        self.assertFalse(plan["ok"])
        self.assertTrue(plan["validations"][0]["blocking"])
        self.assertTrue(
            any("validation commands failed" in item for item in plan["blockers"])
        )

    def test_existing_mr_plans_push_update(self) -> None:
        manager = FakeManager(
            root=self.root,
            dirty=False,
            ahead=2,
            pushed=True,
            mr_url="https://gitlab.example.test/team/project/-/merge_requests/7",
        )

        plan = build_finish_plan(
            settings=self.settings,
            manager=manager,  # type: ignore[arg-type]
            runner=FakeRunner(),  # type: ignore[arg-type]
            workspace_id="abc123def456",
        )

        self.assertTrue(plan["ok"])
        self.assertEqual(plan["plan"]["push_action"], "push-update")
        self.assertEqual(
            plan["plan"]["existing_mr"],
            "https://gitlab.example.test/team/project/-/merge_requests/7",
        )

    def test_execute_finish_commits_then_creates_mr(self) -> None:
        manager = FakeManager(root=self.root, dirty=True)
        plan = build_finish_plan(
            settings=self.settings,
            manager=manager,  # type: ignore[arg-type]
            runner=FakeRunner(),  # type: ignore[arg-type]
            workspace_id="abc123def456",
            commit_message="feat: finish",
            mr_description="Validated",
        )
        result = execute_finish(
            manager=manager,  # type: ignore[arg-type]
            workspace_id="abc123def456",
            plan=plan,
        )

        self.assertEqual(manager.commits, ["feat: finish"])
        self.assertEqual(manager.pushes, ["push-mr"])
        self.assertEqual(
            result["push"]["merge_request_url"],
            "https://gitlab.example.test/team/project/-/merge_requests/1",
        )


if __name__ == "__main__":
    unittest.main()
