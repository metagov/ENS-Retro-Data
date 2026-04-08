# `dashboards/scripts/` — Chart & Hypothesis Modules

This directory holds the rendering logic for every chart and analysis in the Streamlit dashboard. Files are named after the **research hypothesis** they support.

## Naming scheme

The dashboard organizes findings around **five challenges** (C1–C5) and their sub-hypotheses. Script filenames encode that hierarchy:

```
<prefix>_<hypothesis>_<topic>.py
```

| Prefix | Meaning | Example |
|---|---|---|
| `h<N>_<M>_` | Hypothesis N.M under a research challenge | `h1_3_delegation_flow.py` → H1.3 |
| `c<N>_h<M>_` | Challenge-specific hypothesis | `c5_h1_cashflow_explorer.py` → C5/H1 |
| `c<N>_` | Challenge-level visualization (no sub-hypothesis) | `c2_participation_variance.py` → C2 overview |
| `hx_` | Cross-challenge / exploratory hypothesis | `hx_1_outcome_robustness.py` |

The mapping from script → challenge is defined in `dashboards/config.yaml`. Each visual block looks like:

```yaml
- id: "H1.3"
  title: "…"
  visuals:
    - id: "delegation_flow"
      render:
        module: "scripts.h1_3_delegation_flow"
        fn: "render_delegation_flow"
```

Look there to find which script powers which chart.

## Research challenges

| # | Challenge | Scripts (examples) |
|---|---|---|
| **C1** | Voting Power Concentration | `h1_3_*`, `h2_1_*`, `h3_3_*`, `h6_2_*` |
| **C2** | Low Broad-Based Participation | `c2_participation_variance`, `h4_1_complexity_vs_turnout` |
| **C3** | Communication Fragmentation | `c3_structural_reforms`, `h2_3_*` |
| **C4** | Agency & Accountability | `hx_1_outcome_robustness`, `hx_2_vote_alignment` |
| **C5** | Treasury & Institutional Liability | `c5_h1_cashflow_explorer`, `c5_h2_ledger_explorer`, `c5_h3_compensation_explorer` |

## Non-hypothesis files

These are shared infrastructure, not research modules:

| File | Purpose |
|---|---|
| `config.py` | Loads + validates `dashboards/config.yaml`; resolves `module.fn` into callables |
| `db.py` | DuckDB connection helper — single source of truth for the warehouse path |
| `chat_session.py` | Mints OpenAI ChatKit session tokens (rate-limited, TTL-cached) |
| `chat_tools.py` | SQL classifier + safe-query helpers used by the agent |
| `chat_widget.py` | Renders the floating ChatKit bubble on every dashboard page |
| `proposal_type.py` | Heuristic + LLM proposal category classifier (with on-disk cache) |

## Adding a new visualization

1. Write `dashboards/scripts/<script>.py` with a named render function:
   ```python
   import streamlit as st

   def render_my_chart():
       st.markdown("## My chart title")
       # ... do the thing
   ```

2. Reference it in `dashboards/config.yaml`:
   ```yaml
   - id: "H1.4"
     title: "…"
     visuals:
       - id: "my_chart"
         render:
           module: "scripts.my_script"
           fn: "render_my_chart"
   ```

3. Write tests in `dashboards/tests/` if the chart does non-trivial computation. Keep Streamlit calls and data math in separate functions so the math is unit-testable without the UI.

4. Run the dashboard locally (`uv run streamlit run dashboards/app.py`) and visit the relevant challenge page.

## Testing

```bash
cd dashboards
uv run pytest tests/ -v
```

Tests live in `dashboards/tests/` and cover config loading, DuckDB connection, API auth/SQL safety, and a handful of computation helpers. See `tests/test_computations.py` for the pattern.
