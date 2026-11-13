-- One row per study, merged from every source by study_id (the DOI when there is one),
-- with the three signals every study shows (CLAUDE.md, "Contenido de salud"; plan,
-- steps 11 and 12).
--   Metadata: from the source with the best priority (PubMed, preprint server, Europe
--     PMC, journal feed); entered_on is the first day any source stored it.
--   review_status: preprint | journal | unknown, from the best source that knows it.
--     "journal" means published in a journal, not a proof of peer review; how the website
--     words it is decided with Sofía (step 21).
--   species: humans | animals | both | unknown, from MeSH only (PubMed, or Europe PMC's
--     descriptor names); never guessed from the title.
--   integrity: retracted | partially_retracted | concern | corrected | none, from Crossref;
--     withdrawn: a bioRxiv / medRxiv preprint whose authors withdrew it (its latest version
--     is of type "withdrawn"; servers deposit no Crossref notice for it). A retraction
--     outranks it; it outranks a concern or a correction.
--     notices and from the "Retracted Publication" type of PubMed or Europe PMC.
--   is_neuro / neuro_basis: every source but the general journals is neuroscience by its
--     query or category; a general journal's paper needs the step 13 decision (OpenAlex
--     or LLM). Not neuro, or not decided yet, is false: the website shows only true.
--   news_candidate: passes the cheap prefilter for Neuro News and its classification
--     (Aday, 2026-11-12; the spike S5 prefilter): neuroscience, not retracted, in English,
--     with an abstract when the source says, and not a review, case report, letter,
--     comment, editorial or news piece, and published at most 30 days before it entered
--     (Europe PMC indexes papers months old). Preprints pass (they have an abstract).
--   Preprint and journal version are two studies, linked both ways (Aday, 2026-11-12):
--     published_doi on the preprint, preprint_doi on the journal version.
with candidates as (
    select * from {{ ref('int_study__candidates') }}
),

merged as (
    select
        study_id,
        arg_min(doi, priority) as doi,
        arg_min(pmid, priority) filter (where pmid is not null) as pmid,
        arg_min(pmcid, priority) filter (where pmcid is not null) as pmcid,
        arg_min(title, priority) filter (where title is not null) as title,
        arg_min(journal, priority) filter (where journal is not null) as journal,
        arg_min(published_on, priority) filter (where published_on is not null)
            as published_on,
        min(entered_on) as entered_on,
        arg_min(authors, priority) filter (where authors is not null) as authors,
        list(distinct source order by source) as sources,
        coalesce(arg_min(review_status, priority) filter (where review_status != 'unknown'),
                 'unknown') as review_status,
        coalesce(arg_min(species, priority) filter (where species != 'unknown'), 'unknown')
            as species,
        bool_or(flagged_retracted) as flagged_retracted,
        bool_or(is_open_access) as is_open_access,
        arg_min(license, priority) filter (where license is not null) as license,
        arg_min(neuro_basis, priority) filter (where neuro_basis is not null) as neuro_basis,
        arg_min(publication_types, priority) filter (where publication_types is not null)
            as publication_types,
        arg_min(is_english, priority) filter (where is_english is not null) as is_english,
        arg_min(has_abstract, priority) filter (where has_abstract is not null)
            as has_abstract
    from candidates
    group by study_id
),

-- The "pubs" list names the preprint even when it was posted before our window.
preprint_of as (
    select published_doi, min(preprint_doi) as preprint_doi
    from (
        select doi as preprint_doi, published_doi from {{ ref('int_preprints__latest') }}
        union all
        select preprint_doi, published_doi from {{ ref('stg_preprints__published') }}
    )
    where published_doi is not null
    group by published_doi
)

select
    m.study_id,
    m.doi,
    m.pmid,
    m.pmcid,
    m.title,
    m.journal,
    m.published_on,
    m.entered_on,
    m.authors,
    m.sources,
    m.review_status,
    m.species,
    case
        when i.integrity in ('retracted', 'partially_retracted') then i.integrity
        when m.flagged_retracted then 'retracted'
        when w.doi is not null then 'withdrawn'
        when i.integrity is not null then i.integrity
        else 'none'
    end as integrity,
    coalesce(i.notice_dois, []) as integrity_notices,
    coalesce(m.is_open_access, false) as is_open_access,
    m.license,
    m.neuro_basis is not null as is_neuro,
    m.neuro_basis,
    m.publication_types,
    m.neuro_basis is not null
        and coalesce(i.integrity, 'none') not in ('retracted', 'partially_retracted')
        and not coalesce(m.flagged_retracted, false)
        and w.doi is null
        and coalesce(m.is_english, true)
        and coalesce(m.has_abstract, true)
        and (m.published_on is null or m.published_on >= m.entered_on - 30)
        and not list_has_any(coalesce(m.publication_types, []), [
            'Review', 'Systematic Review', 'Meta-Analysis', 'Case Reports', 'Letter',
            'Comment', 'Editorial', 'News', 'Erratum', 'Published Erratum',
            'review', 'review-article', 'case-report', 'letter', 'editorial', 'news'
        ]) as news_candidate,
    -- A Nature, Science or Cell paper is classified as an item of the journal feeds
    -- (``journal:<doi>``, step 14a), the rest as ``study:<id>``.
    coalesce(t.news_type, tj.news_type) as news_type,
    p.published_doi,
    po.preprint_doi,
    o.primary_field as openalex_field
from merged as m
left join {{ ref('int_study__integrity') }} as i on i.doi = m.doi
left join {{ ref('stg_derived__news_types') }} as t on t.item_id = 'study:' || m.study_id
left join {{ ref('stg_derived__news_types') }} as tj on tj.item_id = 'journal:' || m.doi
left join {{ ref('int_preprints__latest') }} as p on p.doi = m.doi and p.published_doi is not null
left join preprint_of as po on po.published_doi = m.doi
left join {{ ref('int_preprints__latest') }} as w
    on w.doi = m.doi and w.preprint_type = 'withdrawn' 
left join (
    select doi, arg_max(primary_field, version_date) as primary_field
    from {{ ref('stg_openalex__works') }} group by doi
) as o on o.doi = m.doi
