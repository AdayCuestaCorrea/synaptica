-- Neuroscience decision for each item of the general journals and feeds
-- (derived/news/neuro.json, written by `syn news neuro`; plan, step 13). Key:
-- "journals:<item_key>" or "news:<item_key>"; basis: openalex | llm.
select
    split_part(key, ':', 1) as item_source,
    substr(key, length(split_part(key, ':', 1)) + 2) as item_key,
    is_neuro,
    basis as neuro_basis,
    prompt_version,
    generator
from {{ read_derived('news/neuro.json', {
    'key': 'VARCHAR', 'is_neuro': 'BOOLEAN', 'basis': 'VARCHAR',
    'prompt_version': 'VARCHAR', 'generator': 'VARCHAR'}) }}
