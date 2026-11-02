{#
    Materialised as a table rather than a view: deduplication with LIMIT BY blocks
    predicate push-down, so a view would re-scan the whole clickstream on every query.
    Duplicates of an event always arrive within the same daily batch, which lets us
    rebuild only the recent partitions.
#}
{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite',
        partition_by='event_date',
        order_by='(event_date, event_type, user_id)',
    )
}}

select
    event_id,
    event_ts,
    toDate(event_ts) as event_date,
    event_type,
    user_id,
    listing_id,
    platform
from {{ source('raw', 'events') }}
{% if is_incremental() %}
where load_date >= (select max(event_date) from {{ this }}) - {{ var('incremental_lookback_days') }}
{% endif %}
limit 1 by event_id
