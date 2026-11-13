-- One row per journal feed item and version (raw/journals/items/<date>.jsonl, written by
-- synaptica.ingest.journals): metadata and links only, never the publisher's text.
with batches as (
    select * from {{ read_batches('journals', 'items',
        'STRUCT(url VARCHAR, title VARCHAR, published VARCHAR, doi VARCHAR,
                authors VARCHAR[], section VARCHAR, journal VARCHAR, via VARCHAR)') }}
)

select
    key as item_key,
    version_date,
    payload.journal as journal,
    lower(nullif(payload.doi, '')) as doi,
    payload.url as url,
    nullif(trim(payload.title), '') as title,
    payload.authors as authors,
    try_cast(payload.published as timestamptz) as published_at,
    nullif(payload.section, '') as section,
    payload.via as via
from batches
