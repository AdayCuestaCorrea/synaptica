"""S1 · PubMed E-utilities: weekly volume of neuro records and 10 of them (esummary + efetch)."""

import os

from common import client, get, save_json, save_text

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# Broad on purpose: new records have no MeSH terms yet, so title/abstract words matter.
TERM = (
    '"nervous system"[MeSH] OR "nervous system diseases"[MeSH] OR brain[tiab] '
    "OR neuron*[tiab] OR neural[tiab] OR cortex[tiab] OR synap*[tiab]"
)


def main() -> None:
    common = {"db": "pubmed", "tool": "synaptica", "email": "adaycuestacorrea@gmail.com"}
    if key := os.environ.get("NCBI_API_KEY"):
        common["api_key"] = key
    print(f"PubMed (API key: {'yes' if key else 'no'})")
    with client() as c:
        for days in (1, 7):
            r = get(c, f"{BASE}/esearch.fcgi", params={
                **common, "term": TERM, "reldate": days, "datetype": "edat",
                "retmax": 10, "retmode": "json"})  # fmt: skip
            print(
                f"  records entered in the last {days} day(s): {r.json()['esearchresult']['count']}"
            )
        search = r.json()
        save_json("pubmed", "esearch.json", search)
        ids = ",".join(search["esearchresult"]["idlist"])
        r = get(c, f"{BASE}/esummary.fcgi", params={**common, "id": ids, "retmode": "json"})
        save_json("pubmed", "esummary.json", r.json())
        r = get(c, f"{BASE}/efetch.fcgi", params={**common, "id": ids, "retmode": "xml"})
        save_text("pubmed", "efetch.xml", r.text)


if __name__ == "__main__":
    main()
