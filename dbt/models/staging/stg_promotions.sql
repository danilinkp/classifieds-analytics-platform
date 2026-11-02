select
    payment_id,
    listing_id,
    seller_id,
    service,
    toFloat64(amount) as amount,
    paid_at,
    toDate(paid_at) as paid_date
from {{ source('raw', 'promotions') }}
order by _loaded_at desc
limit 1 by payment_id
