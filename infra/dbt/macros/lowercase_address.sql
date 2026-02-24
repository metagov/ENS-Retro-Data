{% macro lowercase_address(column_name) %}
    lower(trim({{ column_name }}))
{% endmacro %}
