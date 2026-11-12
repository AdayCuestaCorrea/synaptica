-- Every source's view of a study, one row per source record, with the study key and the
-- signals that source can give (plan, steps 11–12). dim_study merges them by study_id.
--   study_id: the DOI (lower case); without one, "pmid:", "epmc:" or "journal:" + key.
--   priority: whose metadata wins (PubMed 1, preprint server 2, Europe PMC 3, feed 4).
--   neuro_basis: why the record counts as neuroscience — source_query (it came in
--   through a neuroscience query or category), journal_scope (a neuro journal), openalex
--   or llm (step 13 decision for the general journals) — or null if not (yet).
--   review_status / species: what this source says, or 'unknown'. Species comes only from
--   MeSH (PubMed's UIs, or Europe PMC's descriptor names): never guessed from the title.
with pubmed as (
    select * from {{ ref('int_pubmed__records') }}
    where not list_has_any(publication_types, [
        'Published Erratum', 'Retraction of Publication', 'Expression of Concern',
        'Retraction Notice'
    ])
),

epmc as (
    select * from {{ ref('int_europepmc__records') }}
    where not list_has_any(publication_types, [
        'Published Erratum', 'Retraction of Publication', 'Expression of Concern',
        'Retraction Notice', 'erratum', 'retraction'
    ])
)

select
    coalesce(doi, 'pmid:' || pmid) as study_id,
    'pubmed' as source,
    1 as priority,
    doi, pmid, pmcid, title, journal, published_on, entered_on, authors,
    case
        when list_contains(publication_types, 'Preprint') then 'preprint'
        when journal is not null then 'journal'
        else 'unknown'
    end as review_status,
    case
        when list_contains(mesh_uis, 'D006801') and list_contains(mesh_uis, 'D000818')
            then 'both'
        when list_contains(mesh_uis, 'D006801') then 'humans'
        when list_contains(mesh_uis, 'D000818') then 'animals'
        else 'unknown'
    end as species,
    list_contains(publication_types, 'Retracted Publication') as flagged_retracted,
    cast(null as boolean) as is_open_access,
    cast(null as varchar) as license,
    'source_query' as neuro_basis
from pubmed

union all

select
    doi,
    server,
    2,
    doi, null, null, title, server, version_posted_on, entered_on, authors,
    'preprint',
    'unknown',
    false,
    license not in ('cc_no'),
    license,
    'source_query'
from {{ ref('int_preprints__latest') }}

union all

select
    coalesce(doi, 'epmc:' || epmc_key),
    'europepmc',
    3,
    doi, pmid, pmcid, title, journal, published_on, entered_on, authors,
    case when epmc_source = 'PPR' then 'preprint' when journal is not null then 'journal'
         else 'unknown' end,
    case
        when list_contains(mesh_names, 'Humans') and list_contains(mesh_names, 'Animals')
            then 'both'
        when list_contains(mesh_names, 'Humans') then 'humans'
        when list_contains(mesh_names, 'Animals') then 'animals'
        else 'unknown'
    end,
    list_contains(publication_types, 'Retracted Publication'),
    is_open_access,
    license,
    'source_query'
from epmc

union all

select
    coalesce(j.doi, 'journal:' || j.item_key),
    'journals',
    4,
    j.doi, null, null, j.title, j.journal_name, cast(j.published_at as date), j.entered_on,
    j.authors,
    'journal',
    'unknown',
    false,
    null,
    null,
    case when j.journal_scope = 'neuro' then 'journal_scope'
         when d.is_neuro then d.neuro_basis end
from {{ ref('int_journals__items') }} as j
left join {{ ref('stg_derived__neuro') }} as d
    on d.item_source = 'journals' and d.item_key = j.item_key
where j.kind in ('research', 'review')
