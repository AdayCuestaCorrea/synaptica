-- The current state of each Retraction Watch record: its latest version, unless the record
-- left the CSV. A record can change kind (a retraction that becomes a reinstatement keeps
-- its record ID), so only the latest version counts.
select
    record_id,
    arg_max(original_doi, version_date) as original_doi,
    arg_max(original_pmid, version_date) as original_pmid,
    arg_max(nature, version_date) as nature,
    arg_max(notice_doi, version_date) as notice_doi,
    arg_max(noticed_on, version_date) as noticed_on
from {{ ref('stg_retractionwatch__notices') }}
group by record_id
having not arg_max(removed, version_date)
