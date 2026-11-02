{#
    Every monitored metric in long format: one row per (date, metric, slice).
    Slices are produced with ARRAY JOIN so that the total and all breakdowns come
    from a single scan of the fact table.
#}
{{ config(order_by='(metric, slice_type, slice_value, date)') }}

with event_slices as (
    select
        event_date as date,
        s.1 as slice_type,
        s.2 as slice_value,
        countIf(event_type = 'view') as views,
        countIf(event_type = 'contact') as contacts,
        uniqExact(user_id) as dau
    from {{ ref('fct_events') }}
    array join [
        ('total', 'Все'),
        ('platform', toString(platform)),
        ('category', toString(category)),
        ('region', toString(user_region))
    ] as s
    group by date, slice_type, slice_value
),

promo_slices as (
    select
        paid_date as date,
        s.1 as slice_type,
        s.2 as slice_value,
        sum(amount) as promo_revenue,
        count() as promo_purchases
    from {{ ref('fct_promotions') }}
    array join [
        ('total', 'Все'),
        ('category', toString(category)),
        ('region', toString(region))
    ] as s
    group by date, slice_type, slice_value
),

listing_slices as (
    select
        created_date as date,
        s.1 as slice_type,
        s.2 as slice_value,
        count() as new_listings
    from {{ ref('dim_listings') }}
    array join [
        ('total', 'Все'),
        ('category', toString(category)),
        ('region', toString(region))
    ] as s
    where created_date >= (select min(event_date) from {{ ref('fct_events') }})
    group by date, slice_type, slice_value
),

long as (
    select date, slice_type, slice_value, m.1 as metric, m.2 as value, m.3 as numerator, m.4 as denominator
    from event_slices
    array join [
        ('views', toFloat64(views), toFloat64(views), 1.),
        ('contacts', toFloat64(contacts), toFloat64(contacts), 1.),
        ('dau', toFloat64(dau), toFloat64(dau), 1.),
        ('view_to_contact_cr', contacts / views, toFloat64(contacts), toFloat64(views))
    ] as m

    union all

    select date, slice_type, slice_value, m.1, m.2, m.3, m.4
    from promo_slices
    array join [
        ('promo_revenue', promo_revenue, promo_revenue, 1.),
        ('promo_purchases', toFloat64(promo_purchases), toFloat64(promo_purchases), 1.)
    ] as m

    union all

    select date, slice_type, slice_value, 'new_listings', toFloat64(new_listings), toFloat64(new_listings), 1.
    from listing_slices
),

-- Densify: a slice that produced no rows on a given day must show up as 0,
-- otherwise a full outage of a segment would be invisible to the monitor.
series as (
    select distinct metric, slice_type, slice_value from long
),

dates as (
    select distinct date from long
)

select
    d.date as date,
    s.metric as metric,
    s.slice_type as slice_type,
    s.slice_value as slice_value,
    l.value as value,
    l.numerator as numerator,
    l.denominator as denominator
from dates as d
cross join series as s
left join long as l
    on l.date = d.date
    and l.metric = s.metric
    and l.slice_type = s.slice_type
    and l.slice_value = s.slice_value
