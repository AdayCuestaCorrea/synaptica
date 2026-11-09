"""S1 · Later-phase sources: ClinicalTrials.gov, nobelprize.org, Wikipedia, Wikidata, Commons.

The brain atlases (Julich-Brain, Waxholm, Allen, BrainGlobe) are checked in spike S3.
"""

from common import client, get, save_json

WIKI_PARAMS = {"format": "json", "formatversion": 2, "maxlag": 5}


def clinicaltrials(c) -> None:
    print("ClinicalTrials.gov")
    r = get(c, "https://clinicaltrials.gov/api/v2/studies", params={
        "query.cond": "Alzheimer Disease", "query.locn": "Spain",
        "filter.overallStatus": "RECRUITING", "pageSize": 10, "countTotal": "true",
        "fields": "NCTId,BriefTitle,OverallStatus,Condition,Phase,StudyType,"
                  "StartDate,LastUpdatePostDate,LeadSponsorName,LocationCity,LocationCountry",
    })  # fmt: skip
    data = r.json()
    print(f"  Alzheimer, recruiting in Spain: {data.get('totalCount')}")
    save_json("clinicaltrials", "studies_alzheimer_spain.json", data)


def nobel(c) -> None:
    print("nobelprize.org")
    r = get(c, "https://api.nobelprize.org/2.1/nobelPrizes", params={
        "nobelPrizeYear": 2026, "nobelPrizeCategory": "med"})  # fmt: skip
    data = r.json()
    for prize in data.get("nobelPrizes", []):
        names = [lau.get("knownName", {}).get("en") for lau in prize.get("laureates", [])]
        print(f"  {prize['awardYear']} medicine: {names}")
        print(f"  motivation: {prize['laureates'][0]['motivation']['en']}")
    save_json("nobelprize", "medicine_2026.json", data)


def wikimedia(c) -> None:
    print("Wikipedia (EN/ES)")
    for lang, title in (("en", "Hippocampus"), ("es", "Hipocampo (anatomía)")):
        r = get(c, f"https://{lang}.wikipedia.org/w/api.php", params={
            **WIKI_PARAMS, "action": "query", "prop": "revisions|pageprops", "titles": title,
            "rvprop": "ids|timestamp", "redirects": 1})  # fmt: skip
        page = r.json()["query"]["pages"][0]
        print(f"  {lang}: {page.get('title')} rev {page['revisions'][0]['revid']}, "
              f"wikidata {page.get('pageprops', {}).get('wikibase_item')}")  # fmt: skip
        save_json("wikipedia", f"{lang}_{title.split()[0].lower()}.json", r.json())
    print("Wikidata")
    r = get(c, "https://www.wikidata.org/w/api.php", params={
        **WIKI_PARAMS, "action": "wbsearchentities", "search": "Parkinson's disease",
        "language": "en", "limit": 1})  # fmt: skip
    qid = r.json()["search"][0]["id"]
    r = get(c, "https://www.wikidata.org/w/api.php", params={
        **WIKI_PARAMS, "action": "wbgetentities", "ids": qid, "props": "labels|sitelinks|claims",
        "languages": "en|es", "sitefilter": "enwiki|eswiki"})  # fmt: skip
    data = r.json()
    entity = data["entities"][qid]
    print(f"  {qid}: {entity['labels']['en']['value']} / {entity['labels']['es']['value']}, "
          f"{len(entity['claims'])} properties")  # fmt: skip
    # Keep instance of, subclass of and anatomical location (disease -> brain region).
    keep = ("P31", "P279", "P927")
    entity["claims"] = {k: v for k, v in entity["claims"].items() if k in keep}
    save_json("wikidata", f"{qid}.json", data)
    print("Wikimedia Commons")
    r = get(c, "https://commons.wikimedia.org/w/api.php", params={
        **WIKI_PARAMS, "action": "query", "generator": "search", "gsrsearch": "hippocampus brain",
        "gsrnamespace": 6, "gsrlimit": 10, "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|Artist|Credit"})  # fmt: skip
    pages = r.json()["query"]["pages"]
    meta = [p["imageinfo"][0]["extmetadata"] for p in pages]
    licenses = [m.get("LicenseShortName", {}).get("value") for m in meta]
    print(f"  licenses of 10 files: {licenses}")
    save_json("commons", "search_hippocampus.json", r.json())


def main() -> None:
    with client() as c:
        clinicaltrials(c)
        nobel(c)
        wikimedia(c)


if __name__ == "__main__":
    main()
