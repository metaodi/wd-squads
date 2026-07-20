# wd-squads

**A TODO list for Wikidata users, generated from Wikipedia football squads.**

Football clubs' squads are kept nicely up to date on Wikipedia, but the matching
membership data on **Wikidata** often lags behind: players change clubs without
anyone adding a *member of sports team* ([P54](https://www.wikidata.org/wiki/Property:P54))
statement, and — most annoyingly — memberships are frequently missing the
**start date** ([P580](https://www.wikidata.org/wiki/Property:P580)) and
**end date** ([P582](https://www.wikidata.org/wiki/Property:P582)) qualifiers.
Without those dates it is very hard to query "who plays for club X *right now*".

`wd-squads` compares the two projects and produces a prioritised **list of
suggested Wikidata edits** — a TODO list you can work through by hand.

It is written in Python and designed to run unattended via **GitHub Actions**,
committing a refreshed report and a browsable HTML dashboard on a schedule.

> ⚠️ The suggestions are heuristics based on how well Wikipedia and Wikidata
> happen to be maintained. **Always verify each one before editing Wikidata.**

## What it checks

For every club it discovers, it reads the *current squad* from the club's
English Wikipedia article (the `{{fs player}}` / `{{football squad player}}`
templates) and the P54 statements from Wikidata, then reports:

| Suggestion | Meaning |
| --- | --- |
| **Membership marked ended, but player is in the current squad** | Wikidata has an end date (P582) set, yet Wikipedia still lists the player. They may have returned, or the end date is wrong. |
| **In current squad, but no membership statement on Wikidata** | The player is in the squad but has no P54 statement pointing at the club — add one. |
| **Recorded as a current member, but no longer in the squad** | Wikidata says the player is current (open P54, no end date), but Wikipedia dropped them — they probably left; add an end date (P582). |
| **Current member, but the membership has no start date** | Open P54 statement without a P580 start date — add the start date so "current squad" queries work. |
| **In current squad, but the Wikipedia article has no Wikidata item** | The Wikipedia article isn't linked to a Wikidata item (or the player has no item yet). |

## How it works

```
Wikidata (SPARQL)                 Wikipedia (Action API)
  discover clubs in a league  ─┐   fetch the club article's wikitext
  fetch P54 memberships        │   parse {{fs player}} squad templates
                               │   resolve player articles → Q-IDs
                               ▼
                         diff  ──►  suggestions  ──►  reports/  +  docs/
```

- `src/wd_squads/wikidata.py` — SPARQL queries (team discovery + memberships).
- `src/wd_squads/wikipedia.py` — squad parsing (`parse_squad_players`) and Q-ID resolution.
- `src/wd_squads/diff.py` — turns the two views into `Suggestion` objects.
- `src/wd_squads/report.py` — writes Markdown, JSON and the HTML dashboard.
- `src/wd_squads/app.py` / `__main__.py` — orchestration and CLI.

## Configuration

Edit [`config/teams.yaml`](config/teams.yaml). Teams are discovered with
**SPARQL auto-discovery** from the leagues you list (by Wikidata Q-ID):

```yaml
language: en
user_agent: "wd-squads/0.1 (https://github.com/metaodi/wd-squads; you@example.org)"
request_delay: 1.0

leagues:
  - id: Q331268   # Swiss Super League
  - id: Q9448     # Premier League
```

Other ways to choose teams (each overrides the one above it):

- `discovery_query:` — supply your own SPARQL `SELECT` that binds `?team`
  (and optionally `?teamLabel`, `?article`).
- `teams:` — pin an explicit list of club Q-IDs (handy for testing one club).

> **User-Agent:** the Wikimedia APIs require a descriptive User-Agent with a
> contact URL/e-mail. The tool refuses to run with a placeholder one.

## Running locally

```bash
pip install -r requirements.txt

# Full run using the config
python -m wd_squads --config config/teams.yaml

# Test quickly on just the first team
python -m wd_squads --config config/teams.yaml --limit 1 --verbose
```

Outputs:

- `reports/README.md` — an index table of all teams.
- `reports/<Qid>-<slug>.md` — the per-team TODO list (nice diffs in git history).
- `docs/index.html` — a self-contained, browsable dashboard.
- `docs/data.json` — the same data as JSON for further processing.

Network access to `query.wikidata.org` and `<lang>.wikipedia.org` is required.

## Running on GitHub Actions

The [`Update squad TODO`](.github/workflows/update.yml) workflow runs weekly
(and on demand via *workflow_dispatch*), regenerates the reports, and commits
them back to the repository. To publish the dashboard:

1. Push this repository to GitHub.
2. In **Settings → Pages**, set the source to **Deploy from a branch**,
   branch = your default branch, folder = **`/docs`**.
3. The dashboard will be served at `https://<user>.github.io/wd-squads/`.

The workflow needs `contents: write` permission (already declared) so it can
commit the refreshed reports.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The parsing and diff logic is covered by offline unit tests (no network needed);
see [`tests/`](tests/).

## Scope and roadmap

The MVP targets **association football** on the **English** Wikipedia, where the
squad templates are the most consistent. The design keeps the pieces separable
so future work can add other sports, other Wikipedia languages, or emit
[QuickStatements](https://quickstatements.toolforge.org/) once a suggested edit
has enough information (e.g. a confirmed date) to be applied safely.

## License

MIT — see [LICENSE](LICENSE).
