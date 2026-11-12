-- One row per news item for Neuro News: popular-science articles (SINC, The Conversation,
-- ScienceDaily) and the non-research items of the journal feeds (news, commentary,
-- perspectives). Research papers and reviews are studies (dim_study); corrections are
-- neither. Which items are neuroscience is decided in step 13.
with news as (
    select
        *,
        min(version_date) over (partition by item_key) as entered_on,
        row_number() over (partition by item_key order by version_date desc) as rn
    from {{ ref('stg_news__items') }}
)

select
    'news:' || item_key as news_item_id,
    'outlet' as origin,
    outlet,
    feed,
    lang,
    url,
    title,
    authors,
    published_at,
    entered_on,
    cast(null as varchar) as doi,
    cast(null as varchar) as section,
    feed_summary
from news
where rn = 1

union all

select
    'journal:' || item_key,
    'journal',
    journal_name,
    journal,
    'en',
    url,
    title,
    authors,
    published_at,
    entered_on,
    doi,
    section,
    null
from {{ ref('int_journals__items') }}
where kind = 'news'
