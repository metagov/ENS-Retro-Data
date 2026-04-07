{#
    Extracts the Discourse topic_id (the trailing integer) from a forum URL.

    ENS forum URLs follow the shape:
        https://discuss.ens.domains/t/<slug>/<topic_id>
        https://discuss.ens.domains/t/<slug>/<topic_id>/<post_number>
        https://discuss.ens.domains/t/<slug>/<topic_id>?u=username

    We prefer joining on topic_id (stable) over slug (mutable). Returns NULL
    if the input is null/empty or no topic_id can be parsed. Case-insensitive
    on the host. If multiple forum URLs appear in a single body of text, the
    first match wins (deterministic left-to-right).
#}
{% macro extract_discourse_topic_id(text_col) %}
    try_cast(
        regexp_extract(
            {{ text_col }},
            'https?://discuss\.ens\.domains/t/[^/\s)<"]+/(\d+)',
            1
        ) as bigint
    )
{% endmacro %}
