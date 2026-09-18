from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gitlab_agent.config import AgentSettings
from gitlab_agent.runner import CommandRunner
from gitlab_agent.workspace import WorkspaceManager


def run(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return proc.stdout.strip()


class WorkspaceManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        seed = root / "seed"
        remote = root / "remote.git"
        seed.mkdir()

        run("git", "init", "-b", "main", cwd=seed)
        run("git", "config", "user.name", "Test User", cwd=seed)
        run("git", "config", "user.email", "test@example.com", cwd=seed)
        (seed / "README.md").write_text("seed\n", encoding="utf-8")
        run("git", "add", "README.md", cwd=seed)
        run("git", "commit", "-m", "Initial commit", cwd=seed)
        run("git", "clone", "--bare", str(seed), str(remote))
        run(
            "git",
            "--git-dir",
            str(remote),
            "config",
            "receive.advertisePushOptions",
            "true",
        )

        self.remote = remote
        self.settings = AgentSettings(
            config_file=root / ".env",
            gitlab_base_url="https://gitlab.example.invalid",
            api_token="",
            api_verify_ssl=True,
            api_trust_env=False,
            git_token="",
            git_username="oauth2",
            git_trust_env=False,
            allowed_projects={"team/project"},
            require_write_allowlist=True,
            workspace_root=root / "agent",
            branch_prefix="chatgpt/",
            default_base_ref="main",
            allowed_executables={"python"},
            command_timeout_seconds=30,
            max_output_bytes=120000,
            max_file_bytes=1000000,
            git_author_name="Agent Test",
            git_author_email="agent@example.com",
        )
        self.manager = WorkspaceManager(
            self.settings,
            url_resolver=lambda project: str(self.remote),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_worktree_edit_commit_and_push(self) -> None:
        created = self.manager.create_workspace(
            "team/project",
            task_slug="fix timeout",
        )
        workspace_id = str(created["workspace_id"])
        self.assertTrue(str(created["branch"]).startswith("chatgpt/fix-timeout-"))

        readme = self.manager.read_file(workspace_id, "README.md")
        self.assertEqual(readme["content"], "seed\n")

        self.manager.write_file(workspace_id, "README.md", "changed\n")
        diff = self.manager.diff(workspace_id)
        self.assertIn("+changed", str(diff["diff"]))

        committed = self.manager.commit(workspace_id, "Change README")
        self.assertEqual(committed["commits_ahead_of_base"], 1)
        self.assertFalse(committed["dirty"])

        pushed = self.manager.push(workspace_id)
        branch = str(pushed["workspace"]["branch"])
        self.assertTrue(pushed["workspace"]["pushed"])
        remote_sha = run(
            "git",
            "--git-dir",
            str(self.remote),
            "rev-parse",
            f"refs/heads/{branch}",
        )
        self.assertEqual(remote_sha, pushed["workspace"]["head"])

        cleaned = self.manager.cleanup(workspace_id)
        self.assertTrue(cleaned["removed"])

    def test_second_commit_can_update_existing_remote_branch(self) -> None:
        created = self.manager.create_workspace("team/project", task_slug="iterate")
        workspace_id = str(created["workspace_id"])

        self.manager.write_file(workspace_id, "first.txt", "one\n")
        self.manager.commit(workspace_id, "First change")
        first_push = self.manager.push(workspace_id)
        self.assertFalse(first_push["updated_existing_branch"])

        self.manager.write_file(workspace_id, "second.txt", "two\n")
        second_commit = self.manager.commit(workspace_id, "Second change")
        second_push = self.manager.push(workspace_id)

        self.assertTrue(second_push["updated_existing_branch"])
        branch = str(second_push["workspace"]["branch"])
        remote_sha = run(
            "git",
            "--git-dir",
            str(self.remote),
            "rev-parse",
            f"refs/heads/{branch}",
        )
        self.assertEqual(remote_sha, second_commit["head"])
        self.manager.cleanup(workspace_id)

    def test_reconstruct_remote_branch_after_cleanup_and_push_update(self) -> None:
        created = self.manager.create_workspace("team/project", task_slug="resume")
        workspace_id = str(created["workspace_id"])
        self.manager.write_file(workspace_id, "first.txt", "one\n")
        self.manager.commit(workspace_id, "First change")
        first_push = self.manager.push(workspace_id)
        branch = str(first_push["workspace"]["branch"])
        first_head = str(first_push["workspace"]["head"])

        self.manager.cleanup(workspace_id)

        restored = self.manager.checkout_remote_branch(
            "team/project",
            branch,
            base_ref="main",
            merge_request_url="https://gitlab.example.test/team/project/-/merge_requests/1",
        )
        restored_id = str(restored["workspace_id"])
        self.assertTrue(restored["pushed"])
        self.assertEqual(restored["branch"], branch)
        self.assertEqual(restored["head"], first_head)
        self.assertEqual(
            restored["merge_request_url"],
            "https://gitlab.example.test/team/project/-/merge_requests/1",
        )

        self.manager.write_file(restored_id, "second.txt", "two\n")
        second_commit = self.manager.commit(restored_id, "Second change")
        second_push = self.manager.push(restored_id)

        self.assertTrue(second_push["updated_existing_branch"])
        self.assertEqual(
            second_push["merge_request_url"],
            "https://gitlab.example.test/team/project/-/merge_requests/1",
        )
        remote_sha = run(
            "git",
            "--git-dir",
            str(self.remote),
            "rev-parse",
            f"refs/heads/{branch}",
        )
        self.assertEqual(remote_sha, second_commit["head"])
        self.manager.cleanup(restored_id)

    def test_diff_includes_untracked_files(self) -> None:
        created = self.manager.create_workspace("team/project", task_slug="untracked")
        workspace_id = str(created["workspace_id"])
        self.manager.write_file(workspace_id, "NEW_FILE.md", "hello\n")

        diff = self.manager.diff(workspace_id)
        self.assertIn("### UNTRACKED", str(diff["diff"]))
        self.assertIn("NEW_FILE.md", str(diff["diff"]))
        self.assertIn("+hello", str(diff["diff"]))

        self.manager.cleanup(workspace_id, force=True)

    def test_apply_patch_and_path_escape_rejection(self) -> None:
        created = self.manager.create_workspace("team/project", task_slug="patch")
        workspace_id = str(created["workspace_id"])

        patch_text = """diff --git a/README.md b/README.md
index 5626abf..2bdf67a 100644
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-seed
+patched
"""
        self.manager.apply_patch(workspace_id, patch_text)
        self.assertEqual(
            self.manager.read_file(workspace_id, "README.md")["content"],
            "patched\n",
        )

        with self.assertRaises(ValueError):
            self.manager.write_file(workspace_id, "../escape.txt", "nope")

        self.manager.cleanup(workspace_id, force=True)

    def test_push_and_create_mr_uses_git_push_options(self) -> None:
        created = self.manager.create_workspace("team/project", task_slug="mr")
        workspace_id = str(created["workspace_id"])
        self.manager.write_file(workspace_id, "feature.txt", "hello\n")
        self.manager.commit(workspace_id, "Add feature")

        result = self.manager.push_and_create_mr(
            workspace_id,
            target_branch="main",
            title="Add feature",
            description="Created by test",
        )
        self.assertTrue(result["workspace"]["pushed"])
        # A stock local Git server accepts push options when configured, but it
        # does not implement GitLab's merge_request.create behavior.
        self.assertIsNone(result["merge_request_url"])
        self.manager.cleanup(workspace_id)

    def test_command_runner_allowlist_and_secret_scrubbing(self) -> None:
        created = self.manager.create_workspace("team/project", task_slug="runner")
        workspace_id = str(created["workspace_id"])
        runner = CommandRunner(self.settings, self.manager)

        with patch.dict(
            os.environ,
            {
                "GITLAB_TOKEN": "super-secret-value",
                "CONTROL_PLANE_API_KEY": "another-secret",
            },
            clear=False,
        ):
            result = runner.run(
                workspace_id,
                [
                    "python",
                    "-c",
                    (
                        "import os; "
                        "print(os.getenv('GITLAB_TOKEN')); "
                        "print(os.getenv('CONTROL_PLANE_API_KEY')); "
                        "print(os.environ['HOME'])"
                    ),
                ],
            )

        self.assertEqual(result["returncode"], 0)
        self.assertNotIn("super-secret-value", str(result["stdout"]))
        self.assertNotIn("another-secret", str(result["stdout"]))
        self.assertIn(str(self.settings.workspace_root), str(result["stdout"]))

        with self.assertRaises(RuntimeError):
            runner.run(workspace_id, ["sh", "-c", "echo unsafe"])

        self.manager.cleanup(workspace_id)


if __name__ == "__main__":
    unittest.main()
