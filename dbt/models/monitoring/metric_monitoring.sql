{#
    Two-step anomaly scoring.

    1. Expected value: median of the same weekday over the previous N weeks.
       Same-weekday comparison removes weekly seasonality; the median keeps a single
       past anomaly from shifting the baseline.
    2. Typical error: robust spread (1.4826 * MAD) of the relative residuals
       value / expected - 1 over the previous 8 weeks of all days. Estimating it from
       ~56 residuals instead of the 6 baseline points gives a stable corridor, and it
       automatically widens for small noisy segments and absorbs the lag of the
       median behind the growth trend. MAD instead of stddev, again, so that past
       incidents do not inflate the corridor.
#}
{{ config(order_by='(metric, slice_type, slice_value, date)') }}

{% set residual_window = 56 %}

with baseline as (
    select
        date,
        metric,
        slice_type,
        slice_value,
        value,
        numerator,
        denominator,
        quantileExact(0.5)(value) over weekday_window as expected_raw,
        count() over weekday_window as weekday_points
    from {{ ref('metric_daily') }}
    window weekday_window as (
        partition by metric, slice_type, slice_value, toDayOfWeek(date)
        order by date
        rows between {{ var('monitoring_weeks') }} preceding and 1 preceding
    )
),

residuals as (
    select
        *,
        if(weekday_points >= 4 and expected_raw > 0, value / expected_raw - 1, null) as residual
    from baseline
),

scored as (
    select
        *,
        1.4826 * quantileExact(0.5)(abs(residual)) over residual_window as residual_sigma_raw,
        count(residual) over residual_window as residual_points
    from residuals
    window residual_window as (
        partition by metric, slice_type, slice_value
        order by date
        rows between {{ residual_window }} preceding and 1 preceding
    )
)

select
    s.date as date,
    s.metric as metric,
    c.title as metric_title,
    c.unit as unit,
    c.is_ratio = 1 as is_ratio,
    s.slice_type as slice_type,
    s.slice_value as slice_value,
    s.value as value,
    s.numerator as numerator,
    s.denominator as denominator,
    s.residual is not null and s.residual_points >= 14 as has_baseline,
    if(has_baseline, s.expected_raw, null) as expected,
    if(has_baseline, greatest(s.residual_sigma_raw, 0.01), null) as sigma_pct,
    if(has_baseline, s.expected_raw * (1 - 3 * sigma_pct), null) as lower_bound,
    if(has_baseline, s.expected_raw * (1 + 3 * sigma_pct), null) as upper_bound,
    if(has_baseline, s.residual, null) as deviation_pct,
    if(has_baseline, s.residual / sigma_pct, null) as z_score,
    multiIf(
        not has_baseline, 'no_baseline',
        abs(z_score) >= 5 and abs(deviation_pct) >= 0.15, 'critical',
        abs(z_score) >= 3.5 and abs(deviation_pct) >= 0.05, 'warning',
        'ok'
    ) as status,
    multiIf(status in ('ok', 'no_baseline'), '', s.value > s.expected_raw, 'up', 'down') as direction
from scored as s
left join {{ ref('metric_catalog') }} as c on c.metric = s.metric
