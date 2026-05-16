#!/usr/bin/env python3
"""
GitHub Repository Search Script
Searches GitHub repositories using the REST API and saves results to JSON.
"""

import os
import json
import time
import sys
from typing import List, Dict, Any, Optional
import requests


class GitHubSearcher:
    """Search and retrieve GitHub repositories using the REST Search API."""

    BASE_URL = "https://api.github.com/search/repositories"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def search_repositories(self, query: str, top_n: int = 30, sort: str = "stars") -> List[Dict[str, Any]]:
        results = []
        top_n = min(top_n, 1000)
        per_page = min(100, top_n)
        pages_needed = (top_n + per_page - 1) // per_page

        for page in range(1, pages_needed + 1):
            params = {
                "q": query,
                "sort": sort,
                "order": "desc",
                "per_page": per_page,
                "page": page,
            }

            try:
                response = self.session.get(self.BASE_URL, params=params, timeout=10)
                response.raise_for_status()

                self._check_rate_limit(response.headers)

                data = response.json()
                items = data.get("items", [])

                if not items:
                    break

                for repo in items:
                    if len(results) >= top_n:
                        break
                    results.append(self._extract_fields(repo))

                if len(results) >= top_n:
                    break

            except requests.exceptions.RequestException as e:
                print(f"Error fetching page {page}: {e}", file=sys.stderr)
                break

        return results[:top_n]

    def _extract_fields(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "full_name": repo.get("full_name"),
            "html_url": repo.get("html_url"),
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "description": repo.get("description"),
            "language": repo.get("language"),
            "updated_at": repo.get("updated_at"),
        }

    def _check_rate_limit(self, headers: Dict[str, str]) -> None:
        remaining = headers.get("X-RateLimit-Remaining")
        limit = headers.get("X-RateLimit-Limit")
        reset = headers.get("X-RateLimit-Reset")

        if remaining and limit:
            print(f"Rate limit: {remaining}/{limit} requests remaining", file=sys.stderr)

            if int(remaining) < 10 and reset:
                reset_time = int(reset)
                wait_time = reset_time - int(time.time())
                if wait_time > 0:
                    print(f"Approaching rate limit. Waiting {wait_time}s...", file=sys.stderr)
                    time.sleep(wait_time)

    def save_to_json(self, results: List[Dict[str, Any]], output_file: str = "github_results.json") -> None:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(results)} results to {output_file}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Search GitHub repositories and save results to JSON")
    parser.add_argument("query", help="Search query (e.g., 'language:python stars:>1000')")
    parser.add_argument("-n", "--top-n", type=int, default=30, help="Number of results to retrieve (default: 30, max: 1000)")
    parser.add_argument("-o", "--output", default="github_results.json", help="Output JSON file path (default: github_results.json)")
    parser.add_argument("-s", "--sort", default="stars", choices=["stars", "forks", "updated", "help-wanted-issues"], help="Sort order (default: stars)")
    parser.add_argument("-t", "--token", help="GitHub API token (uses GITHUB_TOKEN env var if not provided)")

    args = parser.parse_args()

    searcher = GitHubSearcher(token=args.token)

    print(f"Searching for: {args.query}")
    print(f"Requesting top {args.top_n} results (sorted by {args.sort})...")

    results = searcher.search_repositories(query=args.query, top_n=args.top_n, sort=args.sort)

    if results:
        print(f"Found {len(results)} results")
        searcher.save_to_json(results, args.output)
    else:
        print("No results found", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
