from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .config import AgentSettings


class GitLabAPI:
    """Small synchronous GitLab API helper for local CLI workflows."""

    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        if not self.settings.api_token:
            raise RuntimeError(
                "GITLAB_TOKEN is required for GitLab API operations such as checkout-mr"
            )
        return {
            "PRIVATE-TOKEN": self.settings.api_token,
            "Accept": "application/json",
            "User-Agent": "chatgpt-selfhosted-gitlab-mcp/0.2",
        }

    def get_json(self, path: str) -> Any:
        url = f"{self.settings.gitlab_base_url}/api/v4{path}"
        try:
            with httpx.Client(
                headers=self._headers(),
                verify=self.settings.api_verify_ssl,
                trust_env=self.settings.api_trust_env,
                follow_redirects=True,
                timeout=30.0,
            ) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"GitLab API request failed for {url}: {exc}") from exc

        if response.is_error:
            detail = response.text[:2000]
            raise RuntimeError(
                f"GitLab API returned HTTP {response.status_code} for {path}: {detail}"
            )
        return response.json()

    def merge_request(self, project: str, iid: int) -> dict[str, Any]:
        encoded = quote(project.strip(), safe="")
        data = self.get_json(f"/projects/{encoded}/merge_requests/{iid}")
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected GitLab MR response")
        return data
