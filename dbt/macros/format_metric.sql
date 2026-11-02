{% macro format_metric(column, is_ratio_column) -%}
    if({{ is_ratio_column }}, concat(toString(round({{ column }} * 100, 2)), '%'), toString(round({{ column }})))
{%- endmacro %}
