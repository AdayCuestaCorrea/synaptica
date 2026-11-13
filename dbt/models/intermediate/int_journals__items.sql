-- One row per journal feed item, with its kind: research | review | correction | news.
-- The section comes from the feed (seed journal_sections); Nature's feeds carry none,
-- so its DOIs decide: 10.1038/s… are papers (corrections by their title) and 10.1038/d…
-- news. Anything unmapped is news, never a study.
with versions as (
    select
        *,
        min(version_date) over (partition by item_key) as entered_on,
        row_number() over (partition by item_key order by version_date desc) as rn
    from {{ ref('stg_journals__items') }}
)

select
    v.item_key,
    v.journal,
    j.name as journal_name,
    j.scope as journal_scope,
    v.doi,
    v.url,
    v.title,
    v.authors,
    v.published_at,
    v.entered_on,
    v.section,
    v.via,
    case
        when s.kind is not null then s.kind
        when v.section is null and v.doi like '10.1038/s%' then
            case
                when regexp_matches(v.title, '^(Author|Publisher) Correction|^Retraction Note')
                    then 'correction'
                when j.journal = 'nature_reviews_neuroscience' then 'review'
                else 'research'
            end
        else 'news'
    end as kind
from versions as v
left join {{ ref('journal_sections') }} as s on s.section = v.section
left join {{ ref('journals') }} as j on j.journal = v.journal
where v.rn = 1
