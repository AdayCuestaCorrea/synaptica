-- Editorial status of every DOI with a notice, studied by us or not (v148): Crossref's
-- notices and the Retraction Watch database, the most serious one winning, exactly as
-- int_study__integrity decides it for dim_study. It exists for the works that do not go
-- through dim_study, the Clásicos (OpenAlex listings, step 24): their proposal leaves out
-- the retracted ones and the site shows the signal of the ones she picked.
--   Only DOIs: a Retraction Watch row known by its PubMed ID alone ("pmid:<id>") cannot
--   be matched with a work identified by DOI.
select
    study_id as doi,
    integrity,
    notice_dois as integrity_notices,
    sources as integrity_sources,
    last_notice_on
from {{ ref('int_study__integrity') }}
where study_id not like 'pmid:%'
