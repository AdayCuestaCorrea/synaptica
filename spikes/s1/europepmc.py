"""S1 · Europe PMC REST: recent open-access neuro articles, their licenses and full-text access."""

import datetime as dt
from collections import Counter

from common import client, get, save_json

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def main() -> None:
    today = dt.datetime.now(dt.UTC).date()
    since = today - dt.timedelta(days=7)
    query = (
        f"(TITLE_ABS:(brain OR neuron* OR neural OR cortex OR synap*)) "
        f"AND FIRST_PDATE:[{since} TO {today}]"
    )
    print("Europe PMC")
    with client() as c:
        r = get(c, f"{BASE}/search", params={"query": query, "format": "json", "pageSize": 1})
        print(f"  neuro records first published in the last 7 days: {r.json()['hitCount']}")
        r = get(c, f"{BASE}/search", params={
            "query": f"{query} AND OPEN_ACCESS:y", "format": "json", "pageSize": 10,
            "resultType": "core"})  # fmt: skip
        data = r.json()
        print(f"  of which open access: {data['hitCount']}")
        save_json("europepmc", "search_core.json", data)
        results = data["resultList"]["result"]
        print(f"  licenses: {dict(Counter(a.get('license', 'none') for a in results))}")
        print(f"  sources: {dict(Counter(a.get('source') for a in results))}")
        # Full text exists only for PMC articles; check access, do not keep the text.
        pmcid = next((a["pmcid"] for a in results if a.get("pmcid")), None)
        if pmcid:
            r = get(c, f"{BASE}/{pmcid}/fullTextXML")
            print(f"  full text {pmcid}: HTTP {r.status_code}, {len(r.content)} B (not stored)")


if __name__ == "__main__":
    main()
