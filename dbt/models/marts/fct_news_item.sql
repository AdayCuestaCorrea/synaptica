-- One row per news item for Neuro News: popular-science articles (SINC, The Conversation,
-- ScienceDaily) and the non-research items of the journal feeds (news, commentary,
-- perspectives). Research papers and reviews are studies (dim_study); corrections are
-- neither. is_neuro: true for neuro feeds and journals by their scope; for the general
-- ones (SINC's Noticias; Nature, Science, Cell) the step 13 decision, false until made.
with news as (
    select
        *,
        min(version_date) over (partition by item_key) as entered_on,
        row_number() over (partition by item_key order by version_date desc) as rn
    from {{ ref('stg_news__items') }}
),

decisions as (
    select * from {{ ref('stg_derived__neuro') }}
),

items as (
    select
        'news:' || n.item_key as news_item_id,
        'outlet' as origin,
        n.outlet,
        n.feed,
        n.lang,
        n.url,
        n.title,
        n.authors,
        n.published_at,
        n.entered_on,
        cast(null as varchar) as doi,
        cast(null as varchar) as section,
        n.feed_summary,
        case when f.scope = 'neuro' then 'feed_scope' when d.is_neuro then d.neuro_basis end
            as neuro_basis
    from news as n
    left join {{ ref('news_feeds') }} as f on f.feed = n.feed
    left join decisions as d on d.item_source = 'news' and d.item_key = n.item_key
    where n.rn = 1

    union all

    select
        'journal:' || j.item_key,
        'journal',
        j.journal_name,
        j.journal,
        'en',
        j.url,
        j.title,
        j.authors,
        j.published_at,
        j.entered_on,
        j.doi,
        j.section,
        null,
        case when j.journal_scope = 'neuro' then 'journal_scope'
             when d.is_neuro then d.neuro_basis end
    from {{ ref('int_journals__items') }} as j
    left join decisions as d on d.item_source = 'journals' and d.item_key = j.item_key
    where j.kind = 'news'
)

-- story_id: same-story group (step 15); an item never grouped is its own story.
select
    i.*,
    i.neuro_basis is not null as is_neuro,
    t.news_type,
    coalesce(g.story_id, i.news_item_id) as story_id
from items as i
left join {{ ref('stg_derived__news_types') }} as t on t.item_id = i.news_item_id
left join {{ ref('stg_derived__news_groups') }} as g on g.news_item_id = i.news_item_id
