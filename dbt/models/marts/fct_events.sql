{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite',
        partition_by='event_date',
        order_by='(event_date, event_type, category, platform)',
    )
}}

select
    e.event_id as event_id,
    e.event_ts as event_ts,
    e.event_date as event_date,
    e.event_type as event_type,
    e.user_id as user_id,
    e.platform as platform,
    u.region as user_region,
    u.registration_date = e.event_date as is_new_user,
    e.listing_id as listing_id,
    l.category as category,
    l.region as listing_region,
    l.price as listing_price
from {{ ref('stg_events') }} as e
any left join {{ ref('dim_users') }} as u on u.user_id = e.user_id
any left join {{ ref('dim_listings') }} as l on l.listing_id = e.listing_id
{% if is_incremental() %}
where e.event_date >= (select max(event_date) from {{ this }}) - {{ var('incremental_lookback_days') }}
{% endif %}
