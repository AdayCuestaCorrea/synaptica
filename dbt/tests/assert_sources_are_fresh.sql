-- Every source in the cadence seed must have a batch within its max_age_days of "as of"
-- (adapted from paleo-atlas assert_detection_is_fresh / stg_raw__checked): otherwise its
-- ingestion stopped and the website is silently going stale.
select c.source, c.kind, max(b.batch_date) as last_batch, c.max_age_days
from {{ ref('source_cadence') }} as c
left join {{ ref('stg_raw__batches') }} as b using (source, kind)
group by c.source, c.kind, c.max_age_days
having max(b.batch_date) is null
    or max(b.batch_date) < {{ as_of_date() }} - c.max_age_days
