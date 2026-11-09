"""S1 · Nature, Science, Cell and sister journals: RSS feed, with Crossref by ISSN as fallback.

Only metadata and links (CLAUDE.md): the article pages are never downloaded.
"""

import datetime as dt
import re

from common import client, get, save_json, save_text

from synaptica.config import CONTACT_EMAIL

# journal key: (name, RSS feed, ISSN that Crossref indexes: electronic, print for Cell Press)
JOURNALS = {
    "nature": ("Nature", "https://www.nature.com/nature.rss", "1476-4687"),
    "nature_neuroscience": ("Nature Neuroscience", "https://www.nature.com/neuro.rss", "1546-1726"),
    "nature_reviews_neuroscience": (
        "Nature Reviews Neuroscience",
        "https://www.nature.com/nrn.rss",
        "1471-0048",
    ),
    "science": (
        "Science",
        "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science",
        "1095-9203",
    ),
    "science_advances": (
        "Science Advances",
        "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv",
        "2375-2548",
    ),
    "cell": ("Cell", "https://www.cell.com/cell/current.rss", "0092-8674"),
    "neuron": ("Neuron", "https://www.cell.com/neuron/current.rss", "0896-6273"),
}


def main() -> None:
    since = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=14)
    with client() as c:
        for key, (name, feed, issn) in JOURNALS.items():
            print(name)
            r = get(c, feed, pause=1.0)
            items = re.findall(r"<item\b", r.text)
            is_feed = r.status_code == 200 and (
                "<rss" in r.text[:500] or "<rdf:RDF" in r.text[:500]
            )
            dois = re.findall(r"10\.\d{4,9}/[^\s<\"]+", r.text)
            print(f"  RSS: {'ok' if is_feed else 'NOT a feed'}, {len(items)} items, "
                  f"{len(set(dois))} DOIs")  # fmt: skip
            if is_feed:
                save_text("journals", f"{key}.rss.xml", r.text)
            r = get(c, f"https://api.crossref.org/journals/{issn}/works", params={
                "filter": f"from-pub-date:{since}", "rows": 10, "sort": "published",
                "order": "desc", "mailto": CONTACT_EMAIL})  # fmt: skip
            if r.status_code == 200:
                msg = r.json()["message"]
                print(f"  Crossref: {msg['total-results']} works in 14 days")
                save_json("journals", f"{key}.crossref.json", r.json())


if __name__ == "__main__":
    main()
