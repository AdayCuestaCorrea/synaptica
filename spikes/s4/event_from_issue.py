"""S4 · Turn a real review Issue into the event that ``intake.py`` reads.

While the intake workflow is not active (the test with Sofía, step 6 of PLAN.md), Aday
or Claude runs the intake by hand on her Issue. ``gh`` reads the Issue (network, outside
the tests) and ``to_event`` gives it the shape of the ``issues: opened`` webhook payload,
like ``tests/fixtures/review/issue_opened_1.json``. Run from the repo root:

    uv run --group spike-s4 python spikes/s4/event_from_issue.py 12 > event.json
"""

from __future__ import annotations

import json
import subprocess
import sys

FIELDS = "number,title,author,createdAt,labels,body"


def to_event(issue: dict) -> dict:
    """``gh issue view --json`` output -> the fields of the webhook event the intake reads."""
    return {
        "action": "opened",
        "issue": {
            "number": issue["number"],
            "title": issue["title"],
            "user": {"login": issue["author"]["login"]},
            "created_at": issue["createdAt"],
            "labels": [{"name": label["name"]} for label in issue["labels"]],
            "body": issue["body"],
        },
    }


def main() -> None:
    number = sys.argv[1]
    raw = subprocess.run(
        ["gh", "issue", "view", number, "--json", FIELDS],
        check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip
    print(json.dumps(to_event(json.loads(raw)), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
