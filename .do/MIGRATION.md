# Render → DigitalOcean Migration Guide

## Why

GitHub LFS bandwidth cap (10 GB/month) is being consumed by Render deploys.
Each push to main triggers 3 service rebuilds that each clone ~294 MB of LFS data.
DO App Platform is the target because metagov already has billing set up there.

## Pre-migration checklist

- [ ] DO account access with metagov org billing
- [ ] `doctl` CLI installed and authenticated: `doctl auth init`
- [ ] GitHub repo connected to DO (one-time OAuth in DO dashboard)

## Step-by-step

### 1. Create the app

```bash
doctl apps create --spec .do/app.yaml
```

Note the app ID from the output (e.g., `a1b2c3d4-...`).

### 2. Set secrets

Secrets can't be in the spec file. Set them via the DO dashboard or CLI:

```bash
# Dashboard service
doctl apps update <app-id> \
  --env OPENAI_API_KEY=<your-key> \
  --env WORKFLOW_ID=<your-workflow-id>

# API service  
doctl apps update <app-id> \
  --env AGENT_API_KEY=<your-key>
```

Or use the DO dashboard: Apps → ens-retro-data → Settings → Environment Variables.

### 3. Verify builds

Wait for the initial deploy to complete (~5-10 minutes):

```bash
doctl apps list-deployments <app-id>
```

Check logs if a service fails:

```bash
doctl apps logs <app-id> --type=build
doctl apps logs <app-id> --type=run
```

### 4. Smoke test

```bash
# Get the app's default domain
doctl apps get <app-id> --format DefaultIngress

# Test each service
curl https://<default-domain>/                    # Dashboard (Streamlit)
curl https://<default-domain>/api/                # API landing page
curl https://<default-domain>/api/tables          # API endpoint (needs auth)
```

### 5. DNS cutover

Once smoke tests pass, update DNS:

```bash
# Add custom domain to DO app
doctl apps create-domain <app-id> --domain ensretro.metagov.org
doctl apps create-domain <app-id> --domain mcp.ensretro.metagov.org
```

Then update your DNS provider:
- `ensretro.metagov.org` → CNAME to DO's ingress domain
- `mcp.ensretro.metagov.org` → CNAME to DO's ingress domain

### 6. Decommission Render

After DNS propagation (24-48h), delete the Render services:
- ens-retro-dashboard
- ens-retro-api
- ens-retro-dagster

### 7. Clean up LFS (optional, post-migration)

Once DO is running with persistent volumes (or Spaces for data hosting),
you can remove LFS tracking from the repo entirely:

```bash
# Remove LFS tracking rules
git lfs untrack "warehouse/*.duckdb"
git lfs untrack "bronze/governance/agora/**/*.csv"
git lfs untrack ".dagster/storage/*.db"

# Convert LFS pointers to regular files
git lfs migrate export --include="warehouse/*.duckdb,.dagster/storage/*.db"
```

## Cost comparison

| | Render (current) | DO basic-xs | DO basic-s |
|---|---|---|---|
| Per service | $7/mo | $5/mo | $10/mo |
| 3 services | $21/mo | $15/mo | $30/mo |
| RAM per service | 512 MB | 512 MB | 1 GB |
| Persistent disk | No | No (basic) | No (basic) |
| LFS bandwidth | Burns GitHub quota | Burns GitHub quota | Burns GitHub quota |

**Note:** Both Render and DO App Platform clone from GitHub, so LFS bandwidth
is consumed regardless of platform. The real LFS fix is either:
- Remove large files from LFS (the stopgap already applied on main)
- Host data on DO Spaces ($5/mo for 250 GB) and download at build time
- Use DO Managed Database instead of file-based DuckDB

## Rollback

If DO doesn't work out, the Render services are still configured in
`render.yaml` and can be re-enabled by pushing to main with Render's
auto-deploy still connected.
