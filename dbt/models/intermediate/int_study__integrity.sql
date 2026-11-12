-- Editorial status of each DOI from the Crossref notices that update it (step 12): the
-- most serious one wins. A notice deposited years later still lands here, because the
-- join is by DOI on every rebuild.
with notices as (
    select
        updated_doi as doi,
        case
            when update_type in ('retraction', 'withdrawal', 'removal') then 'retracted'
            when update_type = 'partial_retraction' then 'partially_retracted'
            when update_type = 'expression_of_concern' then 'concern'
            when update_type in ('correction', 'erratum') then 'corrected'
        end as integrity,
        notice_doi,
        updated_on
    from {{ ref('stg_crossref__notices') }}
),

ranked as (
    select
        *,
        case integrity
            when 'retracted' then 1 when 'partially_retracted' then 2
            when 'concern' then 3 when 'corrected' then 4
        end as severity
    from notices
    where integrity is not null
)

select
    doi,
    arg_min(integrity, severity) as integrity,
    list(distinct notice_doi order by notice_doi) as notice_dois,
    max(updated_on) as last_notice_on
from ranked
group by doi
