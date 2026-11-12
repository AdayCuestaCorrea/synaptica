-- Same-story group of each news item (derived/news/groups.json, written by
-- `syn news group`; plan, step 15). The group id is the smallest news_item_id in it.
select key as news_item_id, "group" as story_id
from {{ read_derived('news/groups.json', {'key': 'VARCHAR', 'group': 'VARCHAR'}) }}
