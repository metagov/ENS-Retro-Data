{% macro map_vote_choice_snapshot(column_name) %}
    case try_cast({{ column_name }} as integer)
        when 1 then 'for'
        when 2 then 'against'
        when 3 then 'abstain'
        else 'unknown'
    end
{% endmacro %}

{% macro map_vote_choice_tally(column_name) %}
    case try_cast({{ column_name }} as integer)
        when 0 then 'against'
        when 1 then 'for'
        when 2 then 'abstain'
        else 'unknown'
    end
{% endmacro %}
