-- A Nature, Science or Cell paper is classified as an item of the journal feeds
-- (`journal:<doi>`, step 14a); dim_study must carry that type, or the paper shows on the
-- site with no type although it has one. Found on the first real run of step 14a.
select s.study_id
from {{ ref('dim_study') }} as s
join {{ ref('stg_derived__news_types') }} as t on t.item_id = 'journal:' || s.doi
where s.news_type is null
