{{ config(order_by='listing_id') }}

select
    l.listing_id as listing_id,
    l.seller_id as seller_id,
    l.category as category,
    l.region as region,
    l.price as price,
    l.created_at as created_at,
    l.created_date as created_date,
    -- ClickHouse fills unmatched LEFT JOIN columns with type defaults, not NULL.
    if(c.listing_id = 0, null, c.closed_at) as closed_at,
    if(c.listing_id = 0, null, c.closed_date) as closed_date,
    if(c.listing_id = 0, 'active', c.close_reason) as status,
    c.listing_id = 0 as is_active,
    dateDiff('day', l.created_date, if(c.listing_id = 0, today(), c.closed_date)) as lifetime_days
from {{ ref('stg_listings') }} as l
left join {{ ref('stg_listing_closures') }} as c on c.listing_id = l.listing_id
