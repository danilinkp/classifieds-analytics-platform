{#
    Additive measures at the finest dashboard grain. users is a distinct count:
    it is correct only at exactly this grain and must not be summed across rows.
#}
{{ config(order_by='(date, category, platform, user_region)') }}

select
    event_date as date,
    platform,
    category,
    user_region,
    countIf(event_type = 'view') as views,
    countIf(event_type = 'contact') as contacts,
    countIf(event_type = 'favorite') as favorites,
    uniqExact(user_id) as users
from {{ ref('fct_events') }}
group by date, platform, category, user_region
