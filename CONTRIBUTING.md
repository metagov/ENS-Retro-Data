# Contributing to ENS-Retro-Data

Thanks for considering a contribution. This project is an open research dataset and analysis platform, and we welcome improvements to the pipeline, dashboard, documentation, and the research methodology itself.

## Ways to contribute

- **Data pipeline** — add new sources, improve ingest reliability, extend dbt models
- **Dashboard** — add new visualizations, improve the challenge/hypothesis analyses, fix UI bugs
- **Research** — propose new challenges or hypotheses, challenge existing findings, replicate results
- **Documentation** — improve the README, add tutorials, clarify data provenance
- **Bug reports** — open an issue with a minimal reproduction

## Before you start

1. **Read the [README](README.md)** — especially the architecture section and the developer guide
2. **Check existing issues and PRs** to avoid duplicate work
3. **For anything non-trivial, open an issue first** to discuss the approach — it's cheaper to align before coding

## Development setup

See the [Developer Guide in README.md](README.md#developer-guide) for full setup. Short version:

```bash
git lfs install
git clone https://github.com/metagov/ENS-Retro-Data.git
cd ENS-Retro-Data
uv sync --extra dev
cd infra/dbt && uv run dbt deps && cd ../..
uv run python scripts/generate_taxonomy_seeds.py
```

## Branch & PR workflow

1. Create a feature branch from `main`: `git checkout -b fix/your-change` or `feat/your-change`
2. Make your changes in small, focused commits
3. Run tests locally (see below)
4. Push and open a PR against `main`
5. Request review; address feedback; merge after approval

### Commit message style

We follow conventional commits loosely:

```
type(scope): short imperative summary

Optional body explaining the why, not the what. Reference the file paths
that changed and any design decisions that aren't obvious from the diff.

Refs #123
```

Types we use: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `sec`, `perf`.

Scopes (examples): `api`, `mcp`, `dashboard`, `bronze`, `silver`, `gold`, `dbt`, `dagster`, `oss`, `chat`.

## Tests

**Before submitting a PR, run the relevant tests:**

```bash
# Dashboard + API tests (106 cases)
cd dashboards && uv run pytest tests/ -v

# Lint
uv run ruff check .

# Format check
uv run ruff format --check .
```

**For changes to `dashboards/api.py` or `scripts/` in the dashboards directory**, ensure `uv run pytest tests/test_api.py` passes.

**For changes to `infra/ingest/` or `infra/dbt/models/`**, ensure `dbt build` completes cleanly:

```bash
cd infra/dbt && uv run dbt build
```

**For changes to `taxonomy.yaml`**, regenerate the seed CSVs and re-run dbt seed:

```bash
uv run python scripts/generate_taxonomy_seeds.py
cd infra/dbt && uv run dbt seed
```

## Data contributions

Bronze data is **append-only and immutable**. If you need to add a new data source:

1. Create a new directory under `bronze/<category>/`
2. Add a `metadata.json` alongside the data files with schema hints, provenance, and expected record counts
3. Write an ingest module in `infra/ingest/` that emits Dagster assets
4. Add staging + silver dbt models that clean and type the data
5. Update the data-sources table in the README

Do **not** modify existing bronze files — if a source changes its schema, add a new file and update the ingest logic to handle both formats.

## Code style

- Python: `ruff` formatter, line length 100, `select = ["E", "F", "I", "W"]`
- SQL (dbt): snake_case, explicit column lists (no `SELECT *` in silver/gold)
- Tests: one assertion concept per test case, descriptive names, no mocks of the code under test

## Security

If you find a security issue (SQL injection, auth bypass, data leak, secret in code, etc.), please **do not open a public issue**. See [SECURITY.md](SECURITY.md) for disclosure instructions.

## Questions?

- For technical questions, open a GitHub Discussion (or issue if it feels like a bug)
- For research methodology questions, contact the maintainers directly
- For anything else: rashmi@daostar.org

## License

By contributing, you agree that your contributions will be licensed under the project's dual license: [MIT](LICENSE-CODE) for code and [CC BY 4.0](LICENSE-DATA) for data and research materials. See [LICENSE](LICENSE) for which files fall under which license.
