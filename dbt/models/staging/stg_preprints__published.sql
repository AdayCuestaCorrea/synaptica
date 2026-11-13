-- Journal version of each neuro preprint, from the bioRxiv / medRxiv "pubs" list
-- (raw/<server>/published/<date>.jsonl), one row per preprint and version.
{% set payload = 'STRUCT(preprint_doi VARCHAR, published_doi VARCHAR,
                         published_journal VARCHAR, published_date VARCHAR,
                         category VARCHAR)' %}
with batches as (
    select 'biorxiv' as server, * from {{ read_batches('biorxiv', 'published', payload) }}
    union all
    select 'medrxiv' as server, * from {{ read_batches('medrxiv', 'published', payload) }}
)

select
    key as preprint_doi,
    version_date,
    server,
    lower(payload.published_doi) as published_doi,
    payload.published_journal as published_journal,
    try_cast(payload.published_date as date) as published_on
from batches
