# ENS DAO Governance Retrospective — Dashboard

A [Streamlit](https://streamlit.io) portal that presents quantitative findings from the ENS DAO Governance Retrospective. Charts are organized by governance challenge → hypothesis → visual, driven entirely by `config.yaml`.

## Prerequisites

- Python 3.12+
- The DuckDB warehouse file at `warehouse/ens_retro.duckdb` (one level above this folder). The dashboard opens it **read-only**; it must exist before launching.

## Setup

```bash
# From the repo root
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

pip install -r dashboards/requirements.txt
```

## Running the dashboard

```bash
# From the repo root
streamlit run dashboards/app.py
```

The app opens at `http://localhost:8501` by default. Streamlit theme and server settings are pre-configured in [dashboards/.streamlit/config.toml](.streamlit/config.toml).

## Project structure

```
dashboards/
├── app.py                  # Entry point — renders tabs, loads config
├── config.yaml             # Navigation: challenges → hypotheses → visuals
├── requirements.txt        # Python dependencies
├── .streamlit/
│   └── config.toml         # Theme (light, ENS blue) and server settings
└── scripts/
    ├── __init__.py
    ├── config.py           # Loads config.yaml into typed dataclasses
    ├── db.py               # Cached DuckDB connection (read-only)
    └── h*.py               # One file per visualization
```

The warehouse lives outside this folder:

```
warehouse/
└── ens_retro.duckdb        # Source of truth for all charts
```

## How navigation works

`config.yaml` is the single source of truth for the portal structure:

```
challenges
  └── hypotheses
        └── visuals
              ├── script   → dashboards/scripts/<script>.py
              └── fn       → function name to call
```

- **Challenges** become top-level tabs.
- **Hypotheses** become sub-tabs within each challenge.
- **Visuals** are rendered in order within the hypothesis view.
- If `visuals: []`, a "Work in progress" banner is shown automatically.

`app.py` never needs to change when adding new content — only `config.yaml` and a new script file are required.

## Adding a new visualization

1. Create `dashboards/scripts/<script_name>.py` with a public `render_*()` function that calls Streamlit rendering functions directly (no return value needed).

   ```python
   # dashboards/scripts/my_new_chart.py
   import streamlit as st
   from scripts.db import get_connection

   def render_my_chart() -> None:
       con = get_connection()
       df = con.execute("SELECT ... FROM main_gold.some_table").df()
       st.plotly_chart(...)
   ```

2. Register it in `config.yaml` under the relevant hypothesis:

   ```yaml
   visuals:
     - script: "my_new_chart"
       fn: "render_my_chart"
       title: "Chart display title"
       takeaway: "Optional key takeaway shown below the chart."
   ```

3. That's it. The portal picks it up automatically on next run (or hot-reload).

## Data access

All scripts query `warehouse/ens_retro.duckdb` through the shared connection helper:

```python
from scripts.db import get_connection

con = get_connection()  # cached; opens read-only
df = con.execute("SELECT ... FROM main_gold.<table>").df()
```

Use `@st.cache_data` on data-loading functions to avoid re-querying on every interaction.

## Updating data

The warehouse file (`warehouse/ens_retro.duckdb`) is tracked via Git LFS. To refresh the dashboard with new data:

```bash
# 1. Run the dbt pipeline to rebuild the warehouse
cd infra/dbt && dbt run

# 2. Commit the updated warehouse file (LFS handles the binary)
git add ../../warehouse/ens_retro.duckdb
git commit -m "Refresh warehouse — data as of $(date +%Y-%m-%d)"
git push origin main  # triggers Fly.io deploy automatically
```

> **Cold start note:** The first request after a Fly.io machine wakes from sleep may take 3–5 seconds while Streamlit initialises and DuckDB loads the warehouse file. Subsequent requests are served from the in-memory connection cache.

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | UI framework |
| `plotly` | Interactive charts |
| `duckdb` | Analytical queries against the warehouse |
| `pandas` | DataFrame manipulation |
| `numpy` | Numerical computations (Gini, Nakamoto, etc.) |
| `pyyaml` | Parsing `config.yaml` |
