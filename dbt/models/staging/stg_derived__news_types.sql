-- Type of each Neuro News item (derived/news/types.json, written by `syn news classify`;
-- plan, step 14a). Key: "study:<study_id>" or the news_item_id of fct_news_item.
select
    key as item_id,
    type as news_type,
    prompt_version,
    generator
from {{ read_derived('news/types.json', {
    'key': 'VARCHAR', 'type': 'VARCHAR', 'prompt_version': 'VARCHAR',
    'generator': 'VARCHAR'}) }}
