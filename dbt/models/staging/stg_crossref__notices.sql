-- One row per notice, version and DOI it updates (raw/crossref/notices/<date>.jsonl,
-- written by synaptica.ingest.crossref). A notice can update several DOIs.
with batches as (
    select * from {{ read_batches('crossref', 'notices',
        'STRUCT(doi VARCHAR,
                updates STRUCT(doi VARCHAR, type VARCHAR, source VARCHAR, date VARCHAR)[])') }}
),

updates as (
    select key as notice_doi, version_date, unnest(payload.updates) as u
    from batches
)

select
    notice_doi,
    version_date,
    u.doi as updated_doi,
    u.type as update_type,
    u.source as update_source,
    try_cast(u.date as date) as updated_on
from updates
