-- One row per Europe PMC open-access record and version (raw/europepmc/records/<date>.jsonl,
-- written by synaptica.ingest.europepmc). Key: "<source>:<id>" (MED: also in PubMed).
with batches as (
    select * from {{ read_batches('europepmc', 'records',
        'STRUCT(source VARCHAR, id VARCHAR, pmid VARCHAR, pmcid VARCHAR, doi VARCHAR,
                title VARCHAR, authors VARCHAR[], journal VARCHAR, issn VARCHAR,
                essn VARCHAR, first_published VARCHAR, first_indexed VARCHAR,
                pub_types VARCHAR[], language VARCHAR, is_open_access BOOLEAN,
                in_epmc BOOLEAN, license VARCHAR, mesh VARCHAR[], keywords VARCHAR[])') }}
)

select
    key as epmc_key,
    version_date,
    payload.source as epmc_source,
    nullif(payload.pmid, '') as pmid,
    nullif(payload.pmcid, '') as pmcid,
    lower(nullif(payload.doi, '')) as doi,
    nullif(trim(payload.title), '') as title,
    payload.authors as authors,
    nullif(payload.journal, '') as journal,
    try_cast(payload.first_published as date) as published_on,
    try_cast(payload.first_indexed as date) as indexed_on,
    coalesce(payload.pub_types, []) as publication_types,
    payload.language as language,
    payload.is_open_access as is_open_access,
    nullif(payload.license, '') as license,
    coalesce(payload.mesh, []) as mesh_names
from batches
