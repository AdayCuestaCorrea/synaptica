-- One row per news article and version (raw/news/items/<date>.jsonl, written by
-- synaptica.ingest.news). The summary is the feed's own, stored only where its licence
-- allows it (seed news_feeds.csv).
with batches as (
    select * from {{ read_batches('news', 'items',
        'STRUCT(url VARCHAR, outlet VARCHAR, lang VARCHAR, feed VARCHAR, title VARCHAR,
                published VARCHAR, authors VARCHAR[], summary VARCHAR)') }}
)

select
    key as item_key,
    version_date,
    payload.feed as feed,
    payload.outlet as outlet,
    payload.lang as lang,
    payload.url as url,
    nullif(trim(payload.title), '') as title,
    payload.authors as authors,
    try_cast(payload.published as timestamptz) as published_at,
    nullif(payload.summary, '') as feed_summary
from batches
