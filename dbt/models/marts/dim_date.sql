{{ config(order_by='date') }}

with dates as (
    select toDate('2025-01-01') + number as date
    from numbers(toUInt64(dateDiff('day', toDate('2025-01-01'), today()) + 31))
)

select
    date,
    toMonday(date) as week_start,
    toStartOfMonth(date) as month_start,
    toDayOfWeek(date) as weekday_num,
    ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][toDayOfWeek(date)] as weekday_name,
    toDayOfWeek(date) >= 6 as is_weekend
from dates
