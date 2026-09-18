from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from gitlab_agent.gitlab_api import GitLabAPI


class GitLabAPITests(unittest.TestCase):
    def settings(self, token: str = "token") -> SimpleNamespace:
        return SimpleNamespace(
            gitlab_base_url="http://gitlab.example.internal",
            api_token=token,
            api_verify_ssl=True,
            api_trust_env=False,
        )

    def test_merge_request_uses_encoded_project_and_direct_network_mode(self) -> None:
        response = MagicMock()
        response.is_error = False
        response.json.return_value = {
            "iid": 42,
            "title": "Fix thing",
            "source_branch": "chatgpt/fix-thing-abc",
            "target_branch": "main",
        }

        client = MagicMock()
        client.get.return_value = response
        client_cm = MagicMock()
        client_cm.__enter__.return_value = client
        client_cm.__exit__.return_value = False

        with patch("gitlab_agent.gitlab_api.httpx.Client", return_value=client_cm) as cls:
            api = GitLabAPI(self.settings())
            result = api.merge_request("team/project", 42)

        self.assertEqual(result["iid"], 42)
        cls.assert_called_once()
        kwargs = cls.call_args.kwargs
        self.assertFalse(kwargs["trust_env"])
        self.assertTrue(kwargs["verify"])
        client.get.assert_called_once_with(
            "http://gitlab.example.internal/api/v4/projects/team%2Fproject/merge_requests/42"
        )

    def test_api_operations_require_gitlab_token(self) -> None:
        api = GitLabAPI(self.settings(token=""))
        with self.assertRaises(RuntimeError):
            api.merge_request("team/project", 1)


if __name__ == "__main__":
    unittest.main()
