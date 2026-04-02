{% macro token_to_value(column_name, token_column) %}
    case
        when upper({{ token_column }}) in ('USDC', 'USDT')
            then try_cast({{ column_name }} as double) / 1e6
        else
            try_cast({{ column_name }} as double) / 1e18
    end
{% endmacro %}
