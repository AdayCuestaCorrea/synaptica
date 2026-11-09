-- One row per PubMed article (spike S2). Metadata only: no abstracts.
select
    cast(pmid as {{ dbt.type_string() }}) as pmid,
    title,
    journal,
    cast(pub_date as date) as pub_date,
    lower(pub_types) as pub_types,
    lang,
    nullif(doi, '') as doi
from {{ ref('pubmed_articles') }}
