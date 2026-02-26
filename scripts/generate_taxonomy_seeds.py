#!/usr/bin/env python3
"""Generate dbt seed CSVs from taxonomy.yaml.

Reads the single source of truth (taxonomy.yaml) and writes one CSV
per vocabulary into dbt/seeds/ for use in dbt tests and reference joins.
"""

import csv
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = PROJECT_ROOT / "taxonomy.yaml"
SEEDS_DIR = PROJECT_ROOT / "infra" / "dbt" / "seeds"

# Map taxonomy keys to seed filenames and column names
SEED_MAPPINGS = {
    "proposal_status": {
        "filename": "taxonomy_proposal_status.csv",
        "column": "status",
    },
    "vote_choices": {
        "filename": "taxonomy_vote_choices.csv",
        "column": "choice",
    },
    "sources": {
        "filename": "taxonomy_sources.csv",
        "column": "source",
    },
    "stakeholder_roles": {
        "filename": "taxonomy_stakeholder_roles.csv",
        "column": "role",
    },
    "working_groups": {
        "filename": "taxonomy_working_groups.csv",
        "column": "working_group",
    },
}


def main():
    with open(TAXONOMY_PATH) as f:
        taxonomy = yaml.safe_load(f)

    SEEDS_DIR.mkdir(parents=True, exist_ok=True)

    for key, mapping in SEED_MAPPINGS.items():
        values = taxonomy.get(key, [])
        output_path = SEEDS_DIR / mapping["filename"]
        col_name = mapping["column"]

        with open(output_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([col_name])
            for val in values:
                writer.writerow([val])

        print(f"  Wrote {output_path.name} ({len(values)} rows)")

    print("Done.")


if __name__ == "__main__":
    main()
