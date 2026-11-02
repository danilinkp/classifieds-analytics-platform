select
    listing_id,
    closed_at,
    toDate(closed_at) as closed_date,
    reason as close_reason
from {{ source('raw', 'listing_closures') }}
order by _loaded_at desc
limit 1 by listing_id
