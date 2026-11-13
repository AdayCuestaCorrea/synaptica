-- One row per PubMed record and version (raw/pubmed/summary/<date>.jsonl, written by
-- synaptica.ingest.pubmed). Only the fields the ingestion keeps (SUMMARY_FIELDS).
with batches as (
    select * from {{ read_batches('pubmed', 'summary',
        'STRUCT(uid VARCHAR, title VARCHAR, source VARCHAR, fulljournalname VARCHAR,
                issn VARCHAR, essn VARCHAR, pubdate VARCHAR, epubdate VARCHAR,
                sortpubdate VARCHAR, lang VARCHAR[], pubtype VARCHAR[], pubstatus VARCHAR,
                articleids MAP(VARCHAR, VARCHAR), authors VARCHAR[])') }}
)

select
    key as pmid,
    version_date,
    nullif(trim(payload.title), '') as title,
    nullif(payload.fulljournalname, '') as journal,
    nullif(payload.source, '') as journal_abbrev,
    nullif(payload.issn, '') as issn,
    nullif(payload.essn, '') as essn,
    try_cast(strptime(payload.sortpubdate, '%Y/%m/%d %H:%M') as date) as published_on,
    payload.lang as languages,
    payload.pubtype as publication_types,
    nullif(payload.pubstatus, '') as pub_status,
    lower(nullif(payload.articleids['doi'], '')) as doi,
    nullif(payload.articleids['pmc'], '') as pmcid,
    payload.authors as authors
from batches
