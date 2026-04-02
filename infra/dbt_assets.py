"""Dagster assets generated from dbt models (staging, silver, gold)."""

import json
from datetime import datetime, timezone
from pathlib import Path

from dagster_dbt import DbtCliResource, dbt_assets

from infra.dbt_project import EnsDbtTranslator, dbt_project

_BRONZE_ROOT = dbt_project.project_dir.parent.parent / "bronze"

# Staging models that depend on manually-placed or not-yet-fetched files.
# If the file is missing we exclude the model (and its dependents) rather
# than crashing the entire dbt run.
_OPTIONAL_SOURCES: dict[str, tuple[Path, str]] = {
    "stg_compensation":      (_BRONZE_ROOT / "financial" / "compensation.json",       "financial"),
    "stg_grants":            (_BRONZE_ROOT / "grants"    / "grants.json",             "grants"),
    "stg_delegate_profiles": (_BRONZE_ROOT / "interviews"/ "delegate_profiles.json",  "interviews"),
}


def _log_dbt_skip_warning(subdir: str, message: str) -> None:
    """Persist a dbt-skip warning into bronze/{subdir}/metadata.json if the file exists."""
    meta_path = _BRONZE_ROOT / subdir / "metadata.json"
    if not meta_path.exists():
        return
    with open(meta_path) as f:
        meta = json.load(f)
    meta.setdefault("warnings", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "ens_dbt_assets",
        "message": message,
    })
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=EnsDbtTranslator(),
)
def ens_dbt_assets(context, dbt: DbtCliResource):
    """Run dbt build for all staging, silver, and gold models."""
    (dbt_project.project_dir.parent.parent / "warehouse").mkdir(exist_ok=True)

    missing = [(m, p, s) for m, (p, s) in _OPTIONAL_SOURCES.items() if not p.exists()]
    if missing:
        for model, path, subdir in missing:
            msg = f"Skipping dbt model '{model}+' — source file not on disk: {path.name}"
            context.log.warning(msg)
            _log_dbt_skip_warning(subdir, msg)

    cmd = ["build"]
    for model, _path, _subdir in missing:
        cmd += ["--exclude", f"{model}+"]  # model + all its downstream dependents

    yield from dbt.cli(cmd, context=context).stream()
