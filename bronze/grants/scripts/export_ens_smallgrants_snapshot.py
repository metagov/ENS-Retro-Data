import requests
import csv
import time
import json
from datetime import datetime, timezone

API_URL = "https://hub.snapshot.org/graphql"
SPACE = "small-grants.eth"


def run_query(query):
    """Execute a GraphQL query with rate-limit retry."""
    resp = requests.post(API_URL, json={"query": query}, timeout=30)
    if resp.status_code == 429:
        print("  Rate limited – waiting 60 s …")
        time.sleep(60)
        return run_query(query)
    resp.raise_for_status()
    return resp.json()


def fetch_proposals():
    all_proposals = []
    skip = 0
    batch = 100

    while True:
        query = f"""
        {{
          proposals(
            first: {batch},
            skip: {skip},
            where: {{ space_in: ["{SPACE}"] }},
            orderBy: "created",
            orderDirection: desc
          ) {{
            id
            title
            body
            choices
            start
            end
            snapshot
            state
            author
            created
            scores
            scores_total
            scores_updated
            votes
            quorum
            type
            space {{ id name }}
          }}
        }}
        """
        data = run_query(query)["data"]["proposals"]
        if not data:
            break
        all_proposals.extend(data)
        print(f"  Fetched {len(all_proposals)} proposals so far")
        if len(data) < batch:
            break
        skip += batch
        time.sleep(1)

    return all_proposals


def fetch_votes(proposal_id):
    all_votes = []
    skip = 0
    batch = 1000

    while True:
        query = f"""
        {{
          votes(
            first: {batch},
            skip: {skip},
            where: {{ proposal: "{proposal_id}" }},
            orderBy: "created",
            orderDirection: desc
          ) {{
            id
            voter
            vp
            vp_by_strategy
            created
            choice
            reason
          }}
        }}
        """
        data = run_query(query)["data"]["votes"]
        if not data:
            break
        all_votes.extend(data)
        if len(data) < batch:
            break
        skip += batch
        time.sleep(1)

    return all_votes


def resolve_choice(choice_raw, choices):
    """Map 1-indexed choice value(s) to human-readable labels."""
    if isinstance(choice_raw, int):
        return choices[choice_raw - 1] if choice_raw <= len(choices) else str(choice_raw)
    if isinstance(choice_raw, dict):
        return json.dumps(
            {choices[int(k) - 1] if int(k) <= len(choices) else k: v for k, v in choice_raw.items()}
        )
    if isinstance(choice_raw, list):
        return json.dumps(
            [choices[c - 1] if c <= len(choices) else str(c) for c in choice_raw]
        )
    return str(choice_raw)


def ts_to_iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def main():
    print("Fetching ENS Small Grants proposals …")
    proposals = fetch_proposals()
    print(f"Total proposals: {len(proposals)}\n")

    # ── Proposals CSV ──────────────────────────────────────────────
    with open("ens_smallgrants_proposals.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "proposal_id", "title", "author", "state", "type",
            "created", "start", "end", "snapshot_block",
            "choices", "scores", "scores_total",
            "votes_count", "quorum", "body",
        ])
        for p in proposals:
            w.writerow([
                p["id"],
                p["title"],
                p["author"],
                p["state"],
                p.get("type", ""),
                ts_to_iso(p["created"]),
                ts_to_iso(p["start"]),
                ts_to_iso(p["end"]),
                p["snapshot"],
                json.dumps(p["choices"]),
                json.dumps(p["scores"]),
                p["scores_total"],
                p["votes"],
                p.get("quorum", ""),
                p["body"],
            ])
    print("Saved ens_smallgrants_proposals.csv")

    # ── Votes CSV ──────────────────────────────────────────────────
    with open("ens_smallgrants_votes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "proposal_id", "proposal_title", "voter",
            "choice_index", "choice_label", "voting_power",
            "reason", "created",
        ])

        for i, p in enumerate(proposals, 1):
            print(f"[{i}/{len(proposals)}] Fetching votes for: {p['title'][:70]}")
            votes = fetch_votes(p["id"])
            choices = p["choices"]

            for v in votes:
                w.writerow([
                    p["id"],
                    p["title"],
                    v["voter"],
                    json.dumps(v["choice"]),
                    resolve_choice(v["choice"], choices),
                    v["vp"],
                    v.get("reason", ""),
                    ts_to_iso(v["created"]),
                ])

            time.sleep(1)

    print("Saved ens_smallgrants_votes.csv")
    print("Done!")


if __name__ == "__main__":
    main()
