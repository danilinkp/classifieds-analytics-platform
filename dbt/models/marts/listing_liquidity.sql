{#
    Liquidity = share of listings that received at least one contact within 7 days
    of publication. A cohort is complete only once all its listings are 7 days old.
#}
{{ config(order_by='(created_date, category, region)') }}

with first_contact as (
    select listing_id, min(event_ts) as first_contact_ts, 1 as has_contact
    from {{ ref('fct_events') }}
    where event_type = 'contact'
    group by listing_id
),

bounds as (
    select min(event_date) as first_day, max(event_date) as last_day
    from {{ ref('fct_events') }}
)

select
    l.created_date,
    l.category,
    l.region,
    count() as listings,
    countIf(fc.has_contact = 1 and fc.first_contact_ts <= l.created_at + interval 7 day) as contacted_7d,
    contacted_7d / listings as liquidity_7d,
    quantileIf(0.5)(
        dateDiff('minute', l.created_at, fc.first_contact_ts) / 60,
        fc.has_contact = 1
    ) as median_hours_to_first_contact,
    l.created_date <= (select last_day from bounds) - 7 as is_complete
from {{ ref('dim_listings') }} as l
left join first_contact as fc on fc.listing_id = l.listing_id
where l.created_date >= (select first_day from bounds)
group by l.created_date, l.category, l.region
