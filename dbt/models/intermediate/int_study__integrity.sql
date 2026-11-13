-- Editorial status of each study from the notices that update it (step 12): Crossref's
-- notices and the Retraction Watch database (v140); the most serious one wins. A notice
-- deposited years later still lands here, because the join is redone on every rebuild.
--   study_id: the DOI, or "pmid:<id>" for a Retraction Watch row with no DOI whose PubMed
--     ID is not one of our studies with a DOI (int_study__candidates resolves it).
--   Reinstatement (Retraction Watch; Aday, 2026-11-13): shown as "corrected", with its
--     notice, and it cancels the Retraction Watch retractions of the same study dated
--     on or before it. A publisher's retraction in Crossref still counts.
with crossref as (
    select
        updated_doi as study_id,
        case
            when update_type in ('retraction', 'withdrawal', 'removal') then 'retracted'
            when update_type = 'partial_retraction' then 'partially_retracted'
            when update_type = 'expression_of_concern' then 'concern'
            when update_type in ('correction', 'erratum') then 'corrected'
        end as integrity,
        notice_doi,
        updated_on,
        'crossref' as source
    from {{ ref('stg_crossref__notices') }}
),

pmid_to_doi as (
    select pmid, min(doi) as doi
    from {{ ref('int_study__candidates') }}
    where pmid is not null and doi is not null
    group by pmid
),

retraction_watch as (
    select
        coalesce(n.original_doi, d.doi, 'pmid:' || n.original_pmid) as study_id,
        case n.nature
            when 'retraction' then 'retracted'
            when 'expression_of_concern' then 'concern'
            when 'correction' then 'corrected'
            when 'reinstatement' then 'corrected'
        end as integrity,
        n.nature,
        nullif(n.notice_doi, n.original_doi) as notice_doi,  -- some notices reuse the DOI
        n.noticed_on as updated_on,
        'retraction_watch' as source
    from {{ ref('int_retractionwatch__notices') }} as n
    left join pmid_to_doi as d on d.pmid = n.original_pmid and n.original_doi is null
),

reinstated as (
    select study_id, max(updated_on) as reinstated_on
    from retraction_watch
    where nature = 'reinstatement'
    group by study_id
),

notices as (
    select study_id, integrity, notice_doi, updated_on, source from crossref
    union all
    select r.study_id, r.integrity, r.notice_doi, r.updated_on, r.source
    from retraction_watch as r
    left join reinstated as x using (study_id)
    where not (r.nature = 'retraction' and x.reinstated_on is not null
               and coalesce(r.updated_on <= x.reinstated_on, true))
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
    study_id,
    arg_min(integrity, severity) as integrity,
    list(distinct notice_doi order by notice_doi) filter (where notice_doi is not null)
        as notice_dois,
    list(distinct source order by source) as sources,
    max(updated_on) as last_notice_on
from ranked
group by study_id
