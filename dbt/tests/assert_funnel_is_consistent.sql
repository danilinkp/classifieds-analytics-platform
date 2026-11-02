select date, views, contacts, dau, contacting_users
from {{ ref('agg_daily_kpi') }}
where contacts > views
   or contacting_users > dau
   or view_to_contact_cr not between 0 and 1
