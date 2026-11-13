-- One row per PubMed record and version of its MEDLINE indexing
-- (raw/pubmed/medline/<date>.jsonl). MeSH may be missing for weeks (status Publisher,
-- In-Process…) and never arrives for journals outside MEDLINE (PubMed-not-MEDLINE).
with batches as (
    select * from {{ read_batches('pubmed', 'medline',
        'STRUCT(status VARCHAR,
                mesh STRUCT(ui VARCHAR, name VARCHAR, major BOOLEAN, qualifiers VARCHAR[])[],
                publication_types STRUCT(ui VARCHAR, name VARCHAR)[],
                keywords VARCHAR[], has_abstract BOOLEAN)') }}
)

select
    key as pmid,
    version_date,
    payload.status as medline_status,
    payload.mesh as mesh,
    list_transform(payload.mesh, lambda m: m.ui) as mesh_uis,
    list_transform(payload.publication_types, lambda p: p.name) as publication_types,
    payload.keywords as keywords,
    payload.has_abstract as has_abstract
from batches
