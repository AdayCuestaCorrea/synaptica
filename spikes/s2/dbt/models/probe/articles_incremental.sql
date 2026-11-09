{{ config(materialized='incremental', unique_key='pmid') }}
-- Probe: the second run of an incremental model issues a MERGE (DML).
select pmid, title, pub_date from {{ ref('stg_pubmed__articles') }}
{% if is_incremental() %}
where pub_date >= (select max(pub_date) from {{ this }})
{% endif %}
