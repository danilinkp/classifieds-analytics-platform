select date, active_listings
from {{ ref('agg_daily_kpi') }}
where active_listings <= 0
