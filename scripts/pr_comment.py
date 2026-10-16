"""Upsert one evalgate PR comment per suite (FR-9).

The comment body starts with ``<!-- evalgate:report -->`` and carries ``<!-- evalgate:suite=<name> -->``;
an existing comment with both markers is edited, otherwise one is created. A 403 (fork PRs, missing
``pull-requests: write``) skips the comment with a warning and never changes the gate.

Usage: ``python scripts/pr_comment.py --repo owner/name --pr 12 --suite classify --body-file report.md``
(token from ``GITHUB_TOKEN``, API from ``GITHUB_API_URL``, default https://api.github.com).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

MARKER = "<!-- evalgate:report -->"
MAX_BODY = 60_000  # GitHub limits comments to 65,536 characters


def suite_marker(suite: str) -> str:
    return f"<!-- evalgate:suite={suite} -->"


@dataclass
class Outcome:
    action: str  # created | updated | skipped
    comment_id: int | None = None
    reason: str | None = None


DEFAULT_AUTHOR = "github-actions[bot]"


class CommentClient:
    def __init__(
        self, api_url: str, token: str, client: httpx.Client | None = None, author: str = DEFAULT_AUTHOR
    ) -> None:
        self.author = author
        self.api = api_url.rstrip("/")
        self.client = client or httpx.Client(timeout=20)
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def list_comments(self, repo: str, pr: int) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = self.client.get(
                f"{self.api}/repos/{repo}/issues/{pr}/comments",
                params={"per_page": 100, "page": page},
                headers=self.headers,
            )
            resp.raise_for_status()
            batch = resp.json()
            comments += batch
            if len(batch) < 100:
                return comments
            page += 1

    def ours(self, comment: dict[str, Any], suite: str) -> bool:
        """Only a comment written by the bot counts: anyone can paste the markers into their own comment."""
        user = comment.get("user") or {}
        body = comment.get("body") or ""
        return (
            user.get("login") == self.author
            and user.get("type") == "Bot"
            and MARKER in body
            and suite_marker(suite) in body
        )

    def upsert(self, repo: str, pr: int, suite: str, body: str) -> Outcome:
        if not body.startswith(MARKER):
            body = f"{MARKER}\n{body}"
        body = f"{body[:MAX_BODY]}\n{suite_marker(suite)}\n"
        try:
            existing = next((c for c in self.list_comments(repo, pr) if self.ours(c, suite)), None)
            if existing is not None:
                resp = self.client.patch(
                    f"{self.api}/repos/{repo}/issues/comments/{existing['id']}",
                    json={"body": body},
                    headers=self.headers,
                )
                resp.raise_for_status()
                return Outcome("updated", int(existing["id"]))
            resp = self.client.post(
                f"{self.api}/repos/{repo}/issues/{pr}/comments", json={"body": body}, headers=self.headers
            )
            resp.raise_for_status()
            return Outcome("created", int(resp.json().get("id", 0)))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                return Outcome("skipped", reason="GitHub returned 403 (no permission to comment); gate unchanged")
            return Outcome("skipped", reason=f"GitHub returned {exc.response.status_code}; gate unchanged")
        except httpx.TransportError as exc:
            return Outcome("skipped", reason=f"GitHub unreachable ({exc.__class__.__name__}); gate unchanged")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args(argv)
    client = CommentClient(
        os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        os.environ.get("GITHUB_TOKEN", ""),
        author=os.environ.get("EVALGATE_COMMENT_AUTHOR", DEFAULT_AUTHOR),
    )
    outcome = client.upsert(args.repo, args.pr, args.suite, args.body_file.read_text(encoding="utf-8"))
    if outcome.action == "skipped":
        print(f"::warning title=evalgate::PR comment skipped: {outcome.reason}")
    else:
        print(f"evalgate: PR comment {outcome.action} (id {outcome.comment_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
