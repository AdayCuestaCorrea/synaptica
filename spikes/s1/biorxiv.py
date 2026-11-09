"""S1 · bioRxiv / medRxiv API: weekly preprint volume per neuro category, licenses, 10 items."""

import datetime as dt
from collections import Counter

import httpx
from common import client, get, save_json

BASE = "https://api.biorxiv.org/details"
# The API filters by category (lower case, underscores for spaces).
CATEGORIES = {
    "biorxiv": ["neuroscience"],
    "medrxiv": ["neurology", "psychiatry_and_clinical_psychology"],
}


def fetch(c: httpx.Client, url: str, params: dict) -> httpx.Response:
    """The API is slow: long timeout and one retry."""
    for attempt in (1, 2):
        try:
            return get(c, url, params=params, pause=1.0, timeout=120.0)
        except httpx.TimeoutException:
            print(f"  timeout (attempt {attempt})")
    raise SystemExit(f"{url}: no response after 2 attempts of 120 s")


def main() -> None:
    today = dt.datetime.now(dt.UTC).date()
    since = today - dt.timedelta(days=7)
    with client() as c:
        for server, categories in CATEGORIES.items():
            print(server)
            for category in categories:
                r = fetch(c, f"{BASE}/{server}/{since}/{today}/0", {"category": category})
                body = r.json()
                items = body.get("collection", [])
                total = body["messages"][0].get("total")
                print(f"  {category}: {total} preprints in 7 days (first page: {len(items)})")
                print(f"  licenses: {dict(Counter(i.get('license') for i in items))}")
                body["collection"] = items[:10]
                save_json(server, f"details_{category}.json", body)


if __name__ == "__main__":
    main()
