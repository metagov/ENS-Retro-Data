"""Gold layer — handled entirely by dbt models in dbt/models/gold/.

Python gold assets have been removed to avoid duplicate Dagster asset keys.
All analysis-ready views and composite indexes are built in dbt SQL models.
"""
