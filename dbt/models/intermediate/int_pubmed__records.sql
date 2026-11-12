-- One row per PubMed record: its latest summary and latest MEDLINE indexing, with the
-- date it was first stored (entered_on). Raw batches keep every version; this is "now".
with summaries as (
    select
        *,
        min(version_date) over (partition by pmid) as entered_on,
        row_number() over (partition by pmid order by version_date desc) as rn
    from {{ ref('stg_pubmed__summary') }}
),

medline as (
    select *, row_number() over (partition by pmid order by version_date desc) as rn
    from {{ ref('stg_pubmed__medline') }}
)

select
    s.pmid,
    s.doi,
    s.pmcid,
    s.title,
    s.journal,
    s.journal_abbrev,
    s.issn,
    s.essn,
    s.published_on,
    s.entered_on,
    s.languages,
    s.authors,
    -- MEDLINE's list carries NLM's controlled names; esummary's is there from day one.
    coalesce(m.publication_types, s.publication_types) as publication_types,
    m.medline_status,
    coalesce(m.mesh_uis, []) as mesh_uis,
    m.keywords,
    m.has_abstract
from summaries as s
left join medline as m on m.pmid = s.pmid and m.rn = 1
where s.rn = 1
