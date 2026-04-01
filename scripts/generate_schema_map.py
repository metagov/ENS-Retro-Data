#!/usr/bin/env python3
"""
Generate an interactive HTML schema map from the actual data files and dbt models.

Usage:
    python scripts/generate_schema_map.py
    # opens docs/schema-map.html

Reads:
    - bronze/**/*.{csv,json}   → headers, keys, record counts, file sizes
    - infra/dbt/models/**/*.yml → staging, silver, gold model definitions
    - infra/dbt/models/**/*.sql → SELECT columns from dbt models
    - infra/dbt/models/staging/_sources.yml → source-to-file mapping
    - taxonomy.yaml             → controlled vocabularies

Writes:
    - docs/schema-map.html
"""

from __future__ import annotations

import csv
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# ── Paths ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
BRONZE = ROOT / "bronze"
DBT = ROOT / "infra" / "dbt"
MODELS = DBT / "models"
OUT = ROOT / "docs" / "schema-map.html"


# ── Helpers ────────────────────────────────────────────────────────────────


def human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}" if unit != "B" else f"{nbytes} B"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def count_json_records(path: Path) -> int | None:
    """Count top-level array length without loading into memory."""
    try:
        with open(path) as f:
            first = f.read(2).strip()
        if first.startswith("["):
            # count by streaming – fast enough for <100MB
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                return len(data)
    except Exception:
        pass
    return None


def count_csv_rows(path: Path) -> int | None:
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f) - 1  # minus header
    except Exception:
        return None


def read_csv_headers(path: Path) -> list[str]:
    try:
        with open(path, newline="", errors="replace") as f:
            reader = csv.reader(f)
            return next(reader, [])
    except Exception:
        return []


def read_json_keys(path: Path) -> list[str]:
    """Read first record's keys from a JSON array file."""
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            return list(data[0].keys())
        if isinstance(data, dict):
            return list(data.keys())
    except Exception:
        pass
    return []


def parse_sql_columns(path: Path) -> list[str]:
    """Extract column names from a dbt SQL SELECT statement."""
    try:
        text = path.read_text()
    except Exception:
        return []
    # Remove jinja/comments
    text = re.sub(r"\{[%#].*?[%#]\}", "", text, flags=re.DOTALL)
    text = re.sub(r"--.*", "", text)

    # Find last SELECT ... FROM
    matches = list(re.finditer(r"(?i)\bSELECT\b(.*?)\bFROM\b", text, re.DOTALL))
    if not matches:
        return []
    select_body = matches[-1].group(1)

    cols = []
    for part in select_body.split(","):
        part = part.strip()
        if not part:
            continue
        # Handle "expr AS alias" or just "column_name"
        m = re.search(r"(?i)\bAS\s+(\w+)\s*$", part)
        if m:
            cols.append(m.group(1))
        else:
            # last word, skip functions
            tokens = re.findall(r"\w+", part)
            if tokens:
                cols.append(tokens[-1])
    return cols


def parse_python_model_columns(path: Path) -> list[str]:
    """Extract column names from Python dbt model string literals."""
    try:
        text = path.read_text()
    except Exception:
        return []
    # Look for column name patterns in DataFrame construction
    cols = re.findall(r"['\"](\w+)['\"]", text)
    # Filter to likely column names (lowercase, no Python keywords)
    skip = {
        "def", "return", "import", "from", "model", "dbt", "ref", "source",
        "config", "materialized", "table", "true", "false", "none", "self",
        "str", "int", "float", "bool", "list", "dict", "pd", "DataFrame",
        "np", "duckdb", "sql", "execute", "fetchdf", "fetchall", "cursor",
        "connection", "connect", "schema", "database", "relation", "this",
    }
    filtered = []
    seen = set()
    for c in cols:
        if c.lower() not in skip and c not in seen and not c.startswith("__"):
            seen.add(c)
            filtered.append(c)
    return filtered


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


# ── Scan bronze layer ──────────────────────────────────────────────────────


def scan_bronze() -> list[dict]:
    """Walk bronze/ and collect metadata for every data file."""
    entries = []
    if not BRONZE.exists():
        return entries

    for root, dirs, files in os.walk(BRONZE):
        dirs.sort()
        for fname in sorted(files):
            fpath = Path(root) / fname
            if fname.startswith(".") or fname == "metadata.json":
                continue

            rel = fpath.relative_to(BRONZE)
            domain = rel.parts[0] if len(rel.parts) > 1 else "root"
            subdomain = "/".join(rel.parts[1:-1]) if len(rel.parts) > 2 else ""
            ext = fpath.suffix.lower()
            size = fpath.stat().st_size

            entry = {
                "path": str(rel),
                "name": fname,
                "domain": domain,
                "subdomain": subdomain,
                "ext": ext,
                "size": size,
                "size_human": human_size(size),
                "fields": [],
                "records": None,
            }

            if ext == ".csv":
                entry["fields"] = read_csv_headers(fpath)
                entry["records"] = count_csv_rows(fpath)
            elif ext == ".json":
                entry["fields"] = read_json_keys(fpath)
                if size < 200_000_000:  # skip huge files
                    entry["records"] = count_json_records(fpath)

            entries.append(entry)

    return entries


# ── Scan dbt models ────────────────────────────────────────────────────────


def scan_dbt_layer(layer: str) -> list[dict]:
    """Scan dbt models for a layer (staging, silver, gold)."""
    layer_dir = MODELS / layer
    yml_path = layer_dir / f"_{layer}.yml"
    if layer == "staging":
        yml_path = layer_dir / "_staging.yml"

    yml = load_yaml(yml_path)
    models_meta = {}
    for m in yml.get("models", []):
        name = m.get("name", "")
        cols_from_yml = [c["name"] for c in m.get("columns", []) if "name" in c]
        tests = {}
        for c in m.get("columns", []):
            cname = c.get("name", "")
            ctests = []
            for t in c.get("tests", []):
                if isinstance(t, str):
                    ctests.append(t)
                elif isinstance(t, dict):
                    for k, v in t.items():
                        severity = ""
                        if isinstance(v, dict) and v.get("severity") == "warn":
                            severity = " (warn)"
                        ctests.append(f"{k}{severity}")
            if ctests:
                tests[cname] = ctests

        is_sentinel = any(
            isinstance(t, dict) and any(
                isinstance(v, dict) and v.get("severity") == "warn"
                for v in t.values()
            )
            for c in m.get("columns", [])
            for t in c.get("tests", [])
        )

        models_meta[name] = {
            "description": m.get("description", ""),
            "cols_yml": cols_from_yml,
            "tests": tests,
            "sentinel": is_sentinel,
        }

    entries = []
    for fpath in sorted(layer_dir.glob("*")):
        if fpath.name.startswith("_"):
            continue
        if fpath.suffix not in (".sql", ".py"):
            continue

        name = fpath.stem
        meta = models_meta.get(name, {})

        if fpath.suffix == ".sql":
            cols_sql = parse_sql_columns(fpath)
        else:
            cols_sql = parse_python_model_columns(fpath)

        # Prefer SQL-parsed columns, fallback to yml
        columns = cols_sql if cols_sql else meta.get("cols_yml", [])

        entries.append({
            "name": name,
            "file": fpath.name,
            "ext": fpath.suffix,
            "description": meta.get("description", ""),
            "columns": columns,
            "tests": meta.get("tests", {}),
            "sentinel": meta.get("sentinel", False),
        })

    return entries


# ── Scan sources ───────────────────────────────────────────────────────────


def scan_sources() -> dict[str, dict]:
    """Parse _sources.yml to map source tables to bronze files."""
    sources_yml = load_yaml(MODELS / "staging" / "_sources.yml")
    mapping = {}
    for src in sources_yml.get("sources", []):
        src_name = src.get("name", "")
        for tbl in src.get("tables", []):
            tbl_name = tbl.get("name", "")
            loc = tbl.get("meta", {}).get("external_location", "")
            # Extract file path from read_json_auto('...') or read_csv_auto('...')
            m = re.search(r"'([^']+)'", loc)
            file_path = m.group(1) if m else ""
            mapping[tbl_name] = {
                "source": src_name,
                "description": tbl.get("description", ""),
                "file": file_path,
            }
    return mapping


# ── HTML Generation ────────────────────────────────────────────────────────

H = html.escape


def render_badge(text: str, cls: str) -> str:
    return f'<span class="badge badge-{cls}">{H(text)}</span>'


def render_field(name: str, is_key: bool = False, is_new: bool = False) -> str:
    cls = "key" if is_key else ("new-field" if is_new else "")
    return f'<span class="field {cls}">{H(name)}</span>'


def render_fields(fields: list[str], keys: set[str] | None = None) -> str:
    if not fields:
        return '<span class="file-meta">No fields detected</span>'
    keys = keys or set()
    parts = [render_field(f, f in keys) for f in fields]
    return '<div class="fields">' + "".join(parts) + "</div>"


def render_bronze_file(entry: dict) -> str:
    ext_badge = "csv" if entry["ext"] == ".csv" else "json"
    badges = render_badge(entry["ext"].lstrip(".").upper(), ext_badge)
    if entry["records"] is not None:
        badges += " " + render_badge(f'{entry["records"]:,} records', "count")
    if entry["size"] > 50_000_000:
        badges += " " + render_badge(f'LFS {entry["size_human"]}', "lfs")

    search_data = " ".join([entry["name"]] + entry["fields"]).lower()

    return f"""
    <div class="file" data-search="{H(search_data)}">
      <div class="file-name">{H(entry["name"])} {badges}</div>
      <div class="file-meta">{H(entry["path"])}</div>
      {render_fields(entry["fields"])}
    </div>"""


def render_model(entry: dict, layer: str) -> str:
    ext_badge = "py" if entry["ext"] == ".py" else "sql"
    badges = render_badge(entry["ext"].lstrip(".").upper(), ext_badge)
    if entry["sentinel"]:
        badges += " " + render_badge("SENTINEL", "sentinel")

    css_class = "sentinel" if entry["sentinel"] else ""
    search_data = " ".join([entry["name"]] + entry["columns"]).lower()

    test_info = ""
    if entry["tests"]:
        test_parts = []
        for col, tests in entry["tests"].items():
            test_parts.append(f"{col}: {', '.join(tests)}")
        test_info = f'<div class="file-meta" style="margin-top:0.3rem">Tests: {H("; ".join(test_parts))}</div>'

    return f"""
    <div class="file {css_class}" data-search="{H(search_data)}">
      <div class="file-name">{H(entry["name"])} {badges}</div>
      <div class="file-meta">{H(entry["description"])}</div>
      {render_fields(entry["columns"])}
      {test_info}
    </div>"""


def group_bronze_by_domain(entries: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for e in entries:
        key = e["domain"]
        groups.setdefault(key, []).append(e)
    return groups


def generate_html(
    bronze_files: list[dict],
    staging_models: list[dict],
    silver_models: list[dict],
    gold_models: list[dict],
    sources: dict[str, dict],
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Stats
    n_bronze = len(bronze_files)
    n_staging = len(staging_models)
    n_silver = len(silver_models)
    n_gold = len(gold_models)
    n_sentinel = sum(1 for m in silver_models if m["sentinel"])
    n_active_silver = n_silver - n_sentinel

    # Group bronze
    bronze_groups = group_bronze_by_domain(bronze_files)

    # Build bronze HTML
    bronze_html = ""
    for domain in sorted(bronze_groups.keys()):
        files = bronze_groups[domain]
        # Subgroup by subdomain
        subgroups: dict[str, list[dict]] = {}
        for f in files:
            key = f["subdomain"] or "(root)"
            subgroups.setdefault(key, []).append(f)

        domain_body = ""
        for sub, subfiles in sorted(subgroups.items()):
            if sub != "(root)":
                file_html = "".join(render_bronze_file(f) for f in subfiles)
                domain_body += f"""
                <div class="domain">
                  <div class="domain-header" onclick="toggleDomain(this)"><span class="arrow">&#9660;</span> {H(sub)}</div>
                  <div class="domain-body">{file_html}</div>
                </div>"""
            else:
                domain_body += "".join(render_bronze_file(f) for f in subfiles)

        bronze_html += f"""
        <div class="layer">
          <div class="layer-header bronze" onclick="toggleLayer(this)">
            <span class="arrow">&#9660;</span> BRONZE &mdash; {H(domain)}/
            <span style="margin-left:auto;font-size:0.75rem;opacity:0.6">{len(files)} files</span>
          </div>
          <div class="layer-body">{domain_body}</div>
        </div>"""

    # Build staging HTML
    staging_html = ""
    for m in staging_models:
        staging_html += render_model(m, "staging")

    # Build silver HTML
    silver_active_html = ""
    silver_sentinel_html = ""
    for m in silver_models:
        if m["sentinel"]:
            silver_sentinel_html += render_model(m, "silver")
        else:
            silver_active_html += render_model(m, "silver")

    # Build gold HTML
    gold_html = ""
    for m in gold_models:
        gold_html += render_model(m, "gold")

    # Sources lineage
    lineage_rows = ""
    for tbl_name, info in sorted(sources.items()):
        lineage_rows += f"""
        <tr>
          <td>{H(info['source'])}</td>
          <td>{H(tbl_name)}</td>
          <td>{H(info['file'])}</td>
          <td>{H(info['description'])}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ENS Retro Data &mdash; Schema Map</title>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #c9d1d9; --text-dim: #8b949e;
    --accent-blue: #58a6ff; --accent-green: #3fb950;
    --accent-orange: #d29922; --accent-red: #f85149;
    --accent-purple: #bc8cff;
    --bronze: #cd7f32; --silver: #a0aec0; --gold: #ffd700;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: 'SF Mono','Cascadia Code','Fira Code',monospace;
    background: var(--bg); color: var(--text);
    line-height: 1.6; padding: 2rem;
  }}
  h1 {{ font-size:1.5rem; color:#fff; margin-bottom:0.3rem; }}
  .subtitle {{ color:var(--text-dim); font-size:0.82rem; margin-bottom:1.5rem; }}
  .tabs {{ display:flex; gap:0; border-bottom:1px solid var(--border); margin-bottom:1.5rem; }}
  .tab {{
    padding:0.5rem 1rem; cursor:pointer; color:var(--text-dim);
    border:1px solid transparent; border-bottom:none;
    border-radius:6px 6px 0 0; font-family:inherit; font-size:0.82rem;
    background:none; transition:all 0.15s;
  }}
  .tab:hover {{ color:var(--text); }}
  .tab.active {{
    color:#fff; background:var(--surface);
    border-color:var(--border); border-bottom:1px solid var(--surface);
    margin-bottom:-1px;
  }}
  .tab-content {{ display:none; }}
  .tab-content.active {{ display:block; }}
  .layer {{
    border:1px solid var(--border); border-radius:8px;
    margin-bottom:1.2rem; overflow:hidden;
  }}
  .layer-header {{
    padding:0.7rem 1rem; font-weight:600; font-size:0.9rem;
    display:flex; align-items:center; gap:0.5rem;
    cursor:pointer; user-select:none;
  }}
  .layer-header .arrow {{ transition:transform 0.2s; font-size:0.65rem; color:var(--text-dim); }}
  .layer-header.collapsed .arrow {{ transform:rotate(-90deg); }}
  .layer-header.bronze {{ background:rgba(205,127,50,0.12); color:var(--bronze); }}
  .layer-header.silver {{ background:rgba(160,174,192,0.12); color:var(--silver); }}
  .layer-header.gold {{ background:rgba(255,215,0,0.12); color:var(--gold); }}
  .layer-header.staging {{ background:rgba(188,140,255,0.12); color:var(--accent-purple); }}
  .layer-body {{ padding:0 1rem 1rem; }}
  .layer-header.collapsed + .layer-body {{ display:none; }}
  .domain {{
    margin-top:0.8rem; border:1px solid var(--border);
    border-radius:6px; overflow:hidden;
  }}
  .domain-header {{
    padding:0.4rem 0.7rem; background:rgba(255,255,255,0.03);
    font-weight:600; font-size:0.78rem; color:var(--accent-blue);
    cursor:pointer; display:flex; align-items:center; gap:0.4rem;
  }}
  .domain-header .arrow {{ transition:transform 0.2s; font-size:0.55rem; color:var(--text-dim); }}
  .domain-header.collapsed .arrow {{ transform:rotate(-90deg); }}
  .domain-header.collapsed + .domain-body {{ display:none; }}
  .domain-body {{ padding:0.4rem 0.7rem; }}
  .file {{
    margin:0.5rem 0; padding:0.5rem;
    background:rgba(255,255,255,0.02); border-radius:4px;
    border-left:3px solid var(--border);
  }}
  .file.sentinel {{ border-left-color:var(--accent-orange); }}
  .file-name {{
    font-weight:600; font-size:0.78rem; color:#fff;
    display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap;
  }}
  .badge {{
    font-size:0.62rem; padding:0.1rem 0.35rem;
    border-radius:3px; font-weight:400;
  }}
  .badge-json {{ background:rgba(88,166,255,0.15); color:var(--accent-blue); }}
  .badge-csv {{ background:rgba(63,185,80,0.15); color:var(--accent-green); }}
  .badge-sql {{ background:rgba(188,140,255,0.15); color:var(--accent-purple); }}
  .badge-py {{ background:rgba(210,153,34,0.15); color:var(--accent-orange); }}
  .badge-count {{ background:rgba(255,255,255,0.08); color:var(--text-dim); }}
  .badge-lfs {{ background:rgba(248,81,73,0.15); color:var(--accent-red); }}
  .badge-sentinel {{ background:rgba(210,153,34,0.2); color:var(--accent-orange); }}
  .file-meta {{ font-size:0.72rem; color:var(--text-dim); margin-top:0.15rem; }}
  .fields {{
    margin-top:0.3rem; font-size:0.72rem;
    display:flex; flex-wrap:wrap; gap:0.25rem;
  }}
  .field {{
    background:rgba(255,255,255,0.06); padding:0.1rem 0.35rem;
    border-radius:3px; white-space:nowrap;
  }}
  .field.key {{ background:rgba(88,166,255,0.15); color:var(--accent-blue); }}
  .field.new-field {{ background:rgba(63,185,80,0.15); color:var(--accent-green); }}
  .comparison {{
    width:100%; border-collapse:collapse; font-size:0.75rem; margin-top:0.8rem;
  }}
  .comparison th, .comparison td {{
    padding:0.4rem 0.6rem; border:1px solid var(--border);
    text-align:left; vertical-align:top;
  }}
  .comparison th {{
    background:rgba(255,255,255,0.04); color:var(--accent-blue);
    font-weight:600; position:sticky; top:0;
  }}
  .comparison tr:hover td {{ background:rgba(255,255,255,0.02); }}
  .stats {{ display:flex; gap:1.2rem; flex-wrap:wrap; margin-bottom:1.5rem; }}
  .stat {{
    background:var(--surface); border:1px solid var(--border);
    border-radius:6px; padding:0.7rem 1rem; min-width:120px;
  }}
  .stat-value {{ font-size:1.3rem; font-weight:700; color:#fff; }}
  .stat-label {{ font-size:0.68rem; color:var(--text-dim); margin-top:0.1rem; }}
  .note {{
    background:rgba(210,153,34,0.1); border:1px solid rgba(210,153,34,0.3);
    border-radius:6px; padding:0.6rem 0.8rem; font-size:0.75rem;
    color:var(--accent-orange); margin:0.8rem 0;
  }}
  .note.info {{
    background:rgba(88,166,255,0.08); border-color:rgba(88,166,255,0.25);
    color:var(--accent-blue);
  }}
  .search-box {{
    width:100%; padding:0.5rem 0.8rem; background:var(--surface);
    border:1px solid var(--border); border-radius:6px;
    color:var(--text); font-family:inherit; font-size:0.82rem;
    margin-bottom:1.2rem; outline:none;
  }}
  .search-box:focus {{ border-color:var(--accent-blue); }}
  .search-box::placeholder {{ color:var(--text-dim); }}
  .hidden {{ display:none !important; }}
  .section-title {{
    font-size:0.95rem; color:#fff; margin:1.5rem 0 0.4rem;
    padding-bottom:0.2rem; border-bottom:1px solid var(--border);
  }}
</style>
</head>
<body>

<h1>ENS Retro Data &mdash; Schema Map</h1>
<p class="subtitle">Auto-generated {H(now)} &nbsp;|&nbsp; Run <code>python scripts/generate_schema_map.py</code> to refresh</p>

<div class="stats">
  <div class="stat"><div class="stat-value" style="color:var(--bronze)">{n_bronze}</div><div class="stat-label">Bronze Files</div></div>
  <div class="stat"><div class="stat-value" style="color:var(--accent-purple)">{n_staging}</div><div class="stat-label">Staging Models</div></div>
  <div class="stat"><div class="stat-value" style="color:var(--silver)">{n_silver}</div><div class="stat-label">Silver Models</div></div>
  <div class="stat"><div class="stat-value" style="color:var(--gold)">{n_gold}</div><div class="stat-label">Gold Models</div></div>
  <div class="stat"><div class="stat-value" style="color:var(--accent-green)">{n_active_silver}</div><div class="stat-label">Active Silver</div></div>
  <div class="stat"><div class="stat-value" style="color:var(--accent-orange)">{n_sentinel}</div><div class="stat-label">Sentinel</div></div>
</div>

<div class="tabs">
  <button class="tab active" onclick="switchTab('bronze')">Bronze (Raw)</button>
  <button class="tab" onclick="switchTab('staging')">Staging (Views)</button>
  <button class="tab" onclick="switchTab('silver')">Silver (Clean)</button>
  <button class="tab" onclick="switchTab('gold')">Gold (Analysis)</button>
  <button class="tab" onclick="switchTab('lineage')">Lineage</button>
</div>

<!-- BRONZE -->
<div id="tab-bronze" class="tab-content active">
  <input type="text" class="search-box" placeholder="Search fields, files, domains..."
         oninput="searchFiles(this.value, 'tab-bronze')">
  {bronze_html}
</div>

<!-- STAGING -->
<div id="tab-staging" class="tab-content">
  <input type="text" class="search-box" placeholder="Search models, columns..."
         oninput="searchFiles(this.value, 'tab-staging')">
  <div class="layer">
    <div class="layer-header staging" onclick="toggleLayer(this)">
      <span class="arrow">&#9660;</span> STAGING &mdash; column renames + type casts
      <span style="margin-left:auto;font-size:0.75rem;opacity:0.6">{n_staging} models</span>
    </div>
    <div class="layer-body">
      <div class="note info">Staging models are views that normalize column names and apply basic type casts from bronze sources.</div>
      {staging_html}
    </div>
  </div>
</div>

<!-- SILVER -->
<div id="tab-silver" class="tab-content">
  <input type="text" class="search-box" placeholder="Search models, columns..."
         oninput="searchFiles(this.value, 'tab-silver')">
  <div class="layer">
    <div class="layer-header silver" onclick="toggleLayer(this)">
      <span class="arrow">&#9660;</span> SILVER &mdash; Active Models
      <span style="margin-left:auto;font-size:0.75rem;opacity:0.6">{n_active_silver} models</span>
    </div>
    <div class="layer-body">
      <div class="note info">Transforms: lowercase addresses, wei&rarr;ETH, unix&rarr;timestamp, vote choice mapping, deduplication</div>
      {silver_active_html}
    </div>
  </div>
  <div class="layer">
    <div class="layer-header silver" onclick="toggleLayer(this)">
      <span class="arrow">&#9660;</span> SILVER &mdash; Sentinel Models (placeholders)
      <span style="margin-left:auto;font-size:0.75rem;opacity:0.6">{n_sentinel} models</span>
    </div>
    <div class="layer-body">
      <div class="note">Sentinel models have warn-level tests. Waiting for bronze data collection.</div>
      {silver_sentinel_html}
    </div>
  </div>
</div>

<!-- GOLD -->
<div id="tab-gold" class="tab-content">
  <div class="layer">
    <div class="layer-header gold" onclick="toggleLayer(this)">
      <span class="arrow">&#9660;</span> GOLD &mdash; Analysis-Ready
      <span style="margin-left:auto;font-size:0.75rem;opacity:0.6">{n_gold} models</span>
    </div>
    <div class="layer-body">
      <div class="note info">Materialized as tables in DuckDB &mdash; warehouse/ens_retro.duckdb</div>
      {gold_html}
    </div>
  </div>
</div>

<!-- LINEAGE -->
<div id="tab-lineage" class="tab-content">
  <h2 class="section-title">Source &rarr; Bronze File Mapping</h2>
  <table class="comparison">
    <thead><tr><th>Source Group</th><th>Table Name</th><th>Bronze File</th><th>Description</th></tr></thead>
    <tbody>{lineage_rows}</tbody>
  </table>
</div>

<script>
function switchTab(id) {{
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  event.target.classList.add('active');
}}
function toggleLayer(el) {{ el.classList.toggle('collapsed'); }}
function toggleDomain(el) {{ el.classList.toggle('collapsed'); }}
function searchFiles(query, tabId) {{
  const tab = document.getElementById(tabId);
  const files = tab.querySelectorAll('.file');
  const q = query.toLowerCase();
  files.forEach(f => {{
    const search = (f.getAttribute('data-search') || '') + ' ' + f.textContent;
    f.classList.toggle('hidden', q.length > 0 && !search.toLowerCase().includes(q));
  }});
}}
</script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    print("Scanning bronze files...")
    bronze_files = scan_bronze()
    print(f"  Found {len(bronze_files)} data files")

    print("Scanning dbt models...")
    staging_models = scan_dbt_layer("staging")
    silver_models = scan_dbt_layer("silver")
    gold_models = scan_dbt_layer("gold")
    print(f"  Staging: {len(staging_models)}, Silver: {len(silver_models)}, Gold: {len(gold_models)}")

    print("Parsing source mappings...")
    sources = scan_sources()
    print(f"  Found {len(sources)} source tables")

    print("Generating HTML...")
    html_content = generate_html(bronze_files, staging_models, silver_models, gold_models, sources)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html_content)
    print(f"Written to {OUT}")
    print(f"Open: file://{OUT}")


if __name__ == "__main__":
    main()
