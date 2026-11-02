{{ config(order_by='date') }}

with events as (
    select
        event_date as date,
        uniqExact(user_id) as dau,
        uniqExactIf(user_id, event_type = 'contact') as contacting_users,
        countIf(event_type = 'view') as views,
        countIf(event_type = 'contact') as contacts,
        countIf(event_type = 'favorite') as favorites
    from {{ ref('fct_events') }}
    group by date
),

new_users as (
    select registration_date as date, count() as new_users
    from {{ ref('dim_users') }}
    group by date
),

listing_flow as (
    select date, sum(created) as created, sum(closed) as closed, sum(sold) as sold
    from (
        select created_date as date, 1 as created, 0 as closed, 0 as sold
        from {{ ref('dim_listings') }}
        union all
        select closed_date as date, 0, 1, status = 'sold'
        from {{ ref('dim_listings') }}
        where not is_active
    )
    group by date
),

-- Live stock at the end of the day = everything ever created minus everything closed.
listing_stock as (
    select
        date,
        created as new_listings,
        closed as closed_listings,
        sold as sold_listings,
        sum(created - closed) over (order by date rows between unbounded preceding and current row) as active_listings
    from listing_flow
),

promotions as (
    select
        paid_date as date,
        sum(amount) as promo_revenue,
        count() as promo_purchases,
        uniqExact(seller_id) as paying_sellers
    from {{ ref('fct_promotions') }}
    group by date
)

select
    e.date as date,
    e.dau,
    e.contacting_users,
    e.views,
    e.contacts,
    e.favorites,
    e.contacts / nullIf(e.views, 0) as view_to_contact_cr,
    e.views / nullIf(e.dau, 0) as views_per_user,
    nu.new_users,
    ls.new_listings,
    ls.closed_listings,
    ls.sold_listings,
    ls.active_listings,
    p.promo_revenue,
    p.promo_purchases,
    p.paying_sellers,
    p.promo_revenue / nullIf(p.paying_sellers, 0) as arppu
from events as e
left join new_users as nu on nu.date = e.date
left join listing_stock as ls on ls.date = e.date
left join promotions as p on p.date = e.date
