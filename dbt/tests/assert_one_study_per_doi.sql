-- A DOI should belong to one study; two PMIDs with the same DOI would show the same work
-- twice (and split its signals). A warning: PubMed has rare duplicates we cannot fix.
{{ config(severity='warn') }}
select doi, count(*) as studies
from {{ ref('dim_study') }}
where doi is not null
group by doi
having count(*) > 1
