{{ config(order_by='user_id') }}

with sellers as (
    select seller_id, count() as listings_created
    from {{ ref('stg_listings') }}
    group by seller_id
)

select
    u.user_id as user_id,
    u.registered_at as registered_at,
    u.registration_date as registration_date,
    u.region as region,
    u.platform as platform,
    s.listings_created as listings_created,
    s.listings_created > 0 as is_seller
from {{ ref('stg_users') }} as u
left join sellers as s on s.seller_id = u.user_id
