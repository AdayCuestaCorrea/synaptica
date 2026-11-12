-- One row per bioRxiv / medRxiv preprint (latest version known that day) and version
-- (raw/<server>/preprints/<date>.jsonl, written by synaptica.ingest.biorxiv).
{% set payload = 'STRUCT(doi VARCHAR, server VARCHAR, title VARCHAR, authors VARCHAR[],
                         date VARCHAR, version INTEGER, type VARCHAR, license VARCHAR,
                         category VARCHAR, published_doi VARCHAR, jatsxml VARCHAR)' %}
with batches as (
    select 'biorxiv' as server, * from {{ read_batches('biorxiv', 'preprints', payload) }}
    union all
    select 'medrxiv' as server, * from {{ read_batches('medrxiv', 'preprints', payload) }}
)

select
    key as doi,
    version_date,
    server,
    nullif(trim(payload.title), '') as title,
    payload.authors as authors,
    try_cast(payload.date as date) as version_posted_on,
    payload.version as version,
    payload.type as preprint_type,
    payload.license as license,
    payload.category as category,
    nullif(payload.published_doi, '') as published_doi
from batches
