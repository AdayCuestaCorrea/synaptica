-- Figure 1 of each study shown in «Latest» (derived/figures/figures.json, written by
-- `syn figures`; plan, step 23b). Only the rows with a figure: the others keep the reason
-- in the file, so they are not asked again, but the website has nothing to show. The WebP
-- files live in the private cache (D10); the site shows a figure only if they are there.
select
    study_id,
    pmcid as figure_pmcid,
    label as figure_label,
    file as figure_file,
    thumb as figure_thumb,
    width as figure_width,
    height as figure_height,
    license as figure_license,
    license_url as figure_license_url,
    credit as figure_credit,
    citation as figure_citation,
    source_url as figure_source_url
from {{ read_derived('figures/figures.json', {
    'study_id': 'VARCHAR', 'pmcid': 'VARCHAR', 'status': 'VARCHAR', 'label': 'VARCHAR',
    'file': 'VARCHAR', 'thumb': 'VARCHAR', 'width': 'INTEGER', 'height': 'INTEGER',
    'license': 'VARCHAR', 'license_url': 'VARCHAR', 'credit': 'VARCHAR',
    'citation': 'VARCHAR', 'source_url': 'VARCHAR'}) }}
where status = 'ok'
