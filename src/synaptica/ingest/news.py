"""Popular-science news: SINC, The Conversation (EN/ES) and ScienceDaily.

Copied and adapted from paleo-atlas ``src/paleo/ingest/news.py`` (same author, AGPL in
both; decision D2). Same rules: only outlets whose terms allow reuse, listed with their
licence in the seed ``dbt/seeds/news_feeds.csv``; the headline, link, date and, where the
licence allows it (``store_summary``), the feed's own summary, unmodified. One key per
article (a hash of its canonical link), so an article in two feeds of the same outlet
(The Conversation's *neurociencia* and *cerebro*) is stored once.

Changes from Paleo: parsing lives in :mod:`synaptica.ingest.feeds` (shared with the
journals), and items go to a daily batch (``raw/news/items/<date>.jsonl``) compared with
the last :data:`LOOKBACK_DAYS` days, instead of one folder per article: SINC's
*Noticias* feed alone lists 150 items of every subject, covering ~46 days (S1).
Everything in the feeds is stored; which items are neuroscience is decided downstream
(plan, step 13).
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from synaptica.config import project_root
from synaptica.http import HttpError, Throttle, get_text
from synaptica.ingest.feeds import item_key, parse_feed
from synaptica.store import BatchStore, utc_today

log = logging.getLogger(__name__)

LOOKBACK_DAYS = 90  # longer than SINC's 46 days of items


@dataclass(frozen=True)
class Feed:
    feed: str
    outlet: str
    lang: str
    url: str
    license: str
    store_summary: bool


@dataclass
class NewsResult:
    feeds: int = 0
    items: int = 0
    new_versions: int = 0
    failed: list[str] = field(default_factory=list)


def store(raw_root: Path | None = None) -> BatchStore:
    return BatchStore("news", "items", raw_root=raw_root)


def load_feeds(seed: Path | None = None) -> list[Feed]:
    path = seed or project_root() / "dbt" / "seeds" / "news_feeds.csv"
    with path.open(encoding="utf-8") as f:
        return [
            Feed(
                r["feed"],
                r["outlet"],
                r["lang"],
                r["url"],
                r["license"],
                r["store_summary"] == "true",
            )
            for r in csv.DictReader(f)
        ]


def fetch_feed(client: httpx.Client, feed: Feed) -> list[dict[str, Any]]:
    items = parse_feed(get_text(client, feed.url, retries=2), keep_summary=feed.store_summary)
    return [
        {"url": i["url"], "outlet": feed.outlet, "lang": feed.lang, "feed": feed.feed,
         "title": i["title"], "published": i["published"], "authors": i["authors"],
         **({"summary": i["summary"]} if "summary" in i else {})}
        for i in items
    ]  # fmt: skip


def ingest(
    client: httpx.Client,
    feeds: list[Feed] | None = None,
    *,
    today: dt.date | None = None,
    raw_root: Path | None = None,
    throttle: Throttle | None = None,
) -> NewsResult:
    """Every article of every feed; a feed that fails is logged and skipped."""
    today = today or utc_today()
    throttle = throttle or Throttle(1)
    feeds = feeds if feeds is not None else load_feeds()
    result, found = NewsResult(feeds=len(feeds)), {}
    for feed in feeds:
        try:
            throttle.wait()
            payloads = fetch_feed(client, feed)
        except (HttpError, httpx.HTTPError, ET.ParseError) as exc:
            log.warning("News feed %s failed: %s", feed.feed, exc)
            result.failed.append(feed.feed)
            continue
        for payload in payloads:
            found.setdefault(item_key(payload["url"]), payload)  # first feed wins
    result.items = len(found)
    batches = store(raw_root)
    previous = {k: e.payload for k, e in batches.recent(LOOKBACK_DAYS, today).items()}
    result.new_versions = batches.save(found, today, previous=previous)
    return result


def has_new_items(
    client: httpx.Client,
    feeds: list[Feed] | None = None,
    *,
    today: dt.date | None = None,
    raw_root: Path | None = None,
) -> bool:
    """Whether any feed lists an article not stored yet (nothing is saved). A failing
    feed is skipped; if every feed fails, the error propagates (``syn check`` exits 2)."""
    today = today or utc_today()
    feeds = feeds if feeds is not None else load_feeds()
    stored = store(raw_root).recent(LOOKBACK_DAYS, today)
    errors = []
    for feed in feeds:
        try:
            payloads = fetch_feed(client, feed)
        except (HttpError, httpx.HTTPError, ET.ParseError) as exc:
            log.warning("News feed %s failed: %s", feed.feed, exc)
            errors.append(exc)
            continue
        if any(item_key(p["url"]) not in stored for p in payloads):
            return True
    if errors and len(errors) == len(feeds):
        raise HttpError(f"every news feed failed: {errors[0]}")
    return False
