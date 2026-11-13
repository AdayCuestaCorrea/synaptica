-- A run must have been recorded in the last 2 days (copied from paleo-atlas): otherwise
-- the schedule stopped. A warning until pipeline.yml exists (plan, step 28); then an error.
{{ config(severity='warn') }}
select max(started_at) as last_run
from {{ ref('stg_pipeline__runs') }}
having max(started_at) is null
    or cast(max(started_at) as date) < {{ as_of_date() }} - 2
