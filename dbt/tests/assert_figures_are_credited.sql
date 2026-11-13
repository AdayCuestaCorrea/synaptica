-- Every figure the website can show carries a Creative Commons licence, its authors'
-- credit and the article it comes from (CLAUDE.md, "Licencias"; plan, step 23b), and
-- belongs to the same article as the study (its PMCID). `site --check` checks the page too.
select s.study_id
from {{ ref('dim_study') }} as s
where s.figure_file is not null
  and (s.figure_license is null or s.figure_license not like 'CC%'
       or coalesce(s.figure_credit, '') = '' or s.figure_source_url is null
       or s.figure_thumb is null or s.figure_width is null or s.figure_height is null
       or s.figure_pmcid is distinct from s.pmcid)
