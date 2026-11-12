-- One row per preprint DOI: its highest version, the day it was first stored and the DOI
-- of its journal version, from the preprint itself or from the "pubs" list (which comes
-- weeks later and is the usual source of the link).
with versions as (
    select
        *,
        min(version_date) over (partition by doi) as entered_on,
        row_number() over (
            partition by doi order by version desc, version_date desc
        ) as rn
    from {{ ref('stg_preprints') }}
),

links as (
    select preprint_doi, arg_max(published_doi, version_date) as published_doi
    from {{ ref('stg_preprints__published') }}
    group by preprint_doi
)

select
    v.doi,
    v.server,
    v.title,
    v.authors,
    v.version,
    v.version_posted_on,
    v.entered_on,
    v.preprint_type,
    v.license,
    v.category,
    coalesce(l.published_doi, v.published_doi) as published_doi
from versions as v
left join links as l on l.preprint_doi = v.doi
where v.rn = 1
