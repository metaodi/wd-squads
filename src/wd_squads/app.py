"""Wire the pieces together: discover teams, fetch data, diff, write reports."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from .config import Config, load_config
from .diff import compute_suggestions, enrich_career_years, suggestion_titles
from .http_client import HttpClient
from .report import TeamResult, now_iso, write_reports
from .wikidata import WikidataClient
from .wikipedia import WikipediaClient

log = logging.getLogger(__name__)


def run(
    config_path: str | Path,
    reports_dir: str | Path = "reports",
    docs_dir: str | Path = "docs",
    limit: Optional[int] = None,
) -> List[TeamResult]:
    """Execute a full run and write the report files. Returns the results."""
    config = load_config(config_path)
    http = HttpClient(user_agent=config.user_agent, request_delay=config.request_delay)
    wikidata = WikidataClient(http)
    wikipedia = WikipediaClient(http, language=config.language)

    results = process(config, wikidata, wikipedia, limit=limit)

    generated_at = now_iso()
    write_reports(results, reports_dir, docs_dir, generated_at=generated_at)
    log.info(
        "Wrote reports for %d teams (%d suggestions) to %s and %s",
        len(results),
        sum(len(r.suggestions) for r in results),
        reports_dir,
        docs_dir,
    )
    return results


def process(
    config: Config,
    wikidata: WikidataClient,
    wikipedia: WikipediaClient,
    limit: Optional[int] = None,
) -> List[TeamResult]:
    """Discover teams and build a :class:`TeamResult` for each (network heavy)."""
    teams = wikidata.discover_teams(config)
    if limit:
        teams = teams[:limit]
    log.info("Discovered %d teams", len(teams))

    results: List[TeamResult] = []
    for i, team in enumerate(teams, 1):
        log.info("[%d/%d] %s (%s)", i, len(teams), team.label, team.qid)
        result = TeamResult(team=team)
        try:
            squad = wikipedia.get_squad(team)
            memberships = wikidata.get_memberships(team.qid, language=team.language)
            result.squad_size = len([p for p in squad if p.qid or p.name])
            result.wikidata_current = len({m.player_qid for m in memberships if m.is_open})
            suggestions = compute_suggestions(team, squad, memberships)
            titles = suggestion_titles(suggestions)
            if titles:
                career = wikipedia.get_career_spells(titles, team.language)
                enrich_career_years(suggestions, career, team)
            result.suggestions = suggestions
        except Exception as exc:  # keep going even if one team fails
            log.exception("Failed to process %s", team.qid)
            result.error = str(exc)
        results.append(result)
    return results
