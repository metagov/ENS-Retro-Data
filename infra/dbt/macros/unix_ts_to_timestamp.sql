{% macro unix_ts_to_timestamp(column_name) %}
    to_timestamp(try_cast({{ column_name }} as bigint))
{% endmacro %}
