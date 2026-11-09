"""S1 · Study signals and citations: Crossref (retractions, corrections) and OpenAlex (Classics)."""

import datetime as dt
from collections import Counter

from common import client, get, save_json

from synaptica.config import CONTACT_EMAIL

# Lesné et al. 2006 (Nature), retracted in 2024: a known neuro retraction to check against.
RETRACTED_DOI = "10.1038/nature04533"
# OpenAlex topic taxonomy: field 28 is Neuroscience (checked against the response below).
NEURO_FIELD = "28"


def crossref(c) -> None:
    print("Crossref")
    r = get(c, f"https://api.crossref.org/works/{RETRACTED_DOI}", params={"mailto": CONTACT_EMAIL})
    work = r.json()["message"]
    updates = work.get("updated-by", [])
    print(f"  {RETRACTED_DOI}: updated-by {[(u.get('type'), u.get('source')) for u in updates]}")
    save_json("crossref", "work_retracted.json", r.json())
    since = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=30)
    for kind in ("retraction", "correction"):
        r = get(c, "https://api.crossref.org/works", params={
            "filter": f"update-type:{kind},from-update-date:{since}", "rows": 10,
            "mailto": CONTACT_EMAIL})  # fmt: skip
        msg = r.json()["message"]
        print(f"  {kind} notices in 30 days (all fields): {msg['total-results']}")
        save_json("crossref", f"notices_{kind}.json", r.json())


def openalex(c) -> None:
    print("OpenAlex")
    year = dt.datetime.now(dt.UTC).year - 10
    r = get(c, "https://api.openalex.org/works", params={
        "filter": f"primary_topic.field.id:{NEURO_FIELD},publication_year:{year}",
        "sort": "cited_by_count:desc", "per_page": 10, "mailto": CONTACT_EMAIL})  # fmt: skip
    if r.status_code != 200:
        print(f"  {r.text[:300]}")
        return
    data = r.json()
    fields = Counter(w["primary_topic"]["field"]["display_name"] for w in data["results"])
    print(f"  neuro works from {year}: {data['meta']['count']}; fields {dict(fields)}")
    print(f"  most cited: {[w['cited_by_count'] for w in data['results']]}")
    save_json("openalex", f"works_most_cited_{year}.json", data)


def main() -> None:
    with client() as c:
        crossref(c)
        openalex(c)


if __name__ == "__main__":
    main()
