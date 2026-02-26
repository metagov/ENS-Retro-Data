"""Silver layer — handled entirely by dbt models in dbt/models/silver/.

Python silver assets have been removed to avoid duplicate Dagster asset keys.
All cleaning, typing, and deduplication is done in dbt SQL models.
"""
