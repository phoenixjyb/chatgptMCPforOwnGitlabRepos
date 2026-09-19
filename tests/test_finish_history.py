from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from gitlab_agent import finish
from gitlab_agent.history_scan import HistoryScanError
from gitlab_agent.runner import CommandRunner


def dummy_token() -> str:
    return "gl" + "pat-" + "notARealCredential0123456789"


class FinishHistoryTests(unittest.TestCase):
    """Use the real controller and local Git; do not run a model or business GitLab."""

    def setUp(self):
        import test_workspace_publication as fixtures
        self.fixture = fixtures.WorkspacePublicationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.manager = self.fixture.manager
        self.settings = self.fixture.settings
        self.ws = self.fixture.workspace_id
        self.runner = CommandRunner(self.settings, self.manager)

    def plan(self, **kwargs):
        return finish.build_finish_plan(settings=self.settings, manager=self.manager,
                                        runner=self.runner, workspace_id=self.ws,
                                        commit_message="test change", **kwargs)

    def introduce_and_remove(self):
        self.manager.write_file(self.ws, "secret.txt", dummy_token() + "\n")
        introduced = self.manager.commit(self.ws, "introduce")["head"]
        (self.fixture.worktree / "secret.txt").unlink()
        self.manager.commit(self.ws, "remove")
        return introduced

    def test_history_secret_blocks_even_with_clean_final_tree(self):
        introduced = self.introduce_and_remove()
        plan = self.plan()
        self.assertFalse(plan["ok"])
        scan = plan["secret_scan"]
        self.assertTrue(scan["coverage_complete"])
        self.assertFalse(scan["ok"])
        self.assertEqual(scan["history"]["commit_count"], 2)
        self.assertEqual(scan["history"]["findings"][0]["commit_sha"], introduced)
        self.assertNotIn(dummy_token(), json.dumps(plan))

    def test_blocked_plan_performs_zero_writes(self):
        self.introduce_and_remove()
        plan = self.plan()
        with (patch.object(self.manager, "commit") as commit,
              patch.object(self.manager, "push") as push,
              patch.object(self.manager, "push_and_create_mr") as mr):
            with self.assertRaisesRegex(RuntimeError, "blocked"):
                finish.execute_finish(manager=self.manager, workspace_id=self.ws, plan=plan)
            commit.assert_not_called()
            push.assert_not_called()
            mr.assert_not_called()

    def test_history_failure_blocks_even_with_secret_override(self):
        self.fixture.commit("ordinary")
        with patch.object(finish, "scan_history_secrets", side_effect=HistoryScanError("injected limit")):
            plan = self.plan(allow_secret_match=True)
        self.assertFalse(plan["ok"])
        self.assertFalse(plan["secret_scan"]["coverage_complete"])
        self.assertIn("injected limit", plan["secret_scan"]["history"]["error"])
        self.assertTrue(any("history" in x.lower() for x in plan["blockers"]))

    def test_explicit_false_positive_override_requires_complete_coverage(self):
        self.introduce_and_remove()
        plan = self.plan(allow_secret_match=True)
        self.assertTrue(plan["ok"])
        self.assertTrue(plan["secret_scan"]["coverage_complete"])
        self.assertTrue(plan["secret_scan"]["overridden"])
        self.assertFalse(plan["secret_scan"]["ok"])

    def test_clean_history_is_bound_to_actual_head_and_base(self):
        head = self.fixture.commit("ordinary")
        plan = self.plan()
        self.assertTrue(plan["ok"])
        history = plan["secret_scan"]["history"]
        self.assertEqual(history["head_sha"], head)
        self.assertEqual(history["base_sha"], self.fixture.base_sha)
        self.assertEqual(history["findings"], [])

    def test_candidate_only_change_still_has_empty_history(self):
        self.manager.write_file(self.ws, "new.txt", "ordinary text\n")
        plan = self.plan()
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["secret_scan"]["history"]["commit_count"], 0)

    def test_candidate_secret_is_blocked_and_not_echoed_in_review_diff(self):
        self.manager.write_file(self.ws, "secret.txt", "EXAMPLE_TOKEN=" + dummy_token())
        plan = self.plan()
        self.assertFalse(plan["ok"])
        self.assertTrue(plan["review_diff"]["redactions"])
        self.assertNotIn(dummy_token(), json.dumps(plan))

    def test_redaction_does_not_weaken_raw_snapshot_binding(self):
        self.manager.write_file(self.ws, "secret.txt", dummy_token())
        first = self.plan(allow_secret_match=True)
        self.manager.write_file(self.ws, "secret.txt", dummy_token() + "changed")
        second = self.plan(allow_secret_match=True)
        self.assertEqual(first["review_diff"]["diff"], second["review_diff"]["diff"])
        self.assertNotEqual(first["snapshot"]["digest"], second["snapshot"]["digest"])
        with patch.object(self.manager, "commit") as commit:
            with self.assertRaisesRegex(RuntimeError, "changed"):
                finish.execute_finish(manager=self.manager, workspace_id=self.ws, plan=first)
            commit.assert_not_called()

    def test_head_change_after_scan_still_aborts_before_writes(self):
        self.fixture.commit("ordinary")
        plan = self.plan()
        self.fixture.commit("later")
        with patch.object(self.manager, "push_and_create_mr") as mr:
            with self.assertRaisesRegex(RuntimeError, "changed"):
                finish.execute_finish(manager=self.manager, workspace_id=self.ws, plan=plan)
            mr.assert_not_called()

    def test_private_key_body_is_not_exposed_by_review_diff(self):
        begin = "-----BEGIN " + "PRIVATE KEY-----"
        end = "-----END " + "PRIVATE KEY-----"
        self.manager.write_file(self.ws, "key.txt", begin + "\nopaqueKeyBody\n" + end)
        plan = self.plan()
        self.assertFalse(plan["ok"])
        self.assertNotIn("opaqueKeyBody", json.dumps(plan))


if __name__ == "__main__":
    unittest.main()
