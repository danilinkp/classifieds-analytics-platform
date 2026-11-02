{% test unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count() as rows
from {{ model }}
group by {{ columns | join(', ') }}
having rows > 1
{% endtest %}
