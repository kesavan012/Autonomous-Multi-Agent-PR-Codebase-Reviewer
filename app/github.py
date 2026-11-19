from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx


_PR_URL = re.compile(r"^https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/(\d+)/?(?:[?#].*)?$")
_MAX_PATCH_BYTES = 500_000
_MAX_SOURCE_BYTES = 160_000
_MAX_CONTEXT_FILES = 8


class InvalidPullRequestUrl(ValueError):
    pass


class GitHubRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class PullRequest:
    owner: str
    repository: str
    number: int
    title: str
    patch: str
    sources: dict[str, str]


def parse_pull_request_url(url: str) -> tuple[str, str, int]:
    match = _PR_URL.fullmatch(url.strip())
    if not match:
        raise InvalidPullRequestUrl("Enter a GitHub pull request URL, such as https://github.com/owner/repo/pull/42")
    owner, repository, number = match.groups()
    return owner, repository, int(number)


async def _read_limited(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                return None
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > _MAX_SOURCE_BYTES:
                    return None
            return data.decode("utf-8", errors="replace")
    except httpx.HTTPError:
        return None


async def fetch_pull_request(url: str, token: str | None = None) -> PullRequest:
    owner, repository, number = parse_pull_request_url(url)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Patchwork-Review/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    base = f"https://api.github.com/repos/{owner}/{repository}/pulls/{number}"
    timeout = httpx.Timeout(12.0, connect=5.0)
    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=False) as client:
        try:
            pull_response = await client.get(base)
            if pull_response.status_code == 404:
                raise GitHubRequestError("Pull request not found, or the repository is private.")
            pull_response.raise_for_status()
            pull_data = pull_response.json()

            files_response = await client.get(f"{base}/files", params={"per_page": 100})
            files_response.raise_for_status()
            file_data = files_response.json()
        except GitHubRequestError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise GitHubRequestError("GitHub could not provide this pull request. Check the URL and try again.") from error

        patches: list[str] = []
        for item in file_data:
            path = item.get("filename")
            file_patch = item.get("patch")
            if not path or not file_patch:
                continue
            previous = item.get("previous_filename", path)
            patches.append(f"diff --git a/{previous} b/{path}\n--- a/{previous}\n+++ b/{path}\n{file_patch}")

        patch = "\n".join(patches)
        if len(patch.encode("utf-8")) > _MAX_PATCH_BYTES:
            raise GitHubRequestError("This pull request is too large to review in one pass (500 KB diff limit).")
        if not patch:
            raise GitHubRequestError("GitHub returned no text diff for this pull request.")

        base_sha = pull_data.get("base", {}).get("sha", "")
        sources: dict[str, str] = {}
        if base_sha:
            candidates = [
                item.get("filename")
                for item in file_data[:_MAX_CONTEXT_FILES]
                if item.get("status") != "removed" and item.get("filename")
            ]
            for path in candidates:
                encoded_path = quote(path, safe="/")
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repository}/{base_sha}/{encoded_path}"
                source = await _read_limited(client, raw_url)
                if source is not None:
                    sources[path] = source

    return PullRequest(
        owner=owner,
        repository=repository,
        number=number,
        title=str(pull_data.get("title", "Untitled pull request")),
        patch=patch,
        sources=sources,
    )