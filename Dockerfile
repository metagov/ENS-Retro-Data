FROM python:3.12-slim

WORKDIR /app

# Install only dashboard dependencies (not Dagster/dbt)
COPY dashboards/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy dashboard code — lands at /app/dashboards/
COPY dashboards/ ./dashboards/

# Copy the database — lands at /app/warehouse/ens_retro.duckdb
# This matches what db.py expects: 3 parents up from db.py = /app/
COPY warehouse/ens_retro.duckdb ./warehouse/ens_retro.duckdb

EXPOSE 8501
CMD ["streamlit", "run", "dashboards/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]