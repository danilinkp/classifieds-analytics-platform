{#
    Deviations that need attention. A drop of a volume metric to exactly zero while
    it was expected to be non-zero almost never happens in real user behaviour, so
    it is labelled as a probable data-delivery issue rather than a business change.
#}
{{ config(order_by='(date, metric, slice_type, slice_value)') }}

select
    date,
    metric,
    metric_title,
    slice_type,
    slice_value,
    value,
    expected,
    lower_bound,
    upper_bound,
    deviation_pct,
    z_score,
    status as severity,
    direction,
    if(value = 0 and expected > 0, 'data_quality', 'business') as alert_kind,
    concat(
        metric_title,
        if(slice_type = 'total', '', concat(' [', slice_type, ': ', slice_value, ']')),
        ': ', {{ format_metric('value', 'is_ratio') }},
        ' при ожидаемом ', {{ format_metric('expected', 'is_ratio') }},
        ' (', if(deviation_pct > 0, '+', ''), toString(round(deviation_pct * 100, 1)), '%)'
    ) as message
from {{ ref('metric_monitoring') }}
where status in ('warning', 'critical')
