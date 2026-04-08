# Roadmap & Known Limitations

This document tracks **structural improvements** that didn't fit into the open-source polish pass. Everything here is known, understood, and deferred — not hidden. If you're a contributor looking for a project, any of these are fair game.

> Last updated: 2026-04-09 (initial OSS publication pass)

---

## A. Clone size (~1.2 GB via Git LFS)

**Current state:** The repo bundles all raw data (`bronze/`, 397 MB) and the materialized warehouse (`warehouse/ens_retro.duckdb`, 40 MB) via Git LFS. A fresh clone pulls the full dataset.

**Why it's this way:** Render's free/starter tier has no persistent disk — LFS acts as the shared state store. Shipping the warehouse alongside the code lets contributors start querying immediately without re-running the pipeline (which requires multiple API keys).

**Pain points:**
- Contributors on slow connections wait 3–10 minutes to clone
- CI cold starts pull the full LFS payload
- GitHub LFS bandwidth quotas are finite

**Options we've considered:**
1. **Keep as-is + document loudly** (current choice) — simplest, contributors get a working system instantly
2. **Split data into a sibling `ens-retro-data-dumps` repo** — main repo stays code-only; data lives in a separate LFS-tracked repo that pipeline runs pull from
3. **Host bronze on S3/R2 or Zenodo** — fetched at pipeline runtime; main repo ships only code + tiny test fixtures
4. **Generate the warehouse in CI on first deploy** — requires all API keys in CI secrets, slower first-deploy

**Decision deferred until:** contributor volume or bandwidth quotas actually become a problem.

---

## B. Render region lock (Singapore)

**Current state:** All three Render services (`ens-retro-dashboard`, `ens-retro-api`, `ens-retro-dagster`) deploy to `singapore` per `render.yaml`. Render had a Singapore-region incident on 2026-04-08 that temporarily blocked new deploys.

**Why it's this way:** Singapore was the closest region to the maintainer when services were first provisioned.

**Options:**
1. **Multi-region** — run a primary in Singapore + a hot standby in Oregon or Frankfurt; use Cloudflare/DNS for failover
2. **Migrate to a historically more stable region** — Oregon has had fewer incidents over 2025–2026
3. **Stay in Singapore** — accept occasional incidents as the tradeoff for latency

**Decision deferred until:** incident frequency justifies the complexity.

---

## C. Custom domain strategy isn't documented

**Current state:** The MCP API is reachable at both `ens-retro-api.onrender.com` and the custom domain `mcp.ensretro.metagov.org`. The dashboard has only the Render-provided URL. Neither arrangement is documented in the repo.

**Gaps:**
- No explanation of which DNS is authoritative
- No runbook for adding a custom domain for the dashboard
- No guidance on certificate provisioning / renewal (Render handles it automatically, but that's not obvious to contributors)

**What needs to happen:** A short doc in `docs/developer-docs/deployment.md` covering custom domains, environment variables per service, and how to roll back a bad deploy via the Render MCP or dashboard.

---

## D. Test coverage is inverted (pipeline has 0 tests, dashboard has 106)

**Current state:**
- `dashboards/tests/` — 106 pytest cases (API auth, SQL validator, config, warehouse connection)
- `infra/ingest/`, `infra/transform/`, `infra/materialize/`, `infra/validate/` — **zero Python tests**
- `infra/dbt/models/` — dbt data tests exist for some silver and gold models, but coverage is uneven

**Why it's inverted:** The dashboard's SQL validation path is security-critical (it's the attack surface for the MCP agent), so tests accumulated there first. The pipeline has traditionally relied on Dagster asset checks and dbt tests.

**What minimum coverage should look like:**
1. **Unit tests** for each `infra/ingest/*.py` module — mock the HTTP response, assert the flattener produces the expected shape
2. **Integration test** that runs the full bronze → silver → gold pipeline on a tiny fixture dataset (5 proposals, 20 votes) to catch breakage end-to-end
3. **dbt test coverage parity** — every silver and gold model should have at least one `unique` or `not_null` test on its primary key
4. **Asset check coverage** — every bronze asset should have a row-count check

**Rough effort estimate:** 1 day human team / ~2 hours CC+gstack for the full matrix. Split into per-module PRs.

---

## E. Three dbt models excluded pending missing source files

**Current state:** Per the internal project log, three dbt staging/silver models are currently disabled because their source JSON files aren't yet ingested:
- `stg_compensation` / `clean_compensation` — compensation ledger missing
- `stg_grants` / `clean_grants` — grants file needs refreshing
- `stg_delegate_profiles` — interview-derived profiles not indexed

**Impact:** Contributors running `dbt build` may hit errors if these sources aren't explicitly disabled. The gold tables that depend on them (`c5_h3_compensation_explorer`, `c5_h2_ledger_explorer`, some H1.3 visualizations) fall back to partial data or a "work in progress" banner on the dashboard.

**What needs to happen:**
1. Ship the missing source files (either as stable JSON snapshots in bronze/ or as a scraping script in `infra/ingest/`)
2. Alternatively, document clearly in the `bronze/financial/metadata.json`, `bronze/grants/metadata.json`, and `bronze/interviews/metadata.json` which files are expected and where they come from
3. Add tests that skip these models gracefully with a clear message ("model disabled: source file X missing")

---

## How to contribute to this roadmap

If you'd like to tackle one of these items:

1. Open an issue referencing the section (e.g., "[ROADMAP-D] Add unit tests for infra/ingest/etherscan_api.py")
2. Discuss the approach before implementing — these are architectural items where a shared plan avoids rework
3. Keep PRs scoped to one roadmap item at a time

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the general PR workflow.
