from __future__ import annotations

import unittest

from gitlab_agent.cli import _agent_prompt, _build_parser, _handoff


class FakeManager:
    def status(self, workspace_id: str) -> dict[str, object]:
        return {
            "workspace_id": workspace_id,
            "project": "team/project",
            "worktree_path": "/tmp/worktrees/abc123",
            "base_ref": "main",
            "branch": "chatgpt/task-abc123",
            "merge_request_url": None,
            "pushed": False,
            "dirty": False,
            "commits_ahead_of_base": 0,
        }


class CodingAgentCLITests(unittest.TestCase):
    def test_copilot_handoff_is_agent_neutral(self) -> None:
        result = _handoff(
            FakeManager(),  # type: ignore[arg-type]
            "abc123",
            "Implement a small fix",
            agent="copilot",
        )
        self.assertEqual(result["agent"], "copilot")
        self.assertEqual(
            result["agent_command"],
            "cd /tmp/worktrees/abc123 && copilot",
        )
        self.assertIn("selected by CodingAgent", str(result["agent_prompt"]))
        self.assertIn("Implement a small fix", str(result["agent_prompt"]))
        self.assertNotIn("codex_command", result)
        self.assertNotIn("codex_prompt", result)

    def test_codex_handoff_keeps_compatibility_aliases(self) -> None:
        result = _handoff(
            FakeManager(),  # type: ignore[arg-type]
            "abc123",
            "Inspect the code",
            agent="codex",
        )
        self.assertEqual(result["agent"], "codex")
        self.assertEqual(
            result["agent_command"],
            "cd /tmp/worktrees/abc123 && codex",
        )
        self.assertEqual(result["codex_command"], result["agent_command"])
        self.assertEqual(result["codex_prompt"], result["agent_prompt"])

    def test_codingagent_parser_accepts_backend_selection(self) -> None:
        parser = _build_parser(prog="codingagent")
        args = parser.parse_args(
            [
                "task",
                "team/project",
                "--agent",
                "copilot",
                "--goal",
                "Fix it",
            ]
        )
        self.assertEqual(args.command, "task")
        self.assertEqual(args.agent, "copilot")
        self.assertEqual(args.goal, "Fix it")

    def test_agent_prompt_rejects_unknown_backend(self) -> None:
        status = FakeManager().status("abc123")
        with self.assertRaises(ValueError):
            _agent_prompt(status, agent="unknown")


if __name__ == "__main__":
    unittest.main()
