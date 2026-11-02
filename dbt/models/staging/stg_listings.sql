select
    listing_id,
    seller_id,
    category,
    region,
    price,
    created_at,
    toDate(created_at) as created_date
from {{ source('raw', 'listings') }}
order by _loaded_at desc
limit 1 by listing_id
