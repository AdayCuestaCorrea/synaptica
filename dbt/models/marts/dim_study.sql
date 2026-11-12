-- One row per study: PubMed records that are not editorial notices themselves, with the
-- three signals every study shows (CLAUDE.md, "Contenido de salud"; plan, step 12).
--   review_status: preprint | journal | unknown. "journal" means published in a journal
--     indexed by PubMed, not a proof of peer review; how the website words it is decided
--     with Sofía (step 21).
--   species: humans | animals | both | unknown, from the MeSH check tags Humans (D006801)
--     and Animals (D000818). Without MeSH (not indexed yet, or a journal outside MEDLINE)
--     it stays unknown: it is never guessed from the title.
--   integrity: retracted | partially_retracted | concern | corrected | none, from Crossref
--     notices and from PubMed's own "Retracted Publication" type.
with records as (
    select * from {{ ref('int_pubmed__records') }}
),

-- PubMed types of records that are notices about another article, not studies.
notices as (
    select pmid from records
    where list_has_any(publication_types, [
        'Published Erratum', 'Retraction of Publication', 'Expression of Concern',
        'Retraction Notice'
    ])
)

select
    r.pmid,
    r.doi,
    r.pmcid,
    r.title,
    r.journal,
    r.journal_abbrev,
    r.published_on,
    r.entered_on,
    r.languages,
    r.authors,
    r.publication_types,
    r.medline_status,
    case
        when list_contains(r.publication_types, 'Preprint') then 'preprint'
        when r.journal is not null then 'journal'
        else 'unknown'
    end as review_status,
    case
        when list_contains(r.mesh_uis, 'D006801') and list_contains(r.mesh_uis, 'D000818')
            then 'both'
        when list_contains(r.mesh_uis, 'D006801') then 'humans'
        when list_contains(r.mesh_uis, 'D000818') then 'animals'
        else 'unknown'
    end as species,
    case
        when i.integrity is not null then i.integrity
        when list_contains(r.publication_types, 'Retracted Publication') then 'retracted'
        else 'none'
    end as integrity,
    coalesce(i.notice_dois, []) as integrity_notices
from records as r
left join {{ ref('int_study__integrity') }} as i on i.doi = r.doi
where r.pmid not in (select pmid from notices)
