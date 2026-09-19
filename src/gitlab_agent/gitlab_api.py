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

    def _client(self) -> httpx.Client:
        return httpx.Client(
            headers=self._headers(),
            verify=self.settings.api_verify_ssl,
            trust_env=self.settings.api_trust_env,
            follow_redirects=True,
            timeout=30.0,
        )

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.settings.gitlab_base_url}/api/v4{path}"
        try:
            with self._client() as client:
                response = (
                    client.get(url)
                    if params is None
                    else client.get(url, params=params)
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"GitLab API request failed for {url}: {exc}") from exc

        if response.is_error:
            detail = response.text[:2000]
            raise RuntimeError(
                f"GitLab API returned HTTP {response.status_code} for {path}: {detail}"
            )
        return response.json()

    def get_text(self, path: str) -> str:
        url = f"{self.settings.gitlab_base_url}/api/v4{path}"
        try:
            with self._client() as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"GitLab API request failed for {url}: {exc}") from exc

        if response.is_error:
            detail = response.text[:2000]
            raise RuntimeError(
                f"GitLab API returned HTTP {response.status_code} for {path}: {detail}"
            )
        return response.text

    def get_text_tail(
        self,
        path: str,
        *,
        tail_bytes: int,
    ) -> dict[str, object]:
        """Stream a text response while retaining only a bounded UTF-8 tail."""

        url = f"{self.settings.gitlab_base_url}/api/v4{path}"
        cap = max(1_000, min(int(tail_bytes), 80_000))
        tail = bytearray()
        total = 0

        try:
            with self._client() as client:
                with client.stream("GET", url) as response:
                    if response.is_error:
                        detail_raw = response.read()[:2000]
                        detail = detail_raw.decode("utf-8", errors="replace")
                        raise RuntimeError(
                            f"GitLab API returned HTTP {response.status_code} "
                            f"for {path}: {detail}"
                        )

                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        total += len(chunk)
                        tail.extend(chunk)
                        if len(tail) > cap:
                            del tail[:-cap]
        except httpx.HTTPError as exc:
            raise RuntimeError(f"GitLab API request failed for {url}: {exc}") from exc

        return {
            "content": bytes(tail).decode("utf-8", errors="ignore"),
            "truncated": total > cap,
            "original_text_bytes": total,
            "tail_bytes": cap,
        }

    def merge_request(self, project: str, iid: int) -> dict[str, Any]:
        encoded = quote(project.strip(), safe="")
        data = self.get_json(f"/projects/{encoded}/merge_requests/{iid}")
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected GitLab MR response")
        return data

    def pipelines(
        self,
        project: str,
        *,
        ref: str,
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        encoded = quote(project.strip(), safe="")
        data = self.get_json(
            f"/projects/{encoded}/pipelines",
            params={
                "ref": ref,
                "per_page": max(1, min(per_page, 100)),
                "page": 1,
                "order_by": "id",
                "sort": "desc",
            },
        )
        if not isinstance(data, list):
            raise RuntimeError("Unexpected GitLab pipelines response")
        return [item for item in data if isinstance(item, dict)]

    def pipeline_jobs(
        self,
        project: str,
        pipeline_id: int,
        *,
        include_retried: bool = False,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        encoded = quote(project.strip(), safe="")
        page_size = max(1, min(per_page, 100))
        page_cap = max(1, min(max_pages, 20))
        items: list[dict[str, Any]] = []

        for page in range(1, page_cap + 1):
            data = self.get_json(
                f"/projects/{encoded}/pipelines/{pipeline_id}/jobs",
                params={
                    "include_retried": str(include_retried).lower(),
                    "per_page": page_size,
                    "page": page,
                },
            )
            if not isinstance(data, list):
                raise RuntimeError("Unexpected GitLab pipeline jobs response")

            items.extend(item for item in data if isinstance(item, dict))
            if len(data) < page_size:
                return items

        raise RuntimeError(
            f"Pipeline {pipeline_id} has more than {page_cap * page_size} jobs; "
            "refusing to return potentially incomplete CI evidence"
        )

    def job_trace(self, project: str, job_id: int) -> str:
        encoded = quote(project.strip(), safe="")
        return self.get_text(f"/projects/{encoded}/jobs/{job_id}/trace")

    def job_trace_tail(
        self,
        project: str,
        job_id: int,
        *,
        tail_bytes: int,
    ) -> dict[str, object]:
        encoded = quote(project.strip(), safe="")
        return self.get_text_tail(
            f"/projects/{encoded}/jobs/{job_id}/trace",
            tail_bytes=tail_bytes,
        )
