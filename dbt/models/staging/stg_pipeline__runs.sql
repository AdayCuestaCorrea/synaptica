-- Pipeline runs recorded by `syn report` (data/runs/<date>.json), one row per run.
select started_at, finished_at, trigger, changed, status
from {{ read_runs() }}
