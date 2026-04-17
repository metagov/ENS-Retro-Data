{% macro map_vote_choice_snapshot(column_name) %}
    case try_cast({{ column_name }} as integer)
        when 1 then 'for'
        when 2 then 'against'
        when 3 then 'abstain'
        else 'unknown'
    end
{% endmacro %}

{% macro map_vote_choice_tally(column_name) %}
    -- Tally API returns support as lowercase strings ('for'/'against'/'abstain').
    -- Older exports used integer codes (0=against, 1=for, 2=abstain); kept as a fallback.
    case
        when lower(cast({{ column_name }} as varchar)) in ('for', 'against', 'abstain')
            then lower(cast({{ column_name }} as varchar))
        when try_cast({{ column_name }} as integer) = 0 then 'against'
        when try_cast({{ column_name }} as integer) = 1 then 'for'
        when try_cast({{ column_name }} as integer) = 2 then 'abstain'
        else 'unknown'
    end
{% endmacro %}
