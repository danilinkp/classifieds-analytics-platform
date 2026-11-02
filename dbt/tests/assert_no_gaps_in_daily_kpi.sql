-- A missing day in the KPI mart means a failed or skipped load upstream.
select date, prev_date
from (
    select date, lagInFrame(date) over (order by date rows between 1 preceding and current row) as prev_date
    from {{ ref('agg_daily_kpi') }}
)
where prev_date != toDate(0) and dateDiff('day', prev_date, date) > 1
