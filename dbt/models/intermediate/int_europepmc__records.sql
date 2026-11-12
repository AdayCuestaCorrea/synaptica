-- One row per Europe PMC open-access record: its latest version and the day it was first
-- stored. MED records are also in PubMed; PMC and PPR ones may not be.
with versions as (
    select
        *,
        min(version_date) over (partition by epmc_key) as entered_on,
        row_number() over (partition by epmc_key order by version_date desc) as rn
    from {{ ref('stg_europepmc__records') }}
)

select * exclude (rn, version_date)
from versions
where rn = 1
