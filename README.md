# ENS DAO Governance Research

> An open research platform analyzing governance, voting power, treasury, and participation patterns in the Ethereum Name Service DAO. Built on a reproducible medallion data pipeline (Dagster + dbt + DuckDB), with a Streamlit dashboard, AI research assistant, and MCP-compatible query API.

[![Code: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE-CODE) [![Data: CC BY 4.0](https://img.shields.io/badge/Data-CC%20BY%204.0-lightgrey.svg)](LICENSE-DATA)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Dagster](https://img.shields.io/badge/orchestration-Dagster-5E2EE6.svg)](https://dagster.io/)
[![dbt](https://img.shields.io/badge/transform-dbt-FF694A.svg)](https://www.getdbt.com/)
[![DuckDB](https://img.shields.io/badge/warehouse-DuckDB-FFF000.svg)](https://duckdb.org/)

---

## What's in this repo?

This is the data infrastructure and public research frontend for the **ENS DAO Retrospective Evaluation** — a metagov-led study of how ENS governance has evolved since the token launch. Everything is open for public inspection, replication, and extension:

- **Live dashboard** — explore the five governance research challenges interactively
- **AI research assistant** — ask questions in plain English, get answers backed by live SQL against the warehouse
- **Reproducible data pipeline** — every number on the dashboard traces back to a bronze source file through versioned dbt transformations
- **Open dataset** — 58 materialized tables/views spanning 7 data sources (MIT code, CC BY 4.0 data)

### Live services

| Service | URL | Purpose |
|---|---|---|
| Dashboard | [ens-retro-dashboard.onrender.com](https://ens-retro-dashboard.onrender.com) | Interactive Streamlit app — 5 research challenges, 20+ visualizations |
| MCP API | [mcp.ensretro.metagov.org/mcp](https://mcp.ensretro.metagov.org/mcp) | Model Context Protocol endpoint for AI agents (Agent Builder-compatible) |
| Dagster UI | [ens-retro-dagster.onrender.com](https://ens-retro-dagster.onrender.com) | Read-only pipeline view — asset graph, run history, lineage |

> 📷 *Dashboard screenshots and walkthrough video coming soon — see [`docs/developer-docs/`](docs/developer-docs/) for architecture diagrams in the meantime.*

---

## Research Challenges

The dashboard organizes findings around five challenges to ENS governance health:

| # | Challenge | Example questions |
|---|---|---|
| **C1** | Voting Power Concentration | How concentrated is voting power? How stable are early delegates? Does activity track with power? |
| **C2** | Low Broad-Based Participation | Does proposal complexity reduce turnout? Which delegates are dormant? |
| **C3** | Communication Fragmentation | Do insider delegates resist structural reform? How do forum and on-chain vote signals compare? |
| **C4** | Agency & Accountability | *(see dashboard for sub-hypotheses)* |
| **C5** | Treasury & Institutional Liability | Where does DAO money flow? What are the recurring commitments? |

Each challenge decomposes into hypotheses (`H1.3`, `H2.1`, etc.) rendered by dedicated Python modules in `dashboards/scripts/`.

---

## Architecture

```
                   ┌─────────────────────────────────────────┐
                   │           bronze/ (raw data)            │
                   │  ─────────────────────────────────────  │
                   │  governance/   on-chain/   forum/       │
                   │  financial/    grants/     github/      │
                   │  docs/                                  │
                   └─────────────────┬───────────────────────┘
                                     │
                        ┌────────────┴────────────┐
                        │   Dagster orchestration │
                        │   (infra/ingest)        │
                        │                         │
                        │   Snapshot · Discourse  │
                        │   Etherscan · OSO       │
                        │   Safe · SmallGrants    │
                        └────────────┬────────────┘
                                     │
                                     ▼
                   ┌─────────────────────────────────────────┐
                   │           dbt transforms                │
                   │  ─────────────────────────────────────  │
                   │  18 staging views                       │
                   │  16 silver cleaned/typed tables         │
                   │   6 gold analysis-ready tables          │
                   └─────────────────┬───────────────────────┘
                                     │
                                     ▼
                   ┌─────────────────────────────────────────┐
                   │     warehouse/ens_retro.duckdb          │
                   └─────────────────┬───────────────────────┘
                                     │
                ┌────────────────────┼────────────────────┐
                ▼                    ▼                    ▼
      ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
      │ Streamlit        │ │ FastAPI + MCP    │ │ Dagster UI       │
      │ Dashboard        │ │ Server           │ │ (read-only)      │
      │                  │ │                  │ │                  │
      │ dashboards/app.py│ │ dashboards/api.py│ │ infra/           │
      └──────────────────┘ └──────────────────┘ └──────────────────┘
```

**Three deployable services** (all on Render, see `render.yaml`):

1. **Dashboard** (`Dockerfile`) — Streamlit app serving the research frontend + ChatKit widget
2. **MCP API** (`Dockerfile.api`) — FastAPI with REST endpoints and an MCP (Model Context Protocol) server at `/mcp` for OpenAI Agent Builder integration
3. **Dagster** (`Dockerfile.dagster`) — Read-only UI showing the pipeline asset graph and run history

### Why DuckDB + DO Spaces?
The warehouse ships as a single ~40 MB DuckDB file (`warehouse/ens_retro.duckdb`) committed in regular git. Deployed services (Render) download the latest copy from [DigitalOcean Spaces](https://ensretro-data.fra1.digitaloceanspaces.com/) at Docker build time — no Git LFS needed.

**For contributors:** just `git clone` then `python3 scripts/spaces_sync.py --download` — you get a fully-populated warehouse and bronze data ready to query. No LFS setup required.

**For reproducibility:** every number on the dashboard traces back to raw bronze source files. Run `uv run dagster dev` to re-materialize the full pipeline from scratch. The bronze data is append-only and hosted on DigitalOcean Spaces.

---

## Data Sources

| Source | Layer | Via | Active? | Records |
|---|---|---|---|---|
| Snapshot proposals + votes | Governance | GraphQL | ✅ | ~90 proposals / ~48k votes |
| Tally proposals + votes + delegates | Governance | GraphQL | ⚠️ Frozen | ~62 proposals / ~9.5k votes (Tally.xyz shutdown) |
| Discourse forum posts + topics | Discussion | Discourse API | ✅ | `discuss.ens.domains` |
| On-chain delegations | Token | Etherscan API | ✅ | `DelegateChanged` events |
| Token distribution | Token | Etherscan API | ✅ | `Transfer` events |
| Treasury transactions | Financial | Safe API + ledger | ✅ | ENS working-group Safes |
| Grants | Funding | SmallGrants + ledger | ✅ | Formal + small grants |
| GitHub activity | Development | OSO (Open Source Observer) | ✅ | ENS ecosystem repos |
| Governance docs | Reference | Manual/scraped | ✅ | Constitution, bylaws |

All bronze data is immutable append-only JSON/CSV with `metadata.json` provenance files alongside.

---

## Repository layout

```
ENS-Retro-Data/
├── bronze/                Raw data (JSON/CSV, Agora CSVs on DO Spaces)
│   ├── governance/        Snapshot, Tally, Agora governor contract events
│   ├── on-chain/          Delegations, transfers, treasury
│   ├── forum/             Discourse topics + posts
│   ├── financial/         Safe txs, wallet balances, ledger, compensation
│   ├── grants/            SmallGrants + large-grant disbursements
│   ├── github/            OSO code metrics + timeseries
│   └── docs/              ENS governance reference documents
│
├── infra/                 Data pipeline (Dagster + dbt)
│   ├── definitions.py     Central Dagster entry point
│   ├── ingest/            Python ingest modules (8 API clients)
│   ├── dbt/               dbt project — staging → silver → gold
│   ├── validate/          Dagster asset checks (row counts, schema)
│   ├── transform/         Python compute assets (complement to dbt)
│   └── materialize/       Gold-layer composite assets
│
├── dashboards/            Streamlit frontend + ChatKit + FastAPI
│   ├── app.py             Main Streamlit app (research challenges)
│   ├── api.py             FastAPI REST + MCP server
│   ├── scripts/           Hypothesis modules (h1_3, h2_1, …), chart helpers
│   ├── static/            ChatKit iframe pages, landing HTML
│   ├── pages/             Streamlit sub-pages (Chat, …)
│   └── tests/             106 pytest cases (API auth, SQL safety, config)
│
├── warehouse/             DuckDB file output (also on DO Spaces for deploys)
├── docs/                  Research deliverables + developer docs
│   ├── developer-docs/    Architecture, API ref, data dictionary, workflow guides
│   ├── vector-store-exports/  Auto-generated gold table markdown (chatbot knowledge base)
│   └── Phase 1/           Research design docs, codebook, KII synopsis
├── scripts/               Standalone utilities (taxonomy seeds, serve.sh)
├── .dagster/              Dagster instance state (also on DO Spaces for deploys)
├── Dockerfile             Dashboard image
├── Dockerfile.api         MCP API image
├── Dockerfile.dagster     Dagster read-only UI image
├── render.yaml            Render blueprint (3 services, main branch, auto-deploy)
├── pyproject.toml         Python dependencies (managed by uv)
└── taxonomy.yaml          Controlled vocabularies (single source of truth)
```

---

# Developer Guide

Everything below this line is for people who want to run the pipeline, modify the dashboard, or contribute changes. If you just want to use the research, stop here and visit the live dashboard.

## Prerequisites

- **Python 3.12** (or 3.11, but 3.12 is what CI and Docker use)
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager
- **No Git LFS needed** — all data is regular git or downloaded from DO Spaces at deploy time
- **[DuckDB CLI](https://duckdb.org/docs/installation/)** — optional, for interactive queries

### Required environment variables

Copy `.env.example` to `.env` and fill in the keys you need. Not every script needs every key — only set what you actually run:

| Key | Needed by | What it's for |
|---|---|---|
| `ETHERSCAN_API_KEY` | `etherscan_api.py` | On-chain event fetching (delegations, transfers) |
| `OPENAI_API_KEY` | dashboard + chat | Minting ChatKit session tokens and vector-store sync |
| `WORKFLOW_ID` | dashboard chat | Agent Builder workflow ID |
| `AGENT_API_KEY` | MCP API (`api.py`) | Bearer token protecting `/mcp` and `/api/*` endpoints |
| `OSO_API_KEY` | `oso_api.py` | Open Source Observer GitHub metrics |
| `DAGSTER_HOME` | dagster dev | Should point at the repo's `.dagster/` directory |

> ⚠️ **Security:** The MCP API fails closed if `AGENT_API_KEY` is unset — every authenticated request returns HTTP 503 until you configure the key. There is no dev-mode bypass.

## Quick start

```bash
# Clone (no LFS needed)
git clone https://github.com/metagov/ENS-Retro-Data.git
cd ENS-Retro-Data

# Install Python dependencies
uv sync --extra dev

# Install dbt packages (dbt_utils)
cd infra/dbt && uv run dbt deps && cd ../..

# Seed the taxonomy into dbt
uv run python scripts/generate_taxonomy_seeds.py

# Run the full pipeline once (bronze → silver → gold)
DAGSTER_HOME=$(pwd)/.dagster uv run dagster asset materialize \
    -m infra.definitions --select '*'

# Launch the Streamlit dashboard at http://localhost:8501
uv run streamlit run dashboards/app.py

# Or launch the Dagster UI at http://localhost:3000
./scripts/serve.sh              # full edit mode
./scripts/serve.sh --read-only  # read-only mode (matches Render deployment)
```

## Command reference

### Orchestration (Dagster)

| Command | Description |
|---|---|
| `uv run dagster dev` | Launch Dagster UI at http://localhost:3000 |
| `uv run dagster asset materialize -m infra.definitions --select snapshot_proposals` | Materialize one bronze asset |
| `uv run dagster asset materialize -m infra.definitions --select '*'` | Materialize everything |
| `uv run dagster asset check -m infra.definitions` | Run all asset checks |

### Transforms (dbt) — run from `infra/dbt/`

| Command | Description |
|---|---|
| `uv run dbt build` | All models + tests (staging → silver → gold) |
| `uv run dbt run --select silver` | Only silver models |
| `uv run dbt test` | Only tests |
| `uv run dbt seed` | Load `taxonomy.yaml`-derived seed CSVs |
| `uv run dbt parse` | Generate `manifest.json` (required by dagster-dbt) |

### Querying (DuckDB)

```bash
duckdb warehouse/ens_retro.duckdb
D SHOW ALL TABLES;
D SELECT * FROM main_gold.delegate_scorecard LIMIT 10;
D SELECT metric, value FROM main_gold.decentralization_index;
```

### Tests & linting

| Command | Description |
|---|---|
| `cd dashboards && uv run pytest tests/` | Run dashboard + API tests (106 cases) |
| `uv run ruff check .` | Lint everything |
| `uv run ruff check . --fix` | Auto-fix |
| `uv run ruff format .` | Format |

## Running the MCP API locally

```bash
export AGENT_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
cd dashboards
uv run uvicorn api:app --host 0.0.0.0 --port 8001 --reload

# Smoke test (new terminal)
curl http://localhost:8001/                          # landing page
curl -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Deployment

All three services auto-deploy from `main` via [Render's blueprint](render.yaml):

```bash
git push origin main
# → Render detects the push, rebuilds affected services
# → ~3 min later, changes are live
```

Each service reads its secrets from Render's environment variable store (not from `.env`). Update via the Render dashboard or `mcp__render__update_environment_variables` if you're using the Render MCP.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development workflow, PR conventions, and test requirements.

Security disclosures: please read [`SECURITY.md`](SECURITY.md) before filing a public issue for any auth / SQL-safety / data-access concerns.

## Citation

If you use this dataset or code in research, please cite:

```bibtex
@misc{ens_retro_data_2026,
  title        = {{ENS DAO Governance Research Platform}},
  author       = {Metagov},
  year         = {2026},
  url          = {https://github.com/metagov/ENS-Retro-Data},
  note         = {MIT (code), CC BY 4.0 (data)}
}
```

## License

Dual-licensed:

- **Code** (`.py`, `.sql`, `.html`, Dockerfiles, scripts) — [MIT](LICENSE-CODE)
- **Data & research** (`bronze/`, `warehouse/`, `docs/`, all `.md`/`.csv`/`.json`/`.pdf`) — [CC BY 4.0](LICENSE-DATA)

See [LICENSE](LICENSE) for the full breakdown. Attribution is required for reuse of data and research materials.
