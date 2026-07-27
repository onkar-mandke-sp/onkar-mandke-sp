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
    "accent": "#d08770",
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


def search_total(query: str) -> int:
    url = f"https://api.github.com/search/issues?q={urllib.parse.quote(query)}&per_page=1"
    try:
        return int(request_json(url).get("total_count", 0))
    except urllib.error.HTTPError:
        return 0


def fetch_stats() -> dict[str, int | str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=365)
    variables = {
        "login": USERNAME,
        "from": start.strftime("%Y-%m-%dT00:00:00Z"),
        "to": now.strftime("%Y-%m-%dT23:59:59Z"),
    }
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalPullRequestReviewContributions
          restrictedContributionsCount
          contributionCalendar {
            totalContributions
          }
        }
        repositoriesContributedTo(
          contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]
          includeUserRepositories: true
        ) {
          totalCount
        }
      }
    }
    """
    payload = request_json("https://api.github.com/graphql", method="POST", payload={"query": query, "variables": variables})
    if "errors" in payload:
        raise RuntimeError(json.dumps(payload["errors"]))

    user = payload["data"]["user"]
    collection = user["contributionsCollection"]
    calendar = collection["contributionCalendar"]

    return {
        "commits": collection["totalCommitContributions"],
        "prs_graph": collection["totalPullRequestContributions"],
        "issues": collection["totalIssueContributions"],
        "reviews": collection["totalPullRequestReviewContributions"],
        "repos_contributed": collection.get("totalRepositoryContributions")
        or user["repositoriesContributedTo"]["totalCount"],
        "graph_total": calendar["totalContributions"],
        "restricted": collection["restrictedContributionsCount"],
        "prs_search": search_total(f"author:{USERNAME}+type:pr+created:>={start.date().isoformat()}"),
        "prs_merged": search_total(f"author:{USERNAME}+type:pr+is:merged+created:>={start.date().isoformat()}"),
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
        stat_block(24, 78, "🔀", "Pull requests (last year)", stats["prs_search"], "includes private repos"),
        stat_block(260, 78, "✅", "Merged PRs", stats["prs_merged"]),
        stat_block(24, 158, "💻", "Commits on graph", stats["commits"], "contribution graph count"),
        stat_block(260, 158, "👀", "PR reviews", stats["reviews"]),
        stat_block(24, 238, "🗂️", "Repos contributed to", stats["repos_contributed"]),
        stat_block(260, 238, "🔒", "Private graph activity", stats["restricted"], "aggregate only"),
    ]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{USERNAME} activity summary</title>
  <desc id="desc">Private and public GitHub activity for the last year</desc>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="4.5" fill="{COLORS['bg']}" stroke="{COLORS['border']}"/>
  <text x="24" y="34" fill="{COLORS['title']}" font-size="18" font-weight="600">Activity Summary</text>
  <text x="24" y="56" fill="{COLORS['muted']}" font-size="12">Last 365 days · includes private activity via PAT</text>
  {''.join(blocks)}
  <text x="24" y="{height - 14}" fill="{COLORS['muted']}" font-size="10">Graph total: {stats['graph_total']} · Updated {stats['updated']}</text>
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
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
