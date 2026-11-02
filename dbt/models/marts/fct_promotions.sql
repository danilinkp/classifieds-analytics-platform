{{ config(order_by='(paid_date, service)') }}

select
    p.payment_id as payment_id,
    p.paid_at as paid_at,
    p.paid_date as paid_date,
    p.listing_id as listing_id,
    p.seller_id as seller_id,
    p.service as service,
    p.amount as amount,
    l.category as category,
    l.region as region
from {{ ref('stg_promotions') }} as p
any left join {{ ref('dim_listings') }} as l on l.listing_id = p.listing_id
