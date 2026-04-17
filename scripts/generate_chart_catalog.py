"""Generate a chart catalog markdown for the OpenAI vector store.

For each chart on the dashboard, produces:
- Title, challenge, hypothesis, verdict
- Public screenshot URL (on DO Spaces)
- Source tables + key columns
- Reproduction SQL
- Sample data (top 10 rows) pulled live from the warehouse
- Takeaway text

The catalog gives the ChatKit agent everything it needs to cite or
reproduce any chart via its DuckDB MCP tool, and to reference the
image URL inline when visuals would help.
"""

import json
import sys
from pathlib import Path

import duckdb
import yaml

REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "dashboards" / "config.yaml"
DB_PATH = REPO_ROOT / "warehouse" / "ens_retro.duckdb"
EXPORT_DIR = REPO_ROOT / "docs" / "vector-store-exports"
IMAGE_URLS_PATH = EXPORT_DIR / "_image_urls.json"
CATALOG_PATH = EXPORT_DIR / "auto__chart_catalog.md"


# Per-hypothesis: source tables, key columns, canonical reproduction SQL
# Keyed by (challenge_id, hypothesis_id)
# The SQL below is chosen to be simple enough for an LLM to adapt, not the
# full production query — the point is to give the agent a correct starting
# point that actually runs against the warehouse.
CHART_SPECS = {
    ("C1", "H1.3"): {
        "tables": ["main_silver.clean_delegations", "main_silver.clean_token_distribution", "main_gold.delegate_scorecard"],
        "key_columns": ["delegator", "delegate", "delegated_at", "balance", "voting_power"],
        "summary": "Classifies top-50 delegates' current delegators by the quarter their current delegation was first established, then computes each quarter's share of top-50 VP.",
        "sql": """
-- H1.3 — Legacy distribution: VP share by cohort quarter for top-50 delegates
WITH current_delegations AS (
    SELECT delegator, delegate, delegated_at,
           ROW_NUMBER() OVER (PARTITION BY delegator ORDER BY delegated_at DESC) AS rn
    FROM main_silver.clean_delegations
),
active AS (
    SELECT delegator, delegate, delegated_at
    FROM current_delegations
    WHERE rn = 1 AND delegate != '0x0000000000000000000000000000000000000000'
),
active_with_balance AS (
    SELECT a.delegator, a.delegate, a.delegated_at, td.balance AS token_balance
    FROM active a
    JOIN main_silver.clean_token_distribution td ON td.address = a.delegator
    WHERE td.balance > 0
),
delegate_totals AS (
    SELECT delegate, SUM(token_balance) AS total_vp,
           ROW_NUMBER() OVER (ORDER BY SUM(token_balance) DESC) AS rnk
    FROM active_with_balance GROUP BY delegate
),
top50 AS (SELECT delegate FROM delegate_totals WHERE rnk <= 50),
cohorted AS (
    SELECT awb.token_balance,
           date_trunc('quarter', awb.delegated_at)::DATE AS cohort_quarter_start
    FROM active_with_balance awb JOIN top50 t ON t.delegate = awb.delegate
)
SELECT cohort_quarter_start,
       SUM(token_balance) AS vp_in_cohort,
       SUM(token_balance) / SUM(SUM(token_balance)) OVER () * 100 AS pct_of_top50_vp
FROM cohorted GROUP BY cohort_quarter_start ORDER BY cohort_quarter_start
""".strip(),
    },
    ("C1", "H1.3_flow"): {  # Alternate view — delegation flow
        "tables": ["main_silver.clean_delegations", "main_gold.delegate_scorecard"],
        "key_columns": ["delegate", "delegator", "delegated_at"],
        "summary": "Net delegation flow per quarter (inflows - outflows) for the top-20 delegates, inferred from delegation event history using LAG().",
        "sql": None,  # Same chart; covered in H1.3 entry
    },
    ("C1", "H2.1"): {
        "tables": ["main_gold.delegate_scorecard", "main_gold.decentralization_index"],
        "key_columns": ["voting_power", "metric", "value"],
        "summary": "Lorenz curve on voting power distribution. Gini coefficient computed in Python from sorted VP array.",
        "sql": """
-- H2.1 — Concentration curve base data
SELECT voting_power FROM main_gold.delegate_scorecard
WHERE voting_power > 0 ORDER BY voting_power DESC
""".strip(),
    },
    ("C1", "H3.3"): {
        "tables": ["main_silver.clean_delegations", "main_gold.delegate_scorecard"],
        "key_columns": ["delegator", "delegate", "delegated_at"],
        "summary": "Per-delegator count of delegate changes (0, 1, 2, 3, 4, 5+) plus Kaplan-Meier survival curves for top-20 vs smaller delegate cohorts.",
        "sql": """
-- H3.3 — Churn distribution by number of delegate changes per delegator
WITH excl_self AS (
    SELECT delegator, delegate, delegated_at
    FROM main_silver.clean_delegations
    WHERE delegator != delegate AND delegate != '0x0000000000000000000000000000000000000000'
),
with_prev AS (
    SELECT delegator, delegate,
           LAG(delegate) OVER (PARTITION BY delegator ORDER BY delegated_at) AS prev
    FROM excl_self
),
changes AS (
    SELECT delegator,
           SUM(CASE WHEN prev IS NOT NULL AND delegate != prev THEN 1 ELSE 0 END) AS n_changes
    FROM with_prev GROUP BY delegator
)
SELECT
    CASE WHEN n_changes >= 5 THEN '5+' ELSE CAST(n_changes AS VARCHAR) END AS bucket,
    COUNT(*) AS n_delegators
FROM changes GROUP BY bucket ORDER BY bucket
""".strip(),
    },
    ("C1", "H6.2"): {
        "tables": ["main_silver.clean_snapshot_votes", "main_silver.clean_snapshot_proposals",
                   "main_silver.clean_tally_votes", "main_silver.clean_tally_proposals",
                   "main_gold.delegate_scorecard"],
        "key_columns": ["address", "ens_name", "voting_power", "proposals_voted"],
        "summary": "Top-30 delegates' Snapshot (or Tally) participation rate over last 12 months, with a monthly activity grid for the top 10.",
        "sql": """
-- H6.2 — Snapshot activity vs voting power for top-30 delegates (last 12 months)
WITH snapshot_proposals_12m AS (
    SELECT COUNT(DISTINCT proposal_id) AS total_proposals
    FROM main_silver.clean_snapshot_proposals
    WHERE start_date >= CURRENT_DATE - INTERVAL '12 months'
),
delegate_votes_12m AS (
    SELECT sv.voter AS address, COUNT(DISTINCT sv.proposal_id) AS proposals_voted
    FROM main_silver.clean_snapshot_votes sv
    JOIN main_silver.clean_snapshot_proposals sp ON sv.proposal_id = sp.proposal_id
    WHERE sp.start_date >= CURRENT_DATE - INTERVAL '12 months'
    GROUP BY sv.voter
),
top_delegates AS (
    SELECT address, ens_name, voting_power FROM main_gold.delegate_scorecard
    ORDER BY voting_power DESC LIMIT 30
)
SELECT d.ens_name, d.voting_power,
       COALESCE(dv.proposals_voted, 0) AS proposals_voted,
       tp.total_proposals,
       ROUND(COALESCE(dv.proposals_voted, 0)::DOUBLE / NULLIF(tp.total_proposals, 0) * 100, 1) AS participation_rate
FROM top_delegates d LEFT JOIN delegate_votes_12m dv ON d.address = dv.address
CROSS JOIN snapshot_proposals_12m tp ORDER BY d.voting_power DESC
""".strip(),
    },
    ("C2", "H4.1"): {
        "tables": ["main_silver.clean_snapshot_proposals", "main_silver.clean_snapshot_votes",
                   "main_silver.clean_tally_proposals", "main_silver.clean_tally_votes"],
        "key_columns": ["proposal_id", "title", "body", "unique_voters", "complexity_score"],
        "summary": "LLM-scored proposal complexity (cognitive load, technical depth, context dependency, time to evaluate) correlated with voter turnout on Snapshot and Tally. Spearman ρ computed in Python.",
        "sql": """
-- H4.1 — Snapshot turnout per proposal (complexity scored in Python via LLM)
SELECT p.proposal_id, LEFT(p.title, 60) AS title,
       CAST(p.start_date AS DATE) AS date,
       COUNT(DISTINCT v.voter) AS unique_voters
FROM main_silver.clean_snapshot_proposals p
LEFT JOIN main_silver.clean_snapshot_votes v ON p.proposal_id = v.proposal_id
WHERE p.status = 'closed'
GROUP BY p.proposal_id, p.title, p.start_date
ORDER BY p.start_date DESC LIMIT 20
""".strip(),
    },
    ("C3", "H2.2"): {
        "tables": ["main_silver.clean_snapshot_proposals", "main_silver.clean_tally_proposals",
                   "main_gold.governance_activity", "main_gold.delegate_scorecard"],
        "key_columns": ["proposal_id", "title", "for_pct", "against_pct", "vote_choice"],
        "summary": "Reform vs routine outcomes: keyword-classifies reform proposals, then plots 'for%' distribution and a top-30 delegate × reform-proposal heatmap showing who votes for/against/abstains.",
        "sql": """
-- H2.2 — Snapshot for/against percentages for outcome-distribution plot
SELECT sp.proposal_id, LEFT(sp.title, 60) AS title, sp.status,
       ga.for_pct, ga.against_pct
FROM main_silver.clean_snapshot_proposals sp
JOIN main_gold.governance_activity ga ON ga.proposal_id = sp.proposal_id
WHERE sp.status = 'closed' AND ga.source = 'snapshot'
ORDER BY sp.start_date DESC LIMIT 20
""".strip(),
    },
    ("C3", "H3.2"): {
        "tables": [],
        "key_columns": [],
        "summary": "Hypothesis is in development — no dashboard visualization yet. Information asymmetry between large and small delegates observed qualitatively via stakeholder interviews; quantitative evidence pending.",
        "sql": None,
    },
    ("C3", "H6.3"): {
        "tables": ["main_silver.clean_snapshot_proposals", "main_silver.clean_tally_proposals"],
        "key_columns": ["proposal_id", "title", "body", "status", "proposal_date"],
        "summary": "Classifies proposals as 'structural experiment' via keyword matching on title + body. Timeline shows when experiments happen vs routine funding proposals.",
        "sql": """
-- H6.3 — Tally proposals classified in Python as experiments vs routine
SELECT proposal_id, LEFT(title, 60) AS title, status, start_date::DATE AS proposal_date
FROM main_silver.clean_tally_proposals
WHERE status IN ('defeated', 'succeeded', 'executed', 'queued', 'canceled')
ORDER BY start_date DESC LIMIT 20
""".strip(),
    },
    ("C4", "H2.3"): {
        "tables": ["main_silver.clean_tally_votes", "main_silver.clean_tally_proposals",
                   "main_silver.clean_token_distribution"],
        "key_columns": ["voter", "weight", "proposal_id", "balance"],
        "summary": "Tiers voters by weight percentile (Small <80th, Medium 80-95th, Large ≥95th). Compares supply share to voice share per tier. Runs counterfactual: removes small-holder votes from last 40 proposals, checks if outcomes change.",
        "sql": """
-- H2.3 — Supply vs Voice by tier
WITH threshold AS (
    SELECT PERCENTILE_CONT(0.80) WITHIN GROUP (ORDER BY weight) AS p80,
           PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY weight) AS p95
    FROM main_silver.clean_tally_votes
),
voter_tiers AS (
    SELECT voter, weight,
           CASE WHEN weight < t.p80 THEN 'Small'
                WHEN weight < t.p95 THEN 'Medium' ELSE 'Large' END AS tier
    FROM main_silver.clean_tally_votes v CROSS JOIN threshold t
)
SELECT tier, SUM(weight) AS weight_cast, COUNT(DISTINCT voter) AS voter_count
FROM voter_tiers GROUP BY tier ORDER BY tier
""".strip(),
    },
    ("C4", "Hx.1"): {
        "tables": ["main_silver.clean_tally_proposals"],
        "key_columns": ["voter", "weight", "proposal_id", "vote_choice", "winning_choice"],
        "summary": "Top-VP voter agreement rate with winning outcome (VP.1). Counterfactual removes top voter and checks if outcome flips (VP.2UP). Uses raw Tally votes JSON because on-chain vote weights need precise tracking.",
        "sql": """
-- Hx.1 — Outcome robustness (simplified: agreement rate per proposal)
SELECT p.proposal_id, LEFT(p.title, 60) AS title, p.status
FROM main_silver.clean_tally_proposals p
WHERE p.status IN ('executed', 'defeated')
ORDER BY p.start_date DESC LIMIT 20
""".strip(),
    },
    ("C4", "Hx.2"): {
        "tables": ["main_silver.clean_snapshot_votes", "main_silver.clean_snapshot_proposals",
                   "main_silver.clean_tally_votes", "main_silver.clean_tally_proposals",
                   "main_gold.delegate_scorecard"],
        "key_columns": ["voter", "proposal_id", "vote_choice"],
        "summary": "Combines top-50 delegates' Snapshot + Tally votes into a voter × proposal matrix. Computes cosine similarity, applies Ward hierarchical clustering to detect factions.",
        "sql": """
-- Hx.2 — Top-50 delegate vote history (combined Snapshot + Tally)
WITH top50 AS (
    SELECT address FROM main_gold.delegate_scorecard
    ORDER BY voting_power DESC LIMIT 50
)
SELECT sv.voter, sv.proposal_id, sv.vote_choice,
       sp.start_date::DATE AS proposal_date,
       LEFT(COALESCE(sp.title, sv.proposal_id), 60) AS proposal_title
FROM main_silver.clean_snapshot_votes sv
JOIN top50 ON sv.voter = top50.address
JOIN main_silver.clean_snapshot_proposals sp ON sv.proposal_id = sp.proposal_id
ORDER BY proposal_date DESC LIMIT 20
""".strip(),
    },
    ("C5", "H5.1"): {
        "tables": ["main_gold.treasury_summary", "main_silver.clean_ens_ledger"],
        "key_columns": ["period", "category", "inflows_usd", "outflows_usd", "net_usd",
                        "internal_transfer_usd", "source_entity", "destination", "value_usd"],
        "summary": "Monthly treasury cashflow (inflows/outflows/internal transfers) plus Sankey of source→destination ledger flows with $10K threshold for 'Other' bucket.",
        "sql": """
-- H5.1 — Monthly treasury cashflow overview
SELECT period, category, inflows_usd, outflows_usd, net_usd, internal_transfer_usd
FROM main_gold.treasury_summary ORDER BY period DESC LIMIT 12
""".strip(),
    },
    ("C5", "H5.2"): {
        "tables": ["main_silver.clean_ens_ledger"],
        "key_columns": ["tx_hash", "tx_date", "source_entity", "destination", "category",
                        "amount", "asset", "value_usd", "flow_type"],
        "summary": "Row-level ledger explorer — 2,316 transactions with multi-filter controls. No aggregation, pure filtering.",
        "sql": """
-- H5.2 — Ledger transactions (row-level)
SELECT tx_date::DATE AS date, source_entity, destination, category,
       asset, amount, value_usd, flow_type
FROM main_silver.clean_ens_ledger
ORDER BY tx_date DESC LIMIT 20
""".strip(),
    },
    ("C5", "H5.3"): {
        "tables": ["main_silver.clean_compensation"],
        "key_columns": ["recipient_address", "amount", "token", "value_usd",
                        "working_group", "role", "category", "date"],
        "summary": "Contributor compensation records (salaries, streams, fellowships, gas reimbursements) grouped by working group × role.",
        "sql": """
-- H5.3 — Compensation by working group × role
SELECT working_group, role, category,
       COUNT(*) AS n_payments,
       SUM(value_usd) AS total_usd,
       COUNT(DISTINCT recipient_address) AS unique_recipients
FROM main_silver.clean_compensation
GROUP BY working_group, role, category
ORDER BY total_usd DESC LIMIT 20
""".strip(),
    },
}


def run_sql(con: duckdb.DuckDBPyConnection, sql: str) -> str:
    """Run SQL and return top 10 rows as markdown. Return error string on failure."""
    try:
        df = con.execute(sql).fetchdf()
        if df.empty:
            return "_(query returned no rows)_"
        df = df.head(10)
        return df.to_markdown(index=False)
    except Exception as e:
        return f"_(SQL error: {e})_"


def main():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    if IMAGE_URLS_PATH.exists():
        image_urls = json.loads(IMAGE_URLS_PATH.read_text())
    else:
        image_urls = {}

    con = duckdb.connect(str(DB_PATH), read_only=True)

    out = []
    out.append("# ENS Retro — Dashboard Chart Catalog")
    out.append("")
    out.append(
        "Machine-readable catalog of every chart on the ENS Retrospective "
        "Dashboard (https://ensretro.metagov.org). Each entry includes: "
        "public screenshot URL, source warehouse tables, key columns, "
        "reproduction SQL, and a live sample of the underlying data. "
        "Designed for a ChatKit agent with read-only DuckDB MCP access "
        "to cite or reproduce any chart."
    )
    out.append("")
    out.append("**Warehouse connection:** `warehouse/ens_retro.duckdb` (read-only).  ")
    out.append("**Query tool:** `query_duckdb(sql)` — SELECT-only, 50-row cap.  ")
    out.append(f"**Vector store:** vs_69d291d5a5fc819194838e0475405ef7  ")
    out.append(f"**Images hosted:** https://ensretro-data.fra1.digitaloceanspaces.com/chart-catalog/")
    out.append("")
    out.append("---")
    out.append("")

    for ch in config["challenges"]:
        out.append(f"## {ch['id']} — {ch['title']}")
        out.append("")
        out.append((ch.get("description") or "").strip())
        out.append("")

        for h in ch["hypotheses"]:
            out.append(f"### {h['id']} — {h['title']}")
            out.append("")
            out.append(f"**Verdict:** `{h.get('verdict', 'n/a')}`")
            out.append("")

            # Screenshot URL
            slug = f"{ch['id']}_{h['id'].replace('.', '_')}"
            img_url = image_urls.get(slug)
            if img_url:
                out.append(f"**Screenshot:** {img_url}")
                out.append("")
                out.append(f"![{h['short_title']}]({img_url})")
                out.append("")

            # Description
            desc = (h.get("description") or "").strip()
            if desc:
                out.append("**Description:** " + desc)
                out.append("")

            # Chart specs
            spec = CHART_SPECS.get((ch["id"], h["id"]))
            if spec:
                if spec["tables"]:
                    out.append("**Source tables:** " + ", ".join(f"`{t}`" for t in spec["tables"]))
                    out.append("")
                if spec["key_columns"]:
                    out.append("**Key columns:** " + ", ".join(f"`{c}`" for c in spec["key_columns"]))
                    out.append("")
                out.append(f"**Transformation:** {spec['summary']}")
                out.append("")

                if spec["sql"]:
                    out.append("**Reproduction SQL:**")
                    out.append("")
                    out.append("```sql")
                    out.append(spec["sql"])
                    out.append("```")
                    out.append("")
                    out.append("**Sample output (top 10 rows, live from warehouse):**")
                    out.append("")
                    out.append(run_sql(con, spec["sql"]))
                    out.append("")

            # Visuals + takeaways
            for v in (h.get("visuals") or []):
                title = v.get("title", "")
                takeaway = (v.get("takeaway") or "").strip()
                if title:
                    out.append(f"**Chart: {title}**")
                    out.append("")
                if takeaway:
                    out.append(f"> **Key takeaway:** {takeaway}")
                    out.append("")

            out.append("---")
            out.append("")

    con.close()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text("\n".join(out))

    size_kb = CATALOG_PATH.stat().st_size / 1024
    print(f"Wrote {CATALOG_PATH} ({size_kb:.1f} KB, {len(out)} lines)")


if __name__ == "__main__":
    main()
