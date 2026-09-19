from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from gitlab_agent.config import AgentSettings
from gitlab_agent.workspace import WorkspaceManager


class WorkspacePublicationTests(unittest.TestCase):
    """Exercise publication checks against real temporary Git repositories."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        seed = self.root / "seed"
        seed.mkdir()
        self.git("init", "-b", "main", cwd=seed)
        self.git("config", "user.name", "Publication Test", cwd=seed)
        self.git("config", "user.email", "test@example.invalid", cwd=seed)
        (seed / "README.md").write_text("base\n", encoding="utf-8")
        self.git("add", "-A", cwd=seed)
        self.git("commit", "-m", "base", cwd=seed)
        self.remote = self.root / "remote.git"
        self.git("clone", "--bare", str(seed), str(self.remote))
        self.settings = AgentSettings(
            config_file=self.root / ".env",
            gitlab_base_url="https://gitlab.example.invalid",
            api_token="", api_verify_ssl=True, api_trust_env=False,
            git_token="", git_username="oauth2", git_trust_env=False,
            allowed_projects={"team/project"}, require_write_allowlist=True,
            workspace_root=self.root / "agent", branch_prefix="chatgpt/",
            default_base_ref="main", allowed_executables={"python"},
            command_timeout_seconds=30, max_output_bytes=120000,
            max_file_bytes=1000000, git_author_name="Publication Test",
            git_author_email="test@example.invalid",
        )
        self.manager = WorkspaceManager(
            self.settings, url_resolver=lambda project: str(self.remote),
        )
        created = self.manager.create_workspace("team/project", task_slug="publication")
        self.workspace_id = str(created["workspace_id"])
        self.worktree = Path(str(created["worktree_path"]))
        self.repo = Path(str(created["repo_path"]))
        self.branch = str(created["branch"])
        self.base_sha = str(created["base_sha"])
        self.state_file = self.manager._state_path(self.workspace_id)

    @staticmethod
    def git(*args: str, cwd: Path | None = None) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, text=True, capture_output=True,
            check=True, timeout=30,
        ).stdout.strip()

    def commit(self, name: str) -> str:
        self.manager.write_file(self.workspace_id, name + ".txt", name + "\n")
        return str(self.manager.commit(self.workspace_id, name)["head"])

    def publish(self) -> str:
        first = self.commit("first")
        self.manager.push(self.workspace_id)
        return first

    def assert_preserved(self, head: str) -> None:
        self.assertTrue(self.worktree.is_dir())
        self.assertTrue(self.state_file.is_file())
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.worktree), head)
        self.assertEqual(
            self.git("--git-dir", str(self.repo), "rev-parse", "refs/heads/" + self.branch),
            head,
        )

    def abandon_worktree(self) -> None:
        # Simulate manual removal, leaving the branch and its commits in the cache.
        self.git("--git-dir", str(self.repo), "worktree", "remove", str(self.worktree))
        self.state_file.unlink()

    def assert_no_probe_refs(self) -> None:
        self.assertEqual(self.git(
            "--git-dir", str(self.repo), "for-each-ref", "--format=%(refname)",
            "refs/actualcoder/publication/",
        ), "")

    def test_cleanup_refuses_second_commit_after_first_push(self) -> None:
        first = self.publish()
        second = self.commit("second")
        self.assertTrue(self.manager.get_state(self.workspace_id).pushed)
        with self.assertRaisesRegex(RuntimeError, "unpublished"):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(second)
        self.assertEqual(self.git(
            "--git-dir", str(self.remote), "rev-parse", "refs/heads/" + self.branch,
        ), first)
        self.assert_no_probe_refs()

    def test_cleanup_refuses_raw_git_commit_after_push(self) -> None:
        self.publish()
        self.git("-c", "user.name=Publication Test", "-c", "user.email=test@example.invalid",
                 "commit", "--allow-empty", "-m", "outside controller", cwd=self.worktree)
        head = self.git("rev-parse", "HEAD", cwd=self.worktree)
        with self.assertRaises(RuntimeError):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(head)

    def test_cleanup_refuses_deleted_remote_branch_despite_cached_ref(self) -> None:
        first = self.publish()
        self.git("--git-dir", str(self.remote), "update-ref", "-d", "refs/heads/" + self.branch)
        with self.assertRaisesRegex(RuntimeError, "publication"):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(first)
        self.assert_no_probe_refs()

    def test_cleanup_refuses_unreachable_remote(self) -> None:
        first = self.publish()
        self.remote.rename(self.root / "offline.git")
        with self.assertRaisesRegex(RuntimeError, "publication"):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(first)
        self.assert_no_probe_refs()

    def test_cleanup_refuses_remote_rewind(self) -> None:
        first = self.publish()
        self.git("--git-dir", str(self.remote), "update-ref", "refs/heads/" + self.branch,
                 self.base_sha)
        with self.assertRaises(RuntimeError):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(first)

    def test_cleanup_refuses_reconfigured_origin(self) -> None:
        first = self.publish()
        other = self.root / "other.git"
        self.git("clone", "--bare", str(self.remote), str(other))
        self.git("remote", "set-url", "origin", str(other), cwd=self.worktree)
        with self.assertRaisesRegex(RuntimeError, "remote mismatch"):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(first)

    def test_cleanup_allows_current_published_head(self) -> None:
        self.publish()
        self.assertTrue(self.manager.cleanup(self.workspace_id)["removed"])
        self.assertFalse(self.worktree.exists())
        self.assertFalse(self.state_file.exists())
        self.assert_no_probe_refs()

    def test_cleanup_allows_remote_descendant_of_local_head(self) -> None:
        first = self.publish()
        second = self.commit("second")
        self.manager.push(self.workspace_id)
        self.git("reset", "--hard", first, cwd=self.worktree)
        self.assertTrue(self.manager.cleanup(self.workspace_id)["removed"])
        self.assertEqual(self.git(
            "--git-dir", str(self.remote), "rev-parse", "refs/heads/" + self.branch,
        ), second)

    def test_cleanup_reconciles_publication_when_metadata_was_not_saved(self) -> None:
        self.commit("first")
        self.git("push", "origin", self.branch, cwd=self.worktree)
        self.assertFalse(self.manager.get_state(self.workspace_id).pushed)
        self.assertTrue(self.manager.cleanup(self.workspace_id)["removed"])

    def test_cleanup_of_unchanged_workspace_requires_no_remote(self) -> None:
        self.remote.rename(self.root / "offline.git")
        self.assertTrue(self.manager.cleanup(self.workspace_id)["removed"])

    def test_force_cleanup_explicitly_discards_unpublished_work(self) -> None:
        self.publish()
        self.commit("second")
        self.remote.rename(self.root / "offline.git")
        self.assertTrue(self.manager.cleanup(self.workspace_id, force=True)["removed"])

    def test_cleanup_refuses_dirty_worktree(self) -> None:
        first = self.publish()
        self.manager.write_file(self.workspace_id, "dirty.txt", "preserve\n")
        with self.assertRaisesRegex(RuntimeError, "uncommitted"):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(first)
        self.assertTrue((self.worktree / "dirty.txt").is_file())

    def test_cleanup_refuses_branch_switch_even_with_force(self) -> None:
        first = self.publish()
        self.commit("second")
        self.git("checkout", "--detach", first, cwd=self.worktree)
        for force in (False, True):
            with self.subTest(force=force), self.assertRaisesRegex(RuntimeError, "branch"):
                self.manager.cleanup(self.workspace_id, force=force)
        self.assertTrue(self.worktree.is_dir())
        self.assertTrue(self.state_file.is_file())

    def test_cleanup_refuses_mismatched_repo_path(self) -> None:
        first = self.publish()
        state = self.manager.get_state(self.workspace_id)
        state.repo_path = str(self.remote)
        self.manager._save_state(state)
        with self.assertRaisesRegex(RuntimeError, "repository"):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(first)

    def test_cleanup_refuses_foreign_worktree_inside_managed_root(self) -> None:
        first = self.publish()
        other = self.root / "agent" / "worktrees" / "foreign"
        self.git("clone", str(self.remote), str(other))
        self.git("checkout", self.branch, cwd=other)
        state = self.manager.get_state(self.workspace_id)
        state.worktree_path = str(other)
        self.manager._save_state(state)
        with self.assertRaisesRegex(RuntimeError, "repository"):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(first)
        self.assertTrue(other.is_dir())

    def test_cleanup_rechecks_changes_made_during_publication_check(self) -> None:
        first = self.publish()
        original = self.manager._run_git
        changed = False

        def run(args, **kwargs):
            nonlocal changed
            result = original(args, **kwargs)
            if "fetch" in args and not changed:
                changed = True
                self.manager.write_file(self.workspace_id, "late.txt", "late edit\n")
            return result

        with patch.object(self.manager, "_run_git", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "changed"):
                self.manager.cleanup(self.workspace_id)
        self.assert_preserved(first)
        self.assertTrue((self.worktree / "late.txt").exists())

    def test_cleanup_requires_current_allowlist_authorization(self) -> None:
        first = self.publish()
        self.manager.settings = replace(self.settings, allowed_projects={"other/project"})
        with self.assertRaisesRegex(RuntimeError, "GITLAB_ALLOWED_PROJECTS"):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(first)

    def test_cleanup_refuses_never_published_commit(self) -> None:
        head = self.commit("first")
        with self.assertRaisesRegex(RuntimeError, "publication"):
            self.manager.cleanup(self.workspace_id)
        self.assert_preserved(head)

    def test_publication_probe_preserves_shared_fetch_state(self) -> None:
        self.publish()
        fetch_head = self.repo / "FETCH_HEAD"
        before = fetch_head.read_bytes()
        tracking_ref = "refs/remotes/origin/" + self.branch
        self.git("--git-dir", str(self.repo), "update-ref", tracking_ref, self.base_sha)
        self.manager.cleanup(self.workspace_id)
        self.assertEqual(fetch_head.read_bytes(), before)
        self.assertEqual(self.git(
            "--git-dir", str(self.repo), "rev-parse", tracking_ref,
        ), self.base_sha)
        self.assert_no_probe_refs()

    def test_cleanup_refuses_ancestry_check_error(self) -> None:
        first = self.publish()
        original = self.manager._run_git

        def run(args, **kwargs):
            if "merge-base" in args:
                return subprocess.CompletedProcess(args, 128, "", "injected Git error")
            return original(args, **kwargs)

        with patch.object(self.manager, "_run_git", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "ancestry"):
                self.manager.cleanup(self.workspace_id)
        self.assert_preserved(first)

    def _advance_before_ref_deletion(self, operation) -> str:
        original = self.manager._run_git
        advanced = ""

        def run(args, **kwargs):
            nonlocal advanced
            if (
                "update-ref" in args and "-d" in args
                and "refs/heads/" + self.branch in args and not advanced
            ):
                head = original(["--git-dir", str(self.repo), "rev-parse", "refs/heads/" + self.branch]).stdout.strip()
                tree = original(["--git-dir", str(self.repo), "rev-parse", head + "^{tree}"]).stdout.strip()
                advanced = original([
                    "--git-dir", str(self.repo), "commit-tree", tree, "-p", head,
                    "-m", "concurrent branch advance",
                ]).stdout.strip()
                original(["--git-dir", str(self.repo), "update-ref", "refs/heads/" + self.branch, advanced])
            return original(args, **kwargs)

        with patch.object(self.manager, "_run_git", side_effect=run):
            with self.assertRaises(RuntimeError):
                operation()
        self.assertTrue(advanced)
        self.assertEqual(self.git(
            "--git-dir", str(self.repo), "rev-parse", "refs/heads/" + self.branch,
        ), advanced)
        return advanced

    def test_cleanup_compare_and_delete_preserves_concurrent_branch_tip(self) -> None:
        self.publish()
        self._advance_before_ref_deletion(lambda: self.manager.cleanup(self.workspace_id))
        # Worktree removal already happened, but the new commit/ref and recovery
        # metadata must survive the failed compare-and-delete.
        self.assertTrue(self.state_file.is_file())

    def test_checkout_compare_and_delete_preserves_concurrent_branch_tip(self) -> None:
        self.publish()
        self.abandon_worktree()
        self._advance_before_ref_deletion(
            lambda: self.manager.checkout_remote_branch("team/project", self.branch)
        )

    def test_cleanup_reads_legacy_state_without_new_metadata(self) -> None:
        self.publish()
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertNotIn("last_pushed_sha", state)
        self.assertTrue(self.manager.cleanup(self.workspace_id)["removed"])

    def test_checkout_preserves_abandoned_unpublished_commits(self) -> None:
        self.publish()
        second = self.commit("second")
        self.abandon_worktree()
        with self.assertRaisesRegex(RuntimeError, "unpublished"):
            self.manager.checkout_remote_branch("team/project", self.branch)
        self.assertEqual(self.git(
            "--git-dir", str(self.repo), "rev-parse", "refs/heads/" + self.branch,
        ), second)

    def test_checkout_reuses_abandoned_published_branch(self) -> None:
        first = self.publish()
        self.abandon_worktree()
        restored = self.manager.checkout_remote_branch("team/project", self.branch)
        self.assertEqual(restored["head"], first)
        self.assertTrue(Path(str(restored["worktree_path"])).is_dir())

    def test_checkout_can_fast_forward_abandoned_branch(self) -> None:
        first = self.publish()
        second = self.commit("second")
        self.manager.push(self.workspace_id)
        self.git("reset", "--hard", first, cwd=self.worktree)
        self.abandon_worktree()
        restored = self.manager.checkout_remote_branch("team/project", self.branch)
        self.assertEqual(restored["head"], second)

    def test_checkout_refuses_branch_still_in_use(self) -> None:
        self.publish()
        with self.assertRaisesRegex(RuntimeError, "already checked out"):
            self.manager.checkout_remote_branch("team/project", self.branch)


if __name__ == "__main__":
    unittest.main()
