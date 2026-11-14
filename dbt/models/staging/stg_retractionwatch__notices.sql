-- One row per Retraction Watch record and version (raw/retractionwatch/notices/<date>.jsonl,
-- written by synaptica.ingest.retractionwatch): only the rows that changed that day.
with batches as (
    select * from {{ read_batches('retractionwatch', 'notices',
        'STRUCT(doi VARCHAR, pmid VARCHAR, nature VARCHAR, notice_doi VARCHAR,
                date VARCHAR, removed BOOLEAN)') }}
)

select
    key as record_id,
    version_date,
    payload.doi as original_doi,
    payload.pmid as original_pmid,
    payload.nature,
    payload.notice_doi,
    try_cast(payload.date as date) as noticed_on,
    coalesce(payload.removed, false) as removed
from batches
