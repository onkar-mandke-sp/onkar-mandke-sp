#!/usr/bin/env python3
"""Generate a custom activity summary SVG using GitHub API data."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

USERNAME = os.environ.get("GITHUB_USERNAME", "onkar-mandke-sp")
TOKEN = os.environ["GITHUB_TOKEN"]
OUTPUT = os.environ.get("OUTPUT_PATH", "profile/activity-summary.svg")

COLORS = {
    "bg": "#2e3440",
    "border": "#4c566a",
    "title": "#81a1c1",
    "label": "#d8dee9",
    "value": "#eceff4",
    "muted": "#616e88",
    "icon": "#81a1c1",
}


def request_json(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = None
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "onkar-profile-activity-card",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def graphql(query: str, variables: dict | None = None) -> dict:
    payload = request_json(
        "https://api.github.com/graphql",
        method="POST",
        payload={"query": query, "variables": variables or {}},
    )
    if "errors" in payload:
        raise RuntimeError(json.dumps(payload["errors"]))
    return payload["data"]


def search_issue_count(query: str) -> int:
    data = graphql(
        """
        query($query: String!) {
          search(query: $query, type: ISSUE, first: 1) {
            issueCount
          }
        }
        """,
        {"query": query},
    )
    return int(data["search"]["issueCount"])


def fetch_stats() -> dict[str, int | str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=365)
    from_date = start.strftime("%Y-%m-%dT00:00:00Z")
    to_date = now.strftime("%Y-%m-%dT23:59:59Z")

    data = graphql(
        """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              totalPullRequestContributions
              totalIssueContributions
              totalPullRequestReviewContributions
              restrictedContributionsCount
              totalRepositoryContributions
              contributionCalendar { totalContributions }
            }
            repositoriesContributedTo(
              contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]
              includeUserRepositories: true
            ) {
              totalCount
            }
          }
        }
        """,
        {"login": USERNAME, "from": from_date, "to": to_date},
    )

    user = data["user"]
    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]

    prs_total = search_issue_count(f"author:{USERNAME} type:pr")
    prs_merged = search_issue_count(f"author:{USERNAME} type:pr is:merged")
    prs_last_year = search_issue_count(
        f"author:{USERNAME} type:pr created:>={start.date().isoformat()}"
    )

    return {
        "commits": collection["totalCommitContributions"],
        "issues": collection["totalIssueContributions"],
        "reviews": collection["totalPullRequestReviewContributions"],
        "repos_contributed": collection.get("totalRepositoryContributions")
        or user["repositoriesContributedTo"]["totalCount"],
        "graph_total": calendar["totalContributions"],
        "restricted": collection["restrictedContributionsCount"],
        "prs_total": prs_total,
        "prs_merged": prs_merged,
        "prs_last_year": max(prs_last_year, collection["totalPullRequestContributions"]),
        "updated": now.astimezone().strftime("%d %b %Y, %H:%M %Z"),
    }


def stat_block(x: int, y: int, icon: str, label: str, value: str | int, note: str = "") -> str:
    note_y = y + 58 if note else y + 48
    note_block = (
        f'<text x="{x + 34}" y="{note_y}" fill="{COLORS["muted"]}" font-size="11">{note}</text>'
        if note
        else ""
    )
    return f"""
    <g transform="translate({x}, {y})">
      <text x="0" y="0" fill="{COLORS['icon']}" font-size="16">{icon}</text>
      <text x="34" y="0" fill="{COLORS['label']}" font-size="13">{label}</text>
      <text x="34" y="24" fill="{COLORS['value']}" font-size="24" font-weight="700">{value}</text>
      {note_block}
    </g>
    """


def build_svg(stats: dict[str, int | str]) -> str:
    width = 495
    height = 300
    blocks = [
        stat_block(24, 78, "🔀", "Total pull requests", stats["prs_total"], "includes private repos"),
        stat_block(260, 78, "✅", "Merged PRs", stats["prs_merged"]),
        stat_block(24, 158, "📅", "PRs last year", stats["prs_last_year"]),
        stat_block(260, 158, "👀", "PR reviews", stats["reviews"], "last 365 days"),
        stat_block(24, 238, "💻", "Commits on graph", stats["commits"], "contribution graph"),
        stat_block(260, 238, "🗂️", "Repos contributed", stats["repos_contributed"], "last 365 days"),
    ]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{USERNAME} activity summary</title>
  <desc id="desc">Private and public GitHub activity summary</desc>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="4.5" fill="{COLORS['bg']}" stroke="{COLORS['border']}"/>
  <text x="24" y="34" fill="{COLORS['title']}" font-size="18" font-weight="600">Activity Summary</text>
  <text x="24" y="56" fill="{COLORS['muted']}" font-size="12">Private + public activity · powered by METRICS_TOKEN</text>
  {''.join(blocks)}
  <text x="24" y="{height - 14}" fill="{COLORS['muted']}" font-size="10">Graph total: {stats['graph_total']} · Private graph count: {stats['restricted']} · Updated {stats['updated']}</text>
</svg>
"""


def main() -> None:
    stats = fetch_stats()
    svg = build_svg(stats)
    os.makedirs(os.path.dirname(OUTPUT) or ".", exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        handle.write(svg)
    print(f"Wrote {OUTPUT}")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
