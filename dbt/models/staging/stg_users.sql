select
    user_id,
    registered_at,
    toDate(registered_at) as registration_date,
    region,
    platform
from {{ source('raw', 'users') }}
order by _loaded_at desc
limit 1 by user_id
