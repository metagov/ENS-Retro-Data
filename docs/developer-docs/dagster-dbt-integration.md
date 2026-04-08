# Dagster-dbt Integration

How the Dagster orchestrator and dbt SQL engine are connected.

## Entry Point

Dagster discovers the pipeline via `pyproject.toml`:

```toml
[tool.dagster]
module_name = "infra.definitions"
```

This loads `infra/definitions.py`, which assembles all assets, checks, resources, and sensors into a single `Definitions` object.

## Asset Registration

```python
# infra/definitions.py (current)
defs = Definitions(
    assets=[*bronze_assets, ens_dbt_assets],   # Python + dbt assets
    asset_checks=[*asset_checks],               # 10 bronze checks
    sensors=[vector_store_sync_sensor],
    resources={
        "dbt": DbtCliResource(project_dir=os.fspath(dbt_project.project_dir)),
        "etherscan_config": EtherscanApiConfig(api_key=os.environ.get("ETHERSCAN_API_KEY", "")),
        "oso_config": OsoApiConfig(api_key=os.environ.get("OSO_API_KEY", "")),
    },
)
```

- `bronze_assets`: **18** Python assets loaded from `infra/ingest/assets.py` via `load_assets_from_modules`
- `ens_dbt_assets`: single dbt asset group wrapping all **40** dbt models (18 staging + 16 silver + 6 gold)
- `asset_checks`: **10** checks loaded from `infra/validate/checks.py` via `load_asset_checks_from_modules` (5 row-count + 5 Great Expectations suites, all on governance assets)
- `vector_store_sync_sensor`: re-exports gold tables to markdown and refreshes the OpenAI vector store after gold materializations

## Source-to-Asset Mapping

The critical bridge between Dagster and dbt is the `EnsDbtTranslator` class in `infra/dbt_project.py`.

### Problem

Dagster needs to know that dbt's `{{ source('bronze_governance', 'snapshot_proposals') }}` depends on the Dagster asset named `snapshot_proposals`. Without this mapping, Dagster wouldn't know to run the bronze fetcher before the dbt build.

### Solution

```python
# infra/dbt_project.py
_SOURCE_TO_ASSET_KEY = {
    ("bronze_governance", "snapshot_proposals"):    AssetKey("snapshot_proposals"),
    ("bronze_governance", "snapshot_votes"):        AssetKey("snapshot_votes"),
    ("bronze_governance", "tally_proposals"):       AssetKey("tally_proposals"),
    ("bronze_governance", "tally_votes"):           AssetKey("tally_votes"),
    ("bronze_governance", "tally_delegates"):       AssetKey("tally_delegates"),
    ("bronze_governance", "votingpower_delegates"): AssetKey("votingpower_delegates"),
    ("bronze_onchain",    "delegations"):           AssetKey("delegations"),
    ("bronze_onchain",    "token_distribution"):    AssetKey("token_distribution"),
    ("bronze_onchain",    "treasury_flows"):        AssetKey("treasury_flows"),
    ("bronze_financial",  "compensation"):          AssetKey("compensation"),
    ("bronze_grants",     "grants"):                AssetKey("grants"),
    ("bronze_interviews", "delegate_profiles"):     AssetKey("delegate_profiles"),
    ("bronze_forum",      "forum_posts"):           AssetKey("forum_posts"),
    ("bronze_forum",      "forum_topics"):          AssetKey("forum_topics"),
}

class EnsDbtTranslator(DagsterDbtTranslator):
    def get_asset_key(self, dbt_resource_props: dict) -> AssetKey:
        resource_type = dbt_resource_props.get("resource_type")
        if resource_type == "source":
            source_name = dbt_resource_props.get("source_name", "")
            table_name = dbt_resource_props.get("name", "")
            key = _SOURCE_TO_ASSET_KEY.get((source_name, table_name))
            if key:
                return key
        return super().get_asset_key(dbt_resource_props)

    def get_group_name(self, dbt_resource_props: dict) -> str:
        # fqn = ["ens_retro", "<folder>", "<model_name>"]
        fqn = dbt_resource_props.get("fqn", [])
        if len(fqn) >= 2 and fqn[1] in ("staging", "silver", "gold"):
            return fqn[1]
        return super().get_group_name(dbt_resource_props)
```

The translator does two things:
1. **Source mapping** — maps dbt source references to Dagster bronze asset keys so Dagster knows the dependency order.
2. **Group assignment** — reads the dbt folder (`staging`/`silver`/`gold`) from the fully-qualified name and uses it as the Dagster UI group name, so models are visually grouped by medallion layer.

> **Note:** `_SOURCE_TO_ASSET_KEY` currently contains some entries for sources whose corresponding Python assets have been renamed or are handled differently (e.g., `bronze_interviews.delegate_profiles`, `bronze_financial.compensation`). These are harmless — if the dbt source exists but no Python asset matches, Dagster just treats the source as external. See [`ROADMAP.md`](../ROADMAP.md) for cleanup plans.

## dbt Asset Function

```python
# infra/dbt_assets.py
@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=EnsDbtTranslator(),
)
def ens_dbt_assets(context, dbt: DbtCliResource):
    (dbt_project.project_dir.parent.parent / "warehouse").mkdir(exist_ok=True)
    yield from dbt.cli(["build"], context=context).stream()
```

- Uses the dbt manifest (generated by `dbt parse`) to discover all models at import time
- Creates `warehouse/` directory for DuckDB output
- Runs `dbt build` which executes models, tests, and seeds in dependency order
- Streams results back to Dagster for real-time logging

## Custom Source Macro

dbt models reference bronze files via `{{ source() }}`. A custom macro override in `infra/dbt/macros/source.sql` translates these to DuckDB file-reading functions:

```sql
{% macro source(source_name, table_name) %}
  {%- set external_locations = {
    'bronze_governance.snapshot_proposals':
        "read_json_auto('../../bronze/governance/snapshot_proposals.json')",
    'bronze_onchain.delegations':
        "read_json_auto('../../bronze/on-chain/delegations.json')",
    'bronze_financial.ens_ledger':
        "read_csv_auto('../../bronze/financial/ens_ledger_transactions.csv')",
    ...
  } -%}
  {%- set key = source_name ~ '.' ~ table_name -%}
  {%- if key in external_locations -%}
    {{ external_locations[key] }}
  {%- else -%}
    {{ builtins.source(source_name, table_name) }}
  {%- endif -%}
{% endmacro %}
```

This lets staging models use standard dbt `{{ source() }}` syntax while actually reading JSON/CSV files from disk.

## Manifest Generation

The dbt manifest (`infra/dbt/target/manifest.json`) must exist before Dagster starts. It's generated by:

```python
# infra/dbt_project.py
dbt_project = DbtProject(project_dir=PROJECT_DIR)
dbt_project.prepare_if_dev()  # runs dbt parse at import time in dev mode
```

If the manifest is missing, run manually:

```bash
cd infra/dbt && uv run dbt parse
```

The Dagster Dockerfile (`Dockerfile.dagster`) runs `dbt parse` during image build so the manifest is baked in before the webserver starts.

## Asset Graph

The resulting Dagster asset graph looks like:

```
Bronze (Python)          dbt staging          dbt silver           dbt gold
──────────────          ───────────          ──────────           ────────
snapshot_proposals ──▶ stg_snapshot_proposals ──▶ clean_snapshot_proposals ──┐
snapshot_votes ──────▶ stg_snapshot_votes ──────▶ clean_snapshot_votes ─────┤
tally_proposals ────▶ stg_tally_proposals ────▶ clean_tally_proposals ────┤
tally_votes ────────▶ stg_tally_votes ────────▶ clean_tally_votes ───────┤
tally_delegates ────▶ stg_tally_delegates ────▶ clean_tally_delegates ───┤
                                                                          ├──▶ governance_activity
                                                                          ├──▶ delegate_scorecard
                                                                          ├──▶ participation_index
                                                                          ├──▶ decentralization_index
delegations ────────▶ stg_delegations ────────▶ clean_delegations ───────┤
token_distribution ─▶ stg_token_distribution ─▶ clean_token_distribution ┤
treasury_flows ─────▶ stg_treasury_flows ─────▶ clean_treasury_flows ────┼──▶ treasury_summary
ens_ledger_tx ──────▶ stg_ens_ledger ─────────▶ clean_ens_ledger ────────┘
forum_topics ───────▶ stg_forum_topics ──────▶ snapshot_discourse_crosswalk ──┐
forum_posts ────────▶ stg_forum_posts ───────▶ tally_discourse_crosswalk ────┼──▶ governance_discourse_activity
                                                                             │
smallgrants_* ──────▶ stg_grants ─────────────▶ clean_grants
ens_safe_tx ────────▶ (consumed by treasury_flows)
ens_wallet_balances ▶ (consumed by treasury_flows)
oso_* ──────────────▶ stg_oso_* ──────────────▶ clean_oso_*
```

## Resources

| Resource | Type | Configuration |
|---|---|---|
| `dbt` | `DbtCliResource` | `project_dir = infra/dbt` |
| `etherscan_config` | `EtherscanApiConfig` | `api_key = os.environ["ETHERSCAN_API_KEY"]` |
| `oso_config` | `OsoApiConfig` | `api_key = os.environ["OSO_API_KEY"]` |

The `dbt` resource is injected into `ens_dbt_assets`. The `etherscan_config` resource is injected into the on-chain assets (`delegations`, `token_distribution`, `treasury_flows`). The `oso_config` resource is injected into the `bronze_github` assets.

Snapshot, Discourse, Safe, and SmallGrants clients don't require API keys and are called directly by their respective assets without a Dagster resource wrapper.

> **Removed:** `TallyApiConfig` used to be a registered resource. It was removed when Tally.xyz shut down their public API and the tally assets were converted to file sentinels.
