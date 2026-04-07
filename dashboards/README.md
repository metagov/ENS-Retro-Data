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

## Project structure I don't have an OpenAI key. Is this possible via Claude Code tool somehow, or do I not pay for an OpenAI key? Can I still get one?

Another one is the agent builder workflow. No, I do want to include the agent builder workflow. In the dashboard, I don't want a dedicated page; I just want a small widget on the page in the bottom right corner, a floating widget on every page. Whenever they see something, whenever they see a chat, they should be able to ask a question. I also want the chat widget to send which component they're looking at, or which page they're on, or which tab they're on when they ask that question, so that they have more context on this.

Another one is querying DuckDB and DuckDB Warehouse. DuckDB Warehouse is really, really good, but we also have bronze data, I suppose, since all the dashboard and all the charts are built with clean data, which is silver and gold models, which I assume are inductively, so it would be easier to just access DuckDB. Would there be any need to access the raw data itself? 

```
dashboards/
├── app.py                  # Entry point — renders tabs, loads config
├── api.py                  # FastAPI + MCP server for ChatKit agent tool calls
├── config.yaml             # Navigation: challenges → hypotheses → visuals
├── requirements.txt        # Python dependencies
├── .streamlit/
│   └── config.toml         # Theme (light, ENS blue) and server settings
├── pages/
│   └── Chat.py             # Full-viewport dedicated chat page
├── scripts/
│   ├── __init__.py
│   ├── config.py           # Loads config.yaml into typed dataclasses
│   ├── db.py               # Cached DuckDB connection (read-only)
│   ├── chat_session.py     # ChatKit session token minting
│   ├── chat_widget.py      # Floating chat widget embedding
│   └── h*.py               # One file per visualization
├── static/
│   ├── chat.html           # Floating bubble + panel chat widget
│   └── chatpage.html       # Full-page ChatKit embed
└── tests/
    ├── test_api.py          # API server + chat widget tests
    ├── test_computations.py # Dashboard computation tests
    ├── test_config.py       # Config loading tests
    └── test_warehouse.py    # Warehouse data quality tests
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
git push origin main  # triggers Render auto-deploy
```

> **Cold start note:** The first request after a Render service spins up may take a few seconds while Streamlit initialises and DuckDB loads the warehouse file. Subsequent requests are served from the in-memory connection cache.

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | UI framework |
| `plotly` | Interactive charts |
| `duckdb` | Analytical queries against the warehouse |
| `pandas` | DataFrame manipulation |
| `numpy` | Numerical computations (Gini, Nakamoto, etc.) |
| `pyyaml` | Parsing `config.yaml` |
