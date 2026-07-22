# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

`wd-squads` compares football club squads on **Wikipedia** against *member of
sports team* (P54) membership statements on **Wikidata**, and generates a
prioritised TODO list of suggested Wikidata edits (missing memberships, missing
start/end dates, players that appear to have left, etc.). It runs unattended via
GitHub Actions on a weekly schedule and commits refreshed reports plus an HTML
dashboard.

The suggestions are heuristics — the tool never edits Wikidata itself, it only
produces a list for a human to review.

## Commands

The repo ships both a `requirements*.txt` / pip workflow (documented in the
README) and a `uv.lock` + `pyproject.toml`. **CI uses `uv`**; prefer it locally
for parity.

```bash
# Run the tests (offline; no network needed)
uv run --extra dev pytest -q          # matches CI
python -m pytest                      # if deps installed via pip

# Run a single test file / test
uv run --extra dev pytest tests/test_wikipedia_parse.py
uv run --extra dev pytest tests/test_diff.py::test_add_membership -q

# Full pipeline run (hits query.wikidata.org and <lang>.wikipedia.org)
python -m wd_squads --config config/teams.yaml

# Fast iteration: process only the first team, with debug logging
python -m wd_squads --config config/teams.yaml --limit 1 --verbose
```

There is **no linter or formatter configured** — do not invent one. `.gitignore`
lists `.ruff_cache`/`.mypy_cache` but neither tool is set up.

## Architecture

The pipeline is a straight line, wired together in `app.py::run` →
`app.py::process`:

```
config.load_config → WikidataClient.discover_teams → for each team:
    WikipediaClient.get_squad  (parse wikitext + resolve player Q-IDs)
    WikidataClient.get_memberships  (P54 statements)
    diff.compute_suggestions   → list[Suggestion]
report.write_reports → reports/*.md + docs/index.html + docs/data.json
```

Module responsibilities (`src/wd_squads/`):

- **`models.py`** — the shared dataclasses (`Team`, `SquadPlayer`, `Membership`,
  `Suggestion`) and, crucially, the **suggestion taxonomy**: `KIND_*` constants,
  their `PRIORITY` sort weights (lower = more urgent), and `KIND_LABEL` human
  strings. Adding a new kind of suggestion means touching all three maps here
  plus `diff.py`.
- **`config.py`** — loads/validates `config/teams.yaml`. Enforces that a
  descriptive `user_agent` is set (rejects `example.com` placeholders) because
  the Wikimedia APIs require it, and that at least one of `leagues` /
  `discovery_query` / `teams` is present.
- **`http_client.py`** — the single shared HTTP layer. Sets the required
  User-Agent, throttles to `request_delay` seconds between requests, and retries
  429/5xx with exponential backoff. All network access goes through this; the
  Wikidata and Wikipedia clients are constructed with one shared instance.
- **`wikidata.py`** — SPARQL against WDQS. `discover_teams` picks its source in
  priority order: explicit `teams:` → `discovery_query:` → per-league P118
  queries. `get_memberships` returns **both open and closed** P54 statements so
  the diff can distinguish "add end date" from "review a closed membership".
- **`wikipedia.py`** — `parse_squad_players(wikitext)` is a **pure function and
  the heart of the tool** (directly unit-tested). It auto-detects two squad
  formats per section: English-style `{{fs player}}` templates and German-style
  `{{PersonZelle}}` table cells. Two regexes gate what counts as a current
  squad: `EXCLUDE_HEADING_RE` drops former-players/staff/transfer sections, and
  `SQUAD_HEADING_RE` (Kader/Aufgebot) is a *positive* gate applied **only** to
  the German `{{PersonZelle}}` format, which also appears in unrelated tables.
  `WikipediaClient` then resolves article titles → Q-IDs via the Action API
  (batched, following redirects/normalisation).
- **`diff.py`** — `compute_suggestions` is the pure comparison logic. It walks
  the Wikipedia squad checking each player against Wikidata (missing item,
  missing membership, missing start date, ended-but-still-listed), then walks
  Wikidata's open memberships for players Wikipedia dropped (add end date).
  Results are sorted by `priority` then player name.
- **`report.py`** — renders three outputs from the same `TeamResult` list:
  per-team Markdown (`reports/<Qid>-<slug>.md`), an index (`reports/README.md`),
  a JSON dump (`docs/data.json`), and a self-contained HTML dashboard
  (`docs/index.html`) built from an inline Jinja2 template `_HTML_TEMPLATE`.
- **`app.py`** / **`__main__.py`** — orchestration and the `python -m wd_squads`
  CLI. `process` deliberately catches per-team exceptions and records them on
  `TeamResult.error` so one broken team never aborts the whole run.

### Per-league language

A key design point: each league in `config/teams.yaml` can set its own
`language:` (falling back to the top-level default). Squads are read from the
Wikipedia edition that best maintains that league (e.g. Swiss/German clubs from
`de`, English clubs from `en`). This language flows through `Team.language` into
squad fetching, Q-ID resolution, and the report links.

## Conventions

- **Pure vs. network code is kept separate on purpose.** `parse_squad_players`
  and `compute_suggestions` take plain data and are the only things unit tests
  exercise (see `tests/`, which use `tests/fixtures/*.wikitext`, no mocking of
  HTTP). Keep new parsing/diff logic pure and testable the same way.
- Tests import `wd_squads` without installing the package: `tests/conftest.py`
  prepends `src/` to `sys.path` and exposes a `FIXTURES` path.
- `from __future__ import annotations` is used throughout; dataclasses with
  `Optional` fields are the norm.

## Generated files

`reports/*.md`, `docs/index.html` and `docs/data.json` are **build artifacts**
produced by a pipeline run (and by the `Update squad TODO` GitHub Action). Do
not hand-edit them; regenerate them by running the tool. They are committed to
the repo so the Markdown diffs are reviewable in git history and Pages can serve
`docs/`.

## GitHub Actions

- `tests.yml` — runs `uv run --extra dev pytest -q` on every push/PR.
- `update.yml` — weekly (Mon 06:00 UTC) + manual; runs the pipeline and commits
  `reports/` and `docs/` back to the repo (`contents: write`).
- `pages.yml` — deploys `docs/` to GitHub Pages, chained off `update.yml`'s
  completion (a `GITHUB_TOKEN` push does not itself fire a `push` event).
