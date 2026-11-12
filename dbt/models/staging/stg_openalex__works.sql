-- OpenAlex topic and citations of each DOI looked up (raw/openalex/works/<date>.jsonl,
-- written by synaptica.ingest.openalex), one row per DOI and version.
with batches as (
    select * from {{ read_batches('openalex', 'works',
        'STRUCT(doi VARCHAR, openalex_id VARCHAR, type VARCHAR, publication_year INTEGER,
                cited_by_count INTEGER, is_retracted BOOLEAN,
                primary_topic STRUCT(id VARCHAR, name VARCHAR, score DOUBLE,
                    subfield VARCHAR, field VARCHAR, field_name VARCHAR),
                topics STRUCT(id VARCHAR, name VARCHAR, score DOUBLE, subfield VARCHAR,
                    field VARCHAR, field_name VARCHAR)[])') }}
)

select
    key as doi,
    version_date,
    payload.openalex_id as openalex_id,
    payload.type as work_type,
    payload.cited_by_count as cited_by_count,
    payload.is_retracted as is_retracted,
    payload.primary_topic.field as primary_field,
    payload.primary_topic.field_name as primary_field_name,
    payload.primary_topic.subfield as primary_subfield,
    [t.field for t in payload.topics] as topic_fields
from batches
