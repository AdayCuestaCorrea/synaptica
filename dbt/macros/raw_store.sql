{#
  Readers for the files under $SYN_DATA_DIR. Adapted from paleo-atlas
  dbt/macros/raw_store.sql (decision D2): SYNAPTICA's high-volume sources use daily
  batches (synaptica.store.BatchStore) instead of one folder per entity.
#}

{% macro data_dir() -%}
    {{ env_var("SYN_DATA_DIR", "../data") }}
{%- endmacro %}

{#
  Every line of the daily batches of one source/kind:
  $SYN_DATA_DIR/raw/<source>/<kind>/<YYYY-MM-DD>.jsonl, {"key": ..., "payload": ...}.
  version_date is the date in the file name (the day the line was new or changed).
  `payload_type` is a DuckDB STRUCT so staging gets typed columns; an empty relation with
  the same columns when the source has no batches yet.
#}
{% macro read_batches(source, kind, payload_type) -%}
    {%- set path = data_dir() ~ "/raw/" ~ source ~ "/" ~ kind ~ "/*.jsonl" -%}
    {%- set found = 0 -%}
    {%- if execute -%}
        {%- set found = run_query("select count(*) from glob('" ~ path ~ "')").columns[0].values()[0] -%}
    {%- endif -%}
    {%- if found > 0 -%}
    (
        select
            key,
            cast(regexp_extract(filename, '(\d{4}-\d{2}-\d{2})\.jsonl$', 1) as date) as version_date,
            payload
        from read_json(
            '{{ path }}',
            format = 'newline_delimited',
            filename = true,
            columns = {key: 'VARCHAR', payload: '{{ payload_type }}'}
        )
    )
    {%- else -%}
    (select cast(null as varchar) as key, cast(null as date) as version_date,
            cast(null as {{ payload_type }}) as payload limit 0)
    {%- endif -%}
{%- endmacro %}

{#
  Daily batch files present, per source/kind and date (for the freshness tests).
#}
{% macro read_batch_files() -%}
    (
        select
            split_part(rel, '/', 1) as source,
            split_part(rel, '/', 2) as kind,
            cast(regexp_extract(rel, '(\d{4}-\d{2}-\d{2})\.jsonl$', 1) as date) as batch_date
        from (
            select substr(file, length('{{ data_dir() }}/raw/') + 1) as rel
            from glob('{{ data_dir() }}/raw/*/*/*.jsonl')
        )
    )
{%- endmacro %}

{#
  Pipeline run log written by synaptica.report: $SYN_DATA_DIR/runs/<YYYY-MM-DD>.json, a
  JSON array with one item per run; an empty relation before the first run.
#}
{% macro read_runs() -%}
    {%- set path = data_dir() ~ "/runs/*.json" -%}
    {%- set found = 0 -%}
    {%- if execute -%}
        {%- set found = run_query("select count(*) from glob('" ~ path ~ "')").columns[0].values()[0] -%}
    {%- endif -%}
    {%- if found > 0 -%}
    read_json(
        '{{ path }}',
        format = 'array',
        columns = {
            started_at: 'TIMESTAMPTZ', finished_at: 'TIMESTAMPTZ', trigger: 'VARCHAR',
            changed: 'BOOLEAN', status: 'VARCHAR', steps: 'JSON', summary: 'JSON', dbt: 'JSON',
            sources_changed: 'JSON', changes_since_previous: 'JSON'
        }
    )
    {%- else -%}
    (select cast(null as timestamptz) as started_at, cast(null as timestamptz) as finished_at,
            cast(null as varchar) as trigger, cast(null as boolean) as changed,
            cast(null as varchar) as status limit 0)
    {%- endif -%}
{%- endmacro %}

{# "as of" for date-based tests: pinned with --vars in CI on fixtures, today in UTC otherwise. #}
{% macro as_of_date() -%}
    {%- set as_of = var('as_of', none) -%}
    {{ "date '" ~ as_of ~ "'" if as_of else "cast(timezone('UTC', now()) as date)" }}
{%- endmacro %}
