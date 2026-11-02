{#
    Root-cause hint for every alert on a total metric: how much each segment
    contributed to the deviation.
      additive metric: impact = segment value - segment expected value
      ratio metric:    impact = segment weight * (segment ratio - expected ratio),
                       i.e. the change of the total ratio explained by the segment
    impact_share is normalised within a slice type, so the shares of e.g. all
    platforms add up to 1. For DAU it is approximate: distinct users overlap
    between categories.
#}
{{ config(order_by='(date, metric, slice_type, impact_rank)') }}

with total_alerts as (
    select date, metric, status as severity, denominator as total_denominator
    from {{ ref('metric_monitoring') }}
    where slice_type = 'total' and status in ('warning', 'critical')
),

segments as (
    select
        m.date as date,
        m.metric as metric,
        m.metric_title as metric_title,
        t.severity as total_severity,
        m.slice_type as slice_type,
        m.slice_value as slice_value,
        m.value as value,
        m.expected as expected,
        m.deviation_pct as deviation_pct,
        m.status as segment_status,
        if(
            m.is_ratio,
            m.denominator / nullIf(t.total_denominator, 0) * (m.value - m.expected),
            m.value - m.expected
        ) as impact
    from {{ ref('metric_monitoring') }} as m
    inner join total_alerts as t on t.date = m.date and t.metric = m.metric
    where m.slice_type != 'total' and m.has_baseline
)

select
    *,
    impact / nullIf(sum(impact) over (partition by date, metric, slice_type), 0) as impact_share,
    row_number() over (partition by date, metric, slice_type order by abs(impact) desc) as impact_rank
from segments
