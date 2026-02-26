{% macro wei_to_ether(column_name) %}
    try_cast({{ column_name }} as double) / 1e18
{% endmacro %}
