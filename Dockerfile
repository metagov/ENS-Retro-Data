FROM python:3.12-slim

WORKDIR /app

# Install only dashboard dependencies (not Dagster/dbt)
COPY dashboards/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy dashboard code — lands at /app/dashboards/
COPY dashboards/ ./dashboards/

# Download the DuckDB warehouse from DigitalOcean Spaces (replaces Git LFS).
# This avoids burning GitHub LFS bandwidth on every Render deploy.
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    mkdir -p warehouse && \
    curl -fsSL https://ensretro-data.fra1.digitaloceanspaces.com/warehouse/ens_retro.duckdb \
         -o warehouse/ens_retro.duckdb && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

EXPOSE 8501
CMD ["streamlit", "run", "dashboards/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]
