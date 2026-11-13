-- Spanish title of each study the website shows (derived/titles/es.json, written by
-- `syn titles`; plan, step 23c). Only the titles that passed their checks: a failed one
-- stays in the file with its problems, so it is not asked again, but is never shown.
-- ``title_en`` is the English title it was translated from: dim_study joins on it, so a
-- study whose title changed shows the original until it is translated again.
select
    study_id,
    title_en,
    title_es,
    prompt_version as title_es_prompt_version,
    generator as title_es_generator
from {{ read_derived('titles/es.json', {
    'study_id': 'VARCHAR', 'status': 'VARCHAR', 'title_en': 'VARCHAR',
    'title_es': 'VARCHAR', 'prompt_version': 'VARCHAR', 'generator': 'VARCHAR'}) }}
where status = 'ok'
