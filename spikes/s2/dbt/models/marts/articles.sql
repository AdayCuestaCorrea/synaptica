-- Articles with the signals of SCOPE §4 that the metadata already gives.
select
    pmid,
    title,
    journal,
    pub_date,
    doi,
    pub_types like '%review%' as is_review,
    pub_types like '%meta-analysis%' as is_meta_analysis,
    pub_types like '%preprint%' as is_preprint
from {{ ref('stg_pubmed__articles') }}
